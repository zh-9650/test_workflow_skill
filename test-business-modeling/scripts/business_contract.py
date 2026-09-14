import argparse, json
from pathlib import Path
REQ={'scope','modules','cross_module_flows','confirmed_rules','open_questions','self_review','user_confirmation'}

def fail(path,msg): raise AssertionError(f'{path}: {msg}')

def _list(value,path,required=False):
    if not isinstance(value,list): fail(path,'must be a list')
    if required and not value: fail(path,'must not be empty')
    return value

def _text(value,path):
    if not isinstance(value,str) or not value.strip(): fail(path,'must be non-empty text')

def _question(q,path):
    if isinstance(q,str):
        _text(q,path); return
    if not isinstance(q,dict): fail(path,'must be text or object')
    for k in ['question','why_confirm','impact']:
        _text(q.get(k),f'{path}.{k}')
def validate(v, require_confirmed=True):
    m=REQ-set(v)
    if m: fail('business',f'missing {sorted(m)}')
    _text(v['scope'],'scope')
    if not isinstance(v['modules'],list) or not v['modules']: fail('modules','required')
    for i,mod in enumerate(v['modules']):
        for k in ['name','purpose','functions','rules','data_impacts','linkages','open_questions']:
            if k not in mod: fail(f'modules[{i}].{k}','required')
        _text(mod['name'],f'modules[{i}].name'); _text(mod['purpose'],f'modules[{i}].purpose')
        _list(mod['functions'],f'modules[{i}].functions',True)
        for j,f in enumerate(mod['functions']): _text(f,f'modules[{i}].functions[{j}]')
        for k in ['rules','data_impacts','linkages','open_questions']:
            _list(mod[k],f'modules[{i}].{k}')
        for j,q in enumerate(mod['open_questions']): _question(q,f'modules[{i}].open_questions[{j}]')
        if 'state' in mod:
            st=mod['state']
            if not isinstance(st,dict): fail(f'modules[{i}].state','must be an object')
            _list(st.get('states'),f'modules[{i}].state.states',True); _list(st.get('transitions'),f'modules[{i}].state.transitions',True)
        if 'workflows' in mod:
            flows=_list(mod['workflows'],f'modules[{i}].workflows',True)
            for j,flow in enumerate(flows):
                if not isinstance(flow,dict): fail(f'modules[{i}].workflows[{j}]','must be an object')
                _text(flow.get('name'),f'modules[{i}].workflows[{j}].name'); _list(flow.get('steps'),f'modules[{i}].workflows[{j}].steps',True)
    _list(v['cross_module_flows'],'cross_module_flows')
    _list(v['confirmed_rules'],'confirmed_rules')
    _list(v['open_questions'],'open_questions')
    for i,q in enumerate(v['open_questions']): _question(q,f'open_questions[{i}]')
    if v['self_review'].get('status')!='passed': fail('self_review.status','must pass before human confirmation')
    if require_confirmed and v['user_confirmation'].get('status')!='confirmed': fail('user_confirmation.status','must be confirmed before Case Design')
    return {'ok':True,'module_count':len(v['modules']),'open_question_count':len(v['open_questions'])}
if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--input',required=True); a.add_argument('--allow-waiting-confirmation',action='store_true'); x=a.parse_args(); print(json.dumps(validate(json.loads(Path(x.input).read_text(encoding='utf-8')),not x.allow_waiting_confirmation),ensure_ascii=False))
