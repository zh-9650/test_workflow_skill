import argparse, json, os, hashlib, re, runpy
from pathlib import Path
from datetime import datetime, timezone

EXECUTION_SCHEMA_VERSION = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / 'clarify-before-testing/scripts/workflow_versions.py')
)['EXECUTION_SCHEMA_VERSION']

def fail(path,msg): raise AssertionError(f'{path}: {msg}')
def now(): return datetime.now(timezone.utc).isoformat()

def _inside(path, root):
    try: path.resolve().relative_to(root.resolve()); return True
    except ValueError: return False

def _run_file(run_dir, ref, allowed_root, path):
    if not isinstance(ref,str) or not ref or Path(ref).is_absolute(): fail(path,'must be a Run-relative file reference')
    base=Path(run_dir).resolve(); target=(base/ref).resolve(); allowed=(base/allowed_root).resolve()
    if not _inside(target,allowed): fail(path,f'must stay under {allowed_root}')
    if not target.is_file(): fail(path,f'file does not exist: {target}')
    return target

def _read_json_evidence(run_dir, ref, case_ids, batch_id, object_ref, path, builder=None, object_type=None, expected_state=None):
    target=_run_file(run_dir,ref,Path('evidence')/batch_id,path)
    try: evidence=json.loads(target.read_text(encoding='utf-8'))
    except (OSError,ValueError) as e: fail(path,f'must reference readable JSON evidence: {e}')
    if evidence.get('batch_id')!=batch_id: fail(path,'evidence batch_id must match the current Batch')
    if evidence.get('case_id') not in case_ids: fail(path,'evidence case_id must map to this object')
    if evidence.get('object_ref')!=object_ref: fail(path,'evidence object_ref must match the prepared business object')
    if evidence.get('read_back_verified') is not True: fail(path,'evidence must record read_back_verified=true')
    case_root=Path('evidence')/batch_id/evidence['case_id']
    observation_ref=evidence.get('observation_ref'); report_ref=evidence.get('runner_report_ref')
    if not observation_ref or not report_ref: fail(path,'raw observation_ref and runner_report_ref are required; self-asserted JSON alone is insufficient')
    observation=_run_file(run_dir,observation_ref,case_root,path+'.observation_ref')
    report=_run_file(run_dir,report_ref,case_root,path+'.runner_report_ref')
    observation_hash=hashlib.sha256(observation.read_bytes()).hexdigest()
    report_hash=hashlib.sha256(report.read_bytes()).hexdigest()
    if evidence.get('observation_sha256')!=observation_hash: fail(path+'.observation_sha256','must match the raw read-back observation artifact')
    if evidence.get('runner_report_sha256')!=report_hash: fail(path+'.runner_report_sha256','must match the official Builder runner report')
    try: report_data=json.loads(report.read_text(encoding='utf-8'))
    except (OSError,ValueError) as e: fail(path+'.runner_report_ref',f'invalid runner report: {e}')
    if type(report_data.get('exit_code')) is not int or report_data['exit_code']!=0: fail(path+'.runner_report_ref','data Builder official run must have exit_code=0')
    if not isinstance(report_data.get('script_sha256'),str) or not re.fullmatch(r'[0-9a-f]{64}',report_data['script_sha256']): fail(path+'.runner_report_ref','must bind the executed TypeScript script hash')
    if builder:
        if evidence.get('builder_id')!=builder.get('builder_id'): fail(path,'evidence builder_id must match the verified Builder')
        if evidence.get('script_ref')!=builder.get('script_ref') or evidence.get('script_sha256')!=builder.get('script_sha256'):
            fail(path,'read-back must bind to the verified TypeScript Builder and its current hash')
        if report_data['script_sha256']!=builder.get('script_sha256'): fail(path+'.runner_report_ref','report script hash differs from the verified Builder')
    try: observed=json.loads(observation.read_text(encoding='utf-8'))
    except (OSError,ValueError) as e: fail(path+'.observation_ref',f'raw read-back observation must be JSON: {e}')
    if not isinstance(observed,dict) or observed.get('object_ref')!=object_ref: fail(path+'.observation_ref','raw response/page observation must contain the exact prepared object_ref')
    if observed.get('object_type')!=object_type: fail(path+'.observation_ref',f'raw observation object_type must equal {object_type!r}')
    fields=observed.get('observed_fields')
    if not isinstance(fields,dict) or not fields: fail(path+'.observation_ref','raw observation must contain non-empty observed_fields read from the business object')
    if expected_state is not None and fields.get('state',fields.get('status'))!=expected_state:
        fail(path+'.observation_ref',f'actual read-back state {fields.get("state",fields.get("status"))!r} does not equal target_state {expected_state!r}')
    if evidence.get('observed_via') not in {'node-native-fetch','playwright-page'}: fail(path+'.observed_via','must identify the actual API/UI read-back driver')
    return target

def validate_builder(b,run_dir,batch_id):
    for k in ['builder_id','object_type','business_entry','language','runner','script_ref','script_sha256','verified','verified_environment','verified_at','verified_case_id','verified_object_ref','read_back_evidence_ref']:
        if k not in b or b[k] in (None,''): fail(f'builder.{k}','required')
    if b['business_entry'] not in {'api','ui'}: fail('builder.business_entry','must be api|ui')
    expected={'api':('typescript','vitest'),'ui':('typescript','playwright-test')}[b['business_entry']]
    if (b['language'],b['runner'])!=expected: fail('builder.language/runner',f'{b["business_entry"]} builder must use {expected[0]} + {expected[1]}')
    if b['verified'] is not True: fail('builder.verified','must be true before reuse')
    script=_run_file(run_dir,b['script_ref'],'scripts/data', 'builder.script_ref')
    if script.suffix.lower()!='.ts': fail('builder.script_ref','builder must be a TypeScript script')
    digest=hashlib.sha256(script.read_bytes()).hexdigest()
    if not re.fullmatch(r'[0-9a-f]{64}',str(b['script_sha256'])) or b['script_sha256']!=digest:
        fail('builder.script_sha256','must match the current builder script SHA-256')
    _read_json_evidence(run_dir,b['read_back_evidence_ref'],[b['verified_case_id']],batch_id,b['verified_object_ref'],'builder.read_back_evidence_ref',b,b['object_type'])
    return {'ok':True,'builder_id':b['builder_id']}

def _plan_batch(plan,batch_id):
    if not isinstance(plan,dict): fail('plan','execution plan is required')
    batches={b.get('id'):b for b in plan.get('batches',[])}
    if batch_id not in batches: fail('batch_id',f'unknown batch {batch_id} in execution plan')
    cases={c.get('case_id'):c for c in plan.get('cases',[])}
    ids=list(batches[batch_id].get('case_ids',[]))
    if not ids or any(cid not in cases for cid in ids): fail('plan','batch case set is invalid')
    return batches[batch_id],[cases[cid] for cid in ids]


def _secret_reference(value,path):
    if not isinstance(value,str) or not re.fullmatch(r'(?:env|keychain|vault|secret-file):[A-Za-z0-9_.:/-]+',value):
        fail(path,'must be a non-secret reference using env:, keychain:, vault:, or secret-file:')


def _validate_actor_bindings(v,run_dir,batch_id,batch_case_ids,requirements):
    bindings=v.get('actor_bindings')
    if not isinstance(bindings,list) or not bindings: fail('actor_bindings','non-empty list required for every Batch')
    covered=set(); actors={}
    for i,b in enumerate(bindings):
        p=f'actor_bindings[{i}]'
        if not isinstance(b,dict): fail(p,'object required')
        actor=b.get('actor_ref')
        if not isinstance(actor,str) or not actor.strip(): fail(p+'.actor_ref','non-empty non-secret account reference required')
        _secret_reference(b.get('secret_ref'),p+'.secret_ref')
        cids=b.get('case_ids')
        if not isinstance(cids,list) or not cids or not set(cids)<=batch_case_ids: fail(p+'.case_ids','must map to current Batch Cases')
        if b.get('verified') is not True: fail(p+'.verified','must be true after real account verification')
        ref=b.get('verification_evidence_ref')
        evidence=_run_file(run_dir,ref,Path('evidence')/batch_id,p+'.verification_evidence_ref')
        digest=hashlib.sha256(evidence.read_bytes()).hexdigest()
        if b.get('verification_evidence_sha256')!=digest: fail(p+'.verification_evidence_sha256','must match account verification evidence')
        try: payload=json.loads(evidence.read_text(encoding='utf-8'))
        except (OSError,ValueError) as exc: fail(p+'.verification_evidence_ref',f'invalid JSON evidence: {exc}')
        if payload.get('batch_id')!=batch_id or payload.get('case_id') not in cids or payload.get('actor_ref')!=actor:
            fail(p+'.verification_evidence_ref','Batch, Case, and actor must match the binding')
        if payload.get('authenticated') is not True or payload.get('permissions_verified') is not True or payload.get('secret_resolved') is not True:
            fail(p+'.verification_evidence_ref','must prove authentication, permissions, and secret-reference resolution')
        roles=b.get('roles'); permissions=b.get('permissions')
        if not isinstance(roles,list) or not roles or not all(isinstance(x,str) and x for x in roles): fail(p+'.roles','explicit verified role list required')
        if not isinstance(permissions,list) or not all(isinstance(x,str) and x for x in permissions): fail(p+'.permissions','explicit permission list required')
        if payload.get('roles')!=roles or payload.get('permissions')!=permissions:
            fail(p+'.verification_evidence_ref','observed roles and permissions must equal actor binding')
        if payload.get('observed_via') not in {'node-native-fetch','playwright-page'}: fail(p+'.verification_evidence_ref','observed_via must be node-native-fetch or playwright-page')
        report=_run_file(run_dir,payload.get('runner_report_ref'),Path('evidence')/batch_id,p+'.runner_report_ref')
        if payload.get('runner_report_sha256')!=hashlib.sha256(report.read_bytes()).hexdigest(): fail(p+'.runner_report_sha256','must match account verification runner report')
        try: report_data=json.loads(report.read_text(encoding='utf-8'))
        except (OSError,ValueError) as exc: fail(p+'.runner_report_ref',f'invalid runner report: {exc}')
        if report_data.get('exit_code')!=0: fail(p+'.runner_report_ref','account verification runner must exit 0')
        if actor in actors: fail(p+'.actor_ref','duplicate actor_ref')
        actors[actor]=b; covered.update(cids)
    if covered!=batch_case_ids: fail('actor_bindings.case_ids',f'every Batch Case must have an actor binding; missing={sorted(batch_case_ids-covered)}')
    for req in requirements:
        for cid in set(req.get('case_ids',[])) & batch_case_ids:
            matches=[b for b in bindings if cid in b['case_ids'] and req.get('actor_role') in b['roles'] and set(req.get('permission_requirements',[]))<=set(b['permissions'])]
            if not matches: fail('actor_bindings',f'Case {cid} has no actor with planned role/permissions for {req.get("object_type")}')
    return actors

def _validate_content(v,plan,run_dir=None):
    if type(v.get('schema_version')) is not int or v['schema_version']!=EXECUTION_SCHEMA_VERSION:
        fail('schema_version',f'Data Manifest requires schema_version={EXECUTION_SCHEMA_VERSION}')
    if 'ready' in v: fail('ready','legacy top-level ready is forbidden; readiness is computed by the contract')
    if not v.get('batch_id'): fail('batch_id','required')
    batch,plan_cases=_plan_batch(plan,v['batch_id'])
    batch_case_ids={c['case_id'] for c in plan_cases}
    dr=plan.get('data_requirements')
    if not isinstance(dr,list) or not dr: fail('plan.data_requirements','new Planning data requirements are required; legacy data_required fallback is forbidden')
    batch_dr=[item for item in dr if any(cid in batch_case_ids for cid in item.get('case_ids',[])) and item.get('scope') in {'base_resource','batch_dedicated'}]
    planned_data_needed=len(batch_dr)>0
    required_case_ids={cid for item in batch_dr for cid in item.get('case_ids',[]) if cid in batch_case_ids}
    actors=_validate_actor_bindings(v,run_dir,v['batch_id'],batch_case_ids,dr)
    if not isinstance(v.get('data_required'),bool): fail('data_required','boolean required')
    objs=v.get('objects',[])
    if v['data_required'] is False:
        if not v.get('reason'): fail('reason','required when data_required=false')
        if objs: fail('objects','must be empty when data_required=false')
        if planned_data_needed: fail('data_required','cannot be false while planned cases still require prepared data')
    else:
        if not isinstance(objs,list) or not objs: fail('objects','non-empty when data_required=true')
    builders={b.get('builder_id'):b for b in v.get('builders',[])}
    if None in builders: fail('builders','builder_id required')
    for builder in builders.values(): validate_builder(builder,run_dir,v['batch_id'])
    mapped=set(); mapped_requirements=set()
    for i,o in enumerate(objs):
        p=f'objects[{i}]'
        for k in ['object_type','object_ref','creation','state_applicable','verified','read_back_verified','read_back_evidence_ref','relations_verified','case_ids']:
            if k not in o: fail(p+'.'+k,'required')
        if not o['object_type'] or not o['object_ref']: fail(p,'object_type/object_ref cannot be empty')
        for k in ['data_category','source','scope','owner','applicable_version','actor_ref','secret_ref','creation_attempts']:
            if k not in o or o[k] in (None,''): fail(p+'.'+k,'required')
        if o['data_category'] not in {'base_resource','batch_dedicated'}: fail(p+'.data_category','must be base_resource or batch_dedicated; runtime_generated belongs to Case execution')
        matching_requirements=[item for item in batch_dr if item.get('scope')==o['data_category'] and item.get('object_type')==o['object_type'] and set(o.get('case_ids',[]))<=set(item.get('case_ids',[]))]
        if not matching_requirements: fail(p+'.data_category','object category/type/Case mapping must match confirmed Planning')
        if not isinstance(o['source'],str) or not o['source'].strip(): fail(p+'.source','non-empty legal business source required')
        if o['data_category']=='batch_dedicated' and o['scope']!=v['batch_id']: fail(p+'.scope','batch_dedicated object scope must equal current batch_id')
        if o['data_category']=='base_resource' and o['scope'] not in {'project','run'}: fail(p+'.scope','base_resource scope must be project or run')
        if o['actor_ref'] not in actors: fail(p+'.actor_ref','must use a verified actor binding')
        current_version=v.get('applicable_version') or plan.get('target_environment',{}).get('initial_deployment_version')
        if not current_version or o['applicable_version']!=current_version: fail(p+'.applicable_version','object must be verified for current Manifest deployment version')
        if not any(req.get('actor_role') in actors[o['actor_ref']]['roles'] and set(req.get('permission_requirements',[]))<=set(actors[o['actor_ref']]['permissions']) for req in matching_requirements):
            fail(p+'.actor_ref','object actor must match planned role and permissions')
        _secret_reference(o['secret_ref'],p+'.secret_ref')
        if o['secret_ref']!=actors[o['actor_ref']]['secret_ref']: fail(p+'.secret_ref','must match the verified actor binding')
        attempts=o['creation_attempts']
        if not isinstance(attempts,list) or not attempts: fail(p+'.creation_attempts','non-empty creation/reconciliation attempt history required')
        for j,attempt in enumerate(attempts):
            ap=f'{p}.creation_attempts[{j}]'
            if not isinstance(attempt,dict) or not all(isinstance(attempt.get(k),str) and attempt[k].strip() for k in ('attempt_id','status','action','reconciliation')):
                fail(ap,'attempt_id, status, action, and reconciliation are required')
        if o['verified'] is not True: fail(p+'.verified','must be true')
        if o['read_back_verified'] is not True: fail(p+'.read_back_verified','must be true')
        if o['relations_verified'] is not True: fail(p+'.relations_verified','required associations must be verified')
        if not isinstance(o['case_ids'],list) or not o['case_ids']: fail(p+'.case_ids','non-empty list required')
        if not run_dir: fail('run_dir','required to resolve prepared object read-back Evidence')
        builder=builders.get(o.get('creation',{}).get('builder_id')) if isinstance(o.get('creation'),dict) else None
        _read_json_evidence(run_dir,o['read_back_evidence_ref'],o['case_ids'],v['batch_id'],o['object_ref'],p+'.read_back_evidence_ref',builder,o['object_type'],o.get('target_state') if o['state_applicable'] else None)
        unknown=set(o['case_ids'])-batch_case_ids
        if unknown: fail(p+'.case_ids',f'contains cases outside current batch: {sorted(unknown)}')
        mapped.update(o['case_ids'])
        mapped_requirements.update((cid,o['data_category'],o['object_type']) for cid in o['case_ids'])
        cr=o['creation']
        if not isinstance(cr,dict): fail(p+'.creation','object required')
        if cr.get('business_entry') not in {'api','ui'}: fail(p+'.creation.business_entry','only api|ui allowed; sql/database/internal status forbidden')
        if cr.get('implementation') not in {'direct','script'}: fail(p+'.creation.implementation','direct|script required')
        if cr.get('implementation')=='script':
            if not cr.get('builder_ref'): fail(p+'.creation.builder_ref','required for script implementation')
            bid=cr.get('builder_id')
            if not bid or bid not in builders: fail(p+'.creation.builder_id','verified builder record required')
            b=builders[bid]
            if b['business_entry']!=cr['business_entry']: fail(p+'.creation.business_entry','must match verified builder')
            if b['object_type']!=o['object_type']: fail(p+'.creation.builder_id',f'builder object_type {b["object_type"]!r} does not match object {o["object_type"]!r}')
            if cr['builder_ref']!=b['script_ref']: fail(p+'.creation.builder_ref','must equal the verified Builder script_ref')
        if not isinstance(o['state_applicable'],bool): fail(p+'.state_applicable','boolean required')
        if o['state_applicable']:
            if o.get('target_state') in (None,''): fail(p+'.target_state','required when state_applicable=true')
            if o.get('current_state') in (None,''): fail(p+'.current_state','required when state_applicable=true')
            if o['target_state']!=o['current_state']: fail(p+'.current_state',f'target state not reached: {o["target_state"]!r} != {o["current_state"]!r}')
        elif o.get('target_state') not in (None,'') or o.get('current_state') not in (None,''): fail(p,'state_applicable=false requires state fields empty')
    missing=sorted(required_case_ids-mapped)
    if missing: fail('objects.case_ids',f'planned cases requiring data have no manifest mapping: {missing}')
    required_requirements={(cid,item['scope'],item['object_type']) for item in batch_dr for cid in item.get('case_ids',[]) if cid in batch_case_ids}
    if required_requirements-mapped_requirements:
        fail('objects.data_requirements',f'every planned Case/category/object_type requirement must be covered: {sorted(required_requirements-mapped_requirements)}')
    return objs

def validate(v,plan,run_dir=None):
    objs=_validate_content(v,plan,run_dir)
    readiness={'ready':True,'checked_at':now(),'reason':'contract validated against current Batch plan and all required data is ready'}
    v['readiness']=readiness
    return {'ok':True,'batch_id':v['batch_id'],'objects':len(objs),'readiness':readiness}

def finalize_file(input_path,plan_path,output_path=None,run_dir=None):
    p=Path(input_path); v=json.loads(p.read_text(encoding='utf-8')); plan=json.loads(Path(plan_path).read_text(encoding='utf-8')); validate(v,plan,run_dir)
    out=Path(output_path) if output_path else p; out.parent.mkdir(parents=True,exist_ok=True); t=out.with_suffix(out.suffix+'.tmp')
    t.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); os.replace(t,out); return v

if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--input',required=True); a.add_argument('--plan',required=True); a.add_argument('--run-dir',required=True); a.add_argument('--finalize',action='store_true'); a.add_argument('--output'); x=a.parse_args()
    if x.finalize: out=finalize_file(x.input,x.plan,x.output,x.run_dir)
    else: out=validate(json.loads(Path(x.input).read_text(encoding='utf-8')),json.loads(Path(x.plan).read_text(encoding='utf-8')),x.run_dir)
    print(json.dumps(out,ensure_ascii=False,indent=2))
