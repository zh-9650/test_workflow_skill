/** Formal-script callsite: confirmed policy, explicit approval, persistent reservation and evidence. */
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, mkdirSync, openSync, closeSync, unlinkSync, existsSync, lstatSync, realpathSync } from 'node:fs';
import { resolve, join, relative, isAbsolute, dirname } from 'node:path';
import { runtimeContext } from './runtime-context.js';
import { redact } from './redaction.js';
import { evaluateApiSemantics, selectUiCandidate, JevBudget, type JevConfig, type JevResponse, type JevUiSnapshot } from './jev-adapter.js';

type Policy = { mode: 'required'|'conditional'|'none'; target_type: string; expected_ids: string[]; bounded_options: string[]; purpose: string;
  provider: string; model: string; model_version: string; max_cost_usd: number; max_cost_per_call_usd: number; max_calls: number; max_input_chars: number };
const hash = (data: string | Buffer): string => createHash('sha256').update(data).digest('hex');
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value !== null && typeof value === 'object') return `{${Object.entries(value).sort(([a],[b])=>a<b?-1:a>b?1:0).map(([k,v])=>`${JSON.stringify(k)}:${canonical(v)}`).join(',')}}`;
  return JSON.stringify(value);
}
function json(path: string): any { return JSON.parse(readFileSync(path,'utf8')); }
function guardPath(runDir: string, target: string): void {
  const root=resolve(runDir), path=resolve(target), rel=relative(root,path);
  if (isAbsolute(rel) || rel==='..' || rel.startsWith(`..${process.platform==='win32'?'\\':'/'}`)) throw new Error('Artifact path escapes Run');
  const realRoot=realpathSync(root);
  let current=path;
  for (;;) {
    if (existsSync(current)) {
      if (lstatSync(current).isSymbolicLink()) throw new Error('Run artifact symlink/junction is forbidden');
      const actual=relative(realRoot,realpathSync(current));
      if (isAbsolute(actual) || actual==='..' || actual.startsWith(`..${process.platform==='win32'?'\\':'/'}`)) throw new Error('Real artifact path escapes Run');
    }
    if (current===root) break;
    current=dirname(current);
  }
}
function prepare(expectedId: string, targetType: string, outbound: unknown, triggered?: boolean) {
  const scope=runtimeContext(); const planPath=join(scope.runDir,'internal/execution/execution-plan.json');
  for (const path of [planPath,join(scope.runDir,'internal/state/run-status.json'),join(scope.runDir,'internal/execution/jev-approval.json')]) guardPath(scope.runDir,path);
  const state=json(join(scope.runDir,'internal/state/run-status.json'));
  const binding=state.confirmation_bindings?.['execution-plan'];
  if (!binding || resolve(binding.contract_path)!==resolve(planPath) || hash(readFileSync(planPath))!==binding.contract_sha256) throw new Error('Current confirmed plan binding is missing or stale');
  const plan=json(planPath); const pc=plan.cases.find((c: any)=>c.case_id===scope.caseId && c.batch_id===scope.batchId);
  const policy: Policy=pc?.jev_policy;
  if (!policy || policy.mode==='none' || policy.target_type!==targetType || !policy.expected_ids.includes(expectedId)) throw new Error('Jev call is outside confirmed Case policy');
  if (policy.mode==='conditional' && triggered!==true) throw new Error('Conditional policy requires recorded observed trigger before calling');
  if (policy.provider!=='typesafe-official' || policy.model!==`jev-${policy.model_version}`) throw new Error('Pinned official provider/model required');
  const policySha=hash(canonical(policy));
  const approval=json(join(scope.runDir,'internal/execution/jev-approval.json'));
  if (approval.approved!==true || !approval.user_decision_ref || approval.plan_sha256!==binding.contract_sha256
    || approval.environment_id!==plan.target_environment.env_id || approval.policy_sha256?.[scope.caseId]!==policySha
    || typeof approval.max_cost_usd!=='number' || !Number.isFinite(approval.max_cost_usd) || approval.max_cost_usd<=0
    || !Array.isArray(approval.outbound_fields?.[targetType])) throw new Error('Explicit current user data/budget/environment approval required');
  const outboundFields=outbound!==null && typeof outbound==='object' && !Array.isArray(outbound) ? Object.keys(outbound) : ['$text'];
  if (outboundFields.some(field=>!approval.outbound_fields[targetType].includes(field))) throw new Error('Source fields exceed explicitly approved outbound fields');
  const clean=redact(outbound);
  if (JSON.stringify(clean)!==JSON.stringify(outbound)) throw new Error('Outbound source contains secret fields; redact before invoking');
  const config: JevConfig={ endpoint:'https://api.typesafe.ai/v1/systemone', apiKey:process.env.TYPESAFE_API_KEY ?? '',
    model:policy.model,modelVersion:policy.model_version,budgetCapUsd:policy.max_cost_usd,maxCostPerCallUsd:policy.max_cost_per_call_usd,
    maxCalls:policy.max_calls,maxInputChars:policy.max_input_chars,timeoutMs:15000 };
  // Reserve across process restarts and test retries before any external request.
  const directory=join(scope.runDir,'internal/execution/jev-budget'); guardPath(scope.runDir,directory); mkdirSync(directory,{recursive:true});
  const path=join(directory,'run-budget.json'); const lock=`${path}.lock`; const fd=openSync(lock,'wx');
  let sequence: number;
  try {
    let budget:{plan_sha256:string;reserved_cost_usd:number;cases:Record<string,{policy_sha256:string;calls:number;reserved_cost_usd:number}>}={plan_sha256:binding.contract_sha256,reserved_cost_usd:0,cases:{}};
    guardPath(scope.runDir,path);
    try { budget=json(path); } catch (error: any) { if (error.code!=='ENOENT') throw error; }
    const caseBudget=budget.cases[scope.caseId] ?? {policy_sha256:policySha,calls:0,reserved_cost_usd:0};
    if (budget.plan_sha256!==binding.contract_sha256 || caseBudget.policy_sha256!==policySha || caseBudget.calls>=policy.max_calls
      || caseBudget.reserved_cost_usd+policy.max_cost_per_call_usd>policy.max_cost_usd+1e-12
      || budget.reserved_cost_usd+policy.max_cost_per_call_usd>approval.max_cost_usd+1e-12) throw new Error('Persistent Run/Case budget exhausted or policy changed');
    caseBudget.calls+=1; caseBudget.reserved_cost_usd+=policy.max_cost_per_call_usd; sequence=caseBudget.calls;
    budget.cases[scope.caseId]=caseBudget; budget.reserved_cost_usd+=policy.max_cost_per_call_usd;
    writeFileSync(path,JSON.stringify(budget,null,2),'utf8');
  } finally { closeSync(fd); unlinkSync(lock); }
  const evidence=join(scope.runDir,'evidence',scope.batchId,scope.caseId,'jev',`${scope.attemptId}-${sequence}`);
  guardPath(scope.runDir,evidence); mkdirSync(evidence,{recursive:true});
  const save=(name: string,value: unknown): Record<string,string>=>{
    const file=join(evidence,`${name}.json`); guardPath(scope.runDir,file); const body=JSON.stringify(redact(value),null,2)+'\n'; writeFileSync(file,body,'utf8');
    const ref=relative(scope.runDir,file).replaceAll('\\','/'); if (isAbsolute(ref) || ref.startsWith('..')) throw new Error('Evidence escapes Run');
    return { [`${name}_ref`]:ref,[`${name}_sha256`]:hash(body) };
  };
  return {scope,policy,policySha,config,save};
}
function finish(context: ReturnType<typeof prepare>, expectedId: string, response: JevResponse, extra: Record<string,string>) {
  const {scope,policy,policySha,save}=context;
  const refs={...save('request',{case_id:scope.caseId,expected_id:expectedId,target_type:policy.target_type,policy_sha256:policySha,request:response.request}),
    ...save('response',response.response),...save('usage',response.usage),...extra};
  // TypeSafe usage may omit monetary charges. Preserve unknown cost; billing reconciliation is then required.
  if (response.usage.costUsd===null) throw new Error('Jev usage lacks verified monetary cost; evidence saved, formal result requires billing reconciliation');
  return { ...refs,target_type:policy.target_type,expected_id:expectedId,provider:policy.provider,model:response.model,model_version:policy.model_version,
    policy_sha256:policySha,selected_option:response.selectedOption,selected_id:response.selectedOption,confidence:response.confidence,cost_usd:response.usage.costUsd };
}
export async function judgeApiResponse(expectedId: string, sourceResponse: unknown, triggered?: boolean) {
  const context=prepare(expectedId,'api_semantic_judgment',sourceResponse,triggered);
  const source=context.save('source_response',sourceResponse);
  const response=await evaluateApiSemantics({kind:'api_semantic_judgment',evaluationGoal:context.policy.purpose,
    responseExcerpt:JSON.stringify(sourceResponse),options:context.policy.bounded_options},context.config,new JevBudget());
  return finish(context,expectedId,response,source);
}
export async function chooseUiCandidate(expectedId: string,snapshot: JevUiSnapshot,fresh: ()=>Promise<JevUiSnapshot>,triggered?: boolean) {
  const context=prepare(expectedId,'ui_candidate_selection',snapshot,triggered);
  if (snapshot.candidates.some(c=>!context.policy.bounded_options.includes(c.id))) throw new Error('Candidate IDs exceed confirmed policy');
  const source=context.save('candidate_snapshot',snapshot);
  const response=await selectUiCandidate({kind:'ui_candidate_selection',stepDescription:context.policy.purpose,snapshot},context.config,new JevBudget(),fresh);
  return finish(context,expectedId,response,{...source,...context.save('post_selection_revalidation',response.postSelectionSnapshot)});
}
