// Mocked integration only: no network, no host dispatch acceptance, no charge.
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, symlinkSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
if (!process.env.JEV_RUNTIME_MODULE) throw Error('Compile the framework and set JEV_RUNTIME_MODULE to its emitted jev-runtime.js');
const runtime=await import(pathToFileURL(process.env.JEV_RUNTIME_MODULE));
const canonical=v=>Array.isArray(v)?`[${v.map(canonical).join(',')}]`:v!==null&&typeof v==='object'?`{${Object.entries(v).sort(([a],[b])=>a<b?-1:a>b?1:0).map(([k,x])=>`${JSON.stringify(k)}:${canonical(x)}`).join(',')}}`:JSON.stringify(v);
const hash=v=>createHash('sha256').update(v).digest('hex');
function setup(cap=0.01) {
  const run=mkdtempSync(join(tmpdir(),'jev-mock-runtime-'));
  const policy={mode:'required',target_type:'api_semantic_judgment',expected_ids:['E1'],bounded_options:['valid','invalid'],purpose:'Synthetic semantic check',provider:'typesafe-official',model:'jev-1.13.0',model_version:'1.13.0',max_cost_usd:0.02,max_cost_per_call_usd:0.01,max_calls:2,max_input_chars:4096};
  const plan={target_environment:{env_id:'fixture'},cases:['C1','C2'].map(case_id=>({case_id,batch_id:'B1',jev_policy:policy}))};
  const planPath=join(run,'internal/execution/execution-plan.json');
  const write=(ref,value)=>{const p=join(run,ref);mkdirSync(join(p,'..'),{recursive:true});writeFileSync(p,JSON.stringify(value));};
  write('internal/execution/execution-plan.json',plan);
  const planHash=hash(readFileSync(planPath));
  write('internal/state/run-status.json',{confirmation_bindings:{'execution-plan':{contract_path:planPath,contract_sha256:planHash}}});
  write('internal/execution/jev-approval.json',{approved:true,user_decision_ref:'synthetic-no-charge',plan_sha256:planHash,environment_id:'fixture',max_cost_usd:cap,outbound_fields:{api_semantic_judgment:['status']},policy_sha256:{C1:hash(canonical(policy)),C2:hash(canonical(policy))}});
  Object.assign(process.env,{TEST_RUN_DIR:run,TEST_BATCH_ID:'B1',TEST_CASE_ID:'C1',TEST_SCRIPT_TARGET:'scripts/api/B1/C1.test.ts',TEST_ATTEMPT_ID:'mock-1',TEST_TASK_ID:'mock-task',TEST_TASK_HASH:'mock-hash',TEST_WORKER_SESSION_ID:'synthetic',TEST_API_BASE_URL:'http://127.0.0.1:1',TYPESAFE_API_KEY:'mock-only'});
  let calls=0;
  globalThis.fetch=async()=>{calls++;return new Response(JSON.stringify({model:'jev-1.13.0',answers:{judgment:{type:'choice',choice:'valid',confidence:0.9,probabilities:{valid:0.9,invalid:0.1}}},usage:{input_tokens:10,output_tokens:2,cost:0.001}}));};
  return {run,calls:()=>calls};
}
test('Run budget is shared across Case calls',async()=>{
  const scope=setup(); await runtime.judgeApiResponse('E1',{status:200});
  process.env.TEST_CASE_ID='C2';process.env.TEST_SCRIPT_TARGET='scripts/api/B1/C2.test.ts';
  await assert.rejects(runtime.judgeApiResponse('E1',{status:200}),/budget exhausted/);
  assert.equal(scope.calls(),1);
});
test('unapproved outbound fields never reach fetch',async()=>{
  const scope=setup(); await assert.rejects(runtime.judgeApiResponse('E1',{status:200,body:'unapproved'}),/approved outbound/);
  assert.equal(scope.calls(),0);
});
test('unknown monetary charge cannot create a formal invocation',async()=>{
  const scope=setup();globalThis.fetch=async()=>new Response(JSON.stringify({model:'jev-1.13.0',answers:{judgment:{type:'choice',choice:'valid',confidence:0.9,probabilities:{valid:0.9,invalid:0.1}}},usage:{input_tokens:10,output_tokens:2}}));
  await assert.rejects(runtime.judgeApiResponse('E1',{status:200}),/billing reconciliation/);
  const usage=JSON.parse(readFileSync(join(scope.run,'evidence/B1/C1/jev/mock-1-1/usage.json'),'utf8'));
  assert.equal(usage.costUsd,null);
});
test('evidence junction cannot write outside Run',async()=>{
  const scope=setup();const outside=mkdtempSync(join(tmpdir(),'jev-outside-'));
  symlinkSync(outside,join(scope.run,'evidence'),process.platform==='win32'?'junction':'dir');
  await assert.rejects(runtime.judgeApiResponse('E1',{status:200}),/symlink\/junction/);
  assert.equal(scope.calls(),0);assert.equal(existsSync(join(outside,'B1')),false);
});
