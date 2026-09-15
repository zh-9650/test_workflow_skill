import argparse, json, os
from pathlib import Path
from datetime import datetime, timezone

def fail(path,msg): raise AssertionError(f'{path}: {msg}')
def now(): return datetime.now(timezone.utc).isoformat()

def validate_builder(b):
    for k in ['builder_id','object_type','business_entry','script_ref','verified','verified_environment','verified_at']:
        if k not in b or b[k] in (None,''): fail(f'builder.{k}','required')
    if b['business_entry'] not in {'api','ui'}: fail('builder.business_entry','must be api|ui')
    if b['verified'] is not True: fail('builder.verified','must be true before reuse')
    return {'ok':True,'builder_id':b['builder_id']}

def _plan_batch(plan,batch_id):
    if not isinstance(plan,dict): fail('plan','execution plan is required')
    batches={b.get('id'):b for b in plan.get('batches',[])}
    if batch_id not in batches: fail('batch_id',f'unknown batch {batch_id} in execution plan')
    cases={c.get('case_id'):c for c in plan.get('cases',[])}
    ids=list(batches[batch_id].get('case_ids',[]))
    if not ids or any(cid not in cases for cid in ids): fail('plan','batch case set is invalid')
    return batches[batch_id],[cases[cid] for cid in ids]

def _validate_content(v,plan):
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
    mapped=set()
    for i,o in enumerate(objs):
        p=f'objects[{i}]'
        for k in ['object_type','object_ref','creation','state_applicable','verified','read_back_verified','relations_verified','case_ids']:
            if k not in o: fail(p+'.'+k,'required')
        if not o['object_type'] or not o['object_ref']: fail(p,'object_type/object_ref cannot be empty')
        if o['verified'] is not True: fail(p+'.verified','must be true')
        if o['read_back_verified'] is not True: fail(p+'.read_back_verified','must be true')
        if o['relations_verified'] is not True: fail(p+'.relations_verified','required associations must be verified')
        if not isinstance(o['case_ids'],list) or not o['case_ids']: fail(p+'.case_ids','non-empty list required')
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
            validate_builder(builders[bid]); b=builders[bid]
            if b['business_entry']!=cr['business_entry']: fail(p+'.creation.business_entry','must match verified builder')
            if b['object_type']!=o['object_type']: fail(p+'.creation.builder_id',f'builder object_type {b["object_type"]!r} does not match object {o["object_type"]!r}')
        if not isinstance(o['state_applicable'],bool): fail(p+'.state_applicable','boolean required')
        if o['state_applicable']:
            if o.get('target_state') in (None,''): fail(p+'.target_state','required when state_applicable=true')
            if o.get('current_state') in (None,''): fail(p+'.current_state','required when state_applicable=true')
            if o['target_state']!=o['current_state']: fail(p+'.current_state',f'target state not reached: {o["target_state"]!r} != {o["current_state"]!r}')
        elif o.get('target_state') not in (None,'') or o.get('current_state') not in (None,''): fail(p,'state_applicable=false requires state fields empty')
    missing=sorted(required_case_ids-mapped)
    if missing: fail('objects.case_ids',f'planned cases requiring data have no manifest mapping: {missing}')
    return objs

def validate(v,plan):
    objs=_validate_content(v,plan)
    readiness={'ready':True,'checked_at':now(),'reason':'contract validated against current Batch plan and all required data is ready'}
    v['readiness']=readiness
    return {'ok':True,'batch_id':v['batch_id'],'objects':len(objs),'readiness':readiness}

def finalize_file(input_path,plan_path,output_path=None):
    p=Path(input_path); v=json.loads(p.read_text(encoding='utf-8')); plan=json.loads(Path(plan_path).read_text(encoding='utf-8')); validate(v,plan)
    out=Path(output_path) if output_path else p; out.parent.mkdir(parents=True,exist_ok=True); t=out.with_suffix(out.suffix+'.tmp')
    t.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); os.replace(t,out); return v

if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--input',required=True); a.add_argument('--plan',required=True); a.add_argument('--finalize',action='store_true'); a.add_argument('--output'); x=a.parse_args()
    if x.finalize: out=finalize_file(x.input,x.plan,x.output)
    else: out=validate(json.loads(Path(x.input).read_text(encoding='utf-8')),json.loads(Path(x.plan).read_text(encoding='utf-8')))
    print(json.dumps(out,ensure_ascii=False,indent=2))
