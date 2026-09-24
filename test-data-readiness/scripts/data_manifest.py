import argparse, json, os, hashlib, re
from pathlib import Path
from datetime import datetime, timezone

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

def _validate_content(v,plan,run_dir=None):
    if 'ready' in v: fail('ready','legacy top-level ready is forbidden; readiness is computed by the contract')
    if not v.get('batch_id'): fail('batch_id','required')
    batch,plan_cases=_plan_batch(plan,v['batch_id'])
    batch_case_ids={c['case_id'] for c in plan_cases}
    if not isinstance(v.get('data_required'),bool): fail('data_required','boolean required')
    objs=v.get('objects',[])
    required_case_ids={c['case_id'] for c in plan_cases if c.get('data_required') is not False}
    if v['data_required'] is False:
        if not v.get('reason'): fail('reason','required when data_required=false')
        if objs: fail('objects','must be empty when data_required=false')
        if required_case_ids: fail('data_required','cannot be false while planned cases still require prepared data; mark those plan cases data_required=false')
    else:
        if not isinstance(objs,list) or not objs: fail('objects','non-empty when data_required=true')
    builders={b.get('builder_id'):b for b in v.get('builders',[])}
    if None in builders: fail('builders','builder_id required')
    for builder in builders.values(): validate_builder(builder,run_dir,v['batch_id'])
    mapped=set()
    for i,o in enumerate(objs):
        p=f'objects[{i}]'
        for k in ['object_type','object_ref','creation','state_applicable','verified','read_back_verified','read_back_evidence_ref','relations_verified','case_ids']:
            if k not in o: fail(p+'.'+k,'required')
        if not o['object_type'] or not o['object_ref']: fail(p,'object_type/object_ref cannot be empty')
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
