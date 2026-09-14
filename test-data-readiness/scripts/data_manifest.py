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

def _validate_content(v):
    if 'ready' in v: fail('ready','legacy top-level ready is forbidden; readiness is computed by the contract')
    if not v.get('batch_id'): fail('batch_id','required')
    if not isinstance(v.get('data_required'),bool): fail('data_required','boolean required')
    objs=v.get('objects',[])
    if v['data_required'] is False:
        if not v.get('reason'): fail('reason','required when data_required=false')
        if objs: fail('objects','must be empty when data_required=false')
    else:
        if not isinstance(objs,list) or not objs: fail('objects','non-empty when data_required=true')
    builders={b.get('builder_id'):b for b in v.get('builders',[])}
    if None in builders: fail('builders','builder_id required')
    seen_refs=set()
    for i,o in enumerate(objs):
        p=f'objects[{i}]'
        for k in ['object_type','object_ref','creation','state_applicable','verified','read_back_verified','relations_verified','access_verified','case_ids','cleanup']:
            if k not in o: fail(p+'.'+k,'required')
        if not o['object_type'] or not o['object_ref']: fail(p,'object_type/object_ref cannot be empty')
        if o['object_ref'] in seen_refs: fail(p+'.object_ref','duplicate object reference')
        seen_refs.add(o['object_ref'])
        if o['verified'] is not True: fail(p+'.verified','must be true')
        if o['read_back_verified'] is not True: fail(p+'.read_back_verified','must be true')
        if o['relations_verified'] is not True: fail(p+'.relations_verified','required associations must be verified')
        if o['access_verified'] is not True: fail(p+'.access_verified','current test account access must be verified')
        if not isinstance(o['case_ids'],list) or not o['case_ids']: fail(p+'.case_ids','non-empty list required')
        if not isinstance(o['cleanup'],(str,dict)) or not o['cleanup']: fail(p+'.cleanup','cleanup strategy required')
        cr=o['creation']
        if not isinstance(cr,dict): fail(p+'.creation','object required')
        if cr.get('business_entry') not in {'api','ui'}: fail(p+'.creation.business_entry','only api|ui allowed; sql/database/internal status forbidden')
        if cr.get('implementation') not in {'direct','script'}: fail(p+'.creation.implementation','direct|script required')
        if cr.get('implementation')=='script':
            ref=cr.get('builder_ref')
            if not ref: fail(p+'.creation.builder_ref','required for script implementation')
            bid=cr.get('builder_id')
            if not bid or bid not in builders: fail(p+'.creation.builder_id','verified builder record required')
            validate_builder(builders[bid])
            if builders[bid]['business_entry'] != cr['business_entry']: fail(p+'.creation.business_entry','must match verified builder')
        if not isinstance(o['state_applicable'],bool): fail(p+'.state_applicable','boolean required')
        if o['state_applicable']:
            if o.get('target_state') in (None,''): fail(p+'.target_state','required when state_applicable=true')
            if o.get('current_state') in (None,''): fail(p+'.current_state','required when state_applicable=true')
            if o['target_state'] != o['current_state']: fail(p+'.current_state',f'target state not reached: {o["target_state"]!r} != {o["current_state"]!r}')
        else:
            if o.get('target_state') not in (None,'') or o.get('current_state') not in (None,''):
                fail(p,'state_applicable=false requires state fields empty')
    return objs

def validate(v):
    objs=_validate_content(v)
    readiness={'ready':True,'checked_at':now(),'reason':'contract validated and all required data is ready'}
    v['readiness']=readiness
    return {'ok':True,'batch_id':v['batch_id'],'objects':len(objs),'readiness':readiness}

def finalize_file(input_path, output_path=None):
    p=Path(input_path); v=json.loads(p.read_text(encoding='utf-8')); validate(v)
    out=Path(output_path) if output_path else p
    out.parent.mkdir(parents=True,exist_ok=True); t=out.with_suffix(out.suffix+'.tmp')
    t.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); os.replace(t,out)
    return v

if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--input',required=True); a.add_argument('--finalize',action='store_true'); a.add_argument('--output'); x=a.parse_args()
    if x.finalize:
        print(json.dumps(finalize_file(x.input,x.output),ensure_ascii=False,indent=2))
    else:
        v=json.loads(Path(x.input).read_text(encoding='utf-8')); print(json.dumps(validate(v),ensure_ascii=False))
