import argparse, json
from pathlib import Path

REQ={'scope','modules','cross_module_flows','confirmed_rules','open_questions','self_review'}
SELF_CHECKS={'scope_checked','modules_checked','rules_checked','state_flow_checked','impact_linkage_checked','open_questions_checked','readability_checked'}


def fail(path,msg): raise AssertionError(f'{path}: {msg}')
def nonempty_text(v): return isinstance(v,str) and bool(v.strip())
def nonempty_list(v): return isinstance(v,list) and bool(v)


def _validate_scope(scope):
    if scope in (None,'',[],{}): fail('scope','must describe the current testing scope')
    if isinstance(scope,dict):
        if not any(scope.get(k) for k in ('in_scope','direct','modules','description')):
            fail('scope','must contain a non-empty direct/in-scope description')


def _validate_question(q,path):
    if not isinstance(q,dict): fail(path,'object required')
    if not nonempty_text(q.get('question')): fail(path+'.question','non-empty required')
    if not isinstance(q.get('affects_expected'),bool): fail(path+'.affects_expected','boolean required')
    status=q.get('status','pending')
    if status not in {'pending','confirmed','not_blocking','out_of_scope'}: fail(path+'.status','invalid status')
    if q['affects_expected'] and status=='pending':
        scopes=q.get('affected_scopes')
        if not isinstance(scopes,list) or not scopes or not all(nonempty_text(x) for x in scopes):
            fail(path+'.affected_scopes','non-empty affected scopes required for unresolved oracle-changing question')
    return status


def validate(v, require_confirmed=True):
    m=REQ-set(v)
    if m: fail('business',f'missing {sorted(m)}')
    _validate_scope(v['scope'])
    modules=v['modules']
    if not isinstance(modules,list) or not modules: fail('modules','required and non-empty')
    names=[]; pending_blocking=[]
    for i,mod in enumerate(modules):
        p=f'modules[{i}]'
        if not isinstance(mod,dict): fail(p,'object required')
        for k in ['name','purpose','functions','rules','data_impacts','linkages','open_questions']:
            if k not in mod: fail(p+'.'+k,'required')
        if not nonempty_text(mod['name']): fail(p+'.name','non-empty required')
        if not nonempty_text(mod['purpose']): fail(p+'.purpose','non-empty required')
        if not nonempty_list(mod['functions']) or not all(nonempty_text(x) for x in mod['functions']): fail(p+'.functions','non-empty business functions required')
        if not isinstance(mod['rules'],list): fail(p+'.rules','list required')
        if not isinstance(mod['data_impacts'],list): fail(p+'.data_impacts','list required')
        if not isinstance(mod['linkages'],list): fail(p+'.linkages','list required')
        if not isinstance(mod['open_questions'],list): fail(p+'.open_questions','list required')
        if mod.get('state_applicable') is True and not nonempty_list(mod.get('states')): fail(p+'.states','required when state_applicable=true')
        if mod.get('flow_applicable') is True and not nonempty_list(mod.get('flows')): fail(p+'.flows','required when flow_applicable=true')
        if mod.get('state_applicable') is False and mod.get('states') not in (None,[],{}): fail(p+'.states','must be empty when state_applicable=false')
        if mod.get('flow_applicable') is False and mod.get('flows') not in (None,[],{}): fail(p+'.flows','must be empty when flow_applicable=false')
        for j,q in enumerate(mod['open_questions']):
            st=_validate_question(q,f'{p}.open_questions[{j}]')
            if q.get('affects_expected') and st=='pending': pending_blocking.extend(q.get('affected_scopes',[]))
        names.append(mod['name'].strip())
    if len(names)!=len(set(names)): fail('modules.name','duplicate module names')
    if not isinstance(v['cross_module_flows'],list): fail('cross_module_flows','list required (may be empty only when no meaningful cross-module flow exists)')
    for i,f in enumerate(v['cross_module_flows']):
        p=f'cross_module_flows[{i}]'
        if not isinstance(f,dict): fail(p,'object required')
        if not nonempty_text(f.get('name')): fail(p+'.name','required')
        if not nonempty_list(f.get('steps')): fail(p+'.steps','non-empty steps required')
    if not isinstance(v['confirmed_rules'],list): fail('confirmed_rules','list required')
    if not isinstance(v['open_questions'],list): fail('open_questions','list required')
    for i,q in enumerate(v['open_questions']):
        st=_validate_question(q,f'open_questions[{i}]')
        if q.get('affects_expected') and st=='pending': pending_blocking.extend(q.get('affected_scopes',[]))
    sr=v['self_review']
    if not isinstance(sr,dict) or sr.get('status')!='passed': fail('self_review.status','must pass before human confirmation')
    checks=sr.get('checks',{})
    for k in SELF_CHECKS:
        if checks.get(k) is not True: fail(f'self_review.checks.{k}','must be true')
    blocked=set(v.get('blocked_scopes',[]))
    if pending_blocking:
        missing=sorted(set(pending_blocking)-blocked)
        if missing: fail('blocked_scopes',f'unresolved oracle-changing questions must block affected scopes: {missing}')
    if require_confirmed:
        uc=v['user_confirmation']
        if not isinstance(uc,dict) or uc.get('status')!='confirmed': fail('user_confirmation.status','must be confirmed before Case Design')
        if not uc.get('confirmed_scope'): fail('user_confirmation.confirmed_scope','must identify the confirmed scope')
    return {'ok':True,'module_count':len(modules),'open_question_count':len(v['open_questions'])+sum(len(m.get('open_questions',[])) for m in modules),'blocked_scopes':sorted(blocked)}


if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--input',required=True); a.add_argument('--allow-waiting-confirmation',action='store_true'); x=a.parse_args()
    print(json.dumps(validate(json.loads(Path(x.input).read_text(encoding='utf-8')),not x.allow_waiting_confirmation),ensure_ascii=False))
