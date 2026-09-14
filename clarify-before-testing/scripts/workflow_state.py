from __future__ import annotations
import argparse,json,os,hashlib
from pathlib import Path
from datetime import datetime, timezone

STAGES=['business-modeling','case-design','execution-planning','data-readiness','execution-runtime','defect-handling','result-review','closed']
LEGAL={
 'business-modeling':{'case-design'},
 'case-design':{'execution-planning'},
 'execution-planning':{'data-readiness'},
 'data-readiness':{'execution-runtime'},
 'execution-runtime':{'defect-handling','result-review','data-readiness','execution-planning','case-design'},
 'defect-handling':{'execution-runtime','result-review'},
 'result-review':{'closed'},
 'closed':set(),
}
BACKWARD={('execution-runtime','data-readiness'),('execution-runtime','execution-planning'),('execution-runtime','case-design'),('defect-handling','execution-runtime')}

FLAG_ALIASES={
    'business_self_review_passed':'business_understanding_self_reviewed',
    'business_understanding_confirmed':'business_understanding_confirmed',
    'test_points_self_review_passed':'test_points_self_reviewed',
    'test_points_confirmed':'test_points_confirmed',
    'test_cases_self_review_passed':'test_cases_self_reviewed',
    'test_cases_confirmed':'test_cases_confirmed',
    'planning_self_review_passed':'planning_self_reviewed',
    'execution_plan_confirmed':'execution_plan_confirmed',
}

def _run_root(state_path):
    p=Path(state_path).resolve()
    if p.name!='run-status.json' or p.parent.name!='state' or p.parent.parent.name!='internal':
        fail('state','state path must be RUN/internal/state/run-status.json')
    return p.parent.parent.parent

def _digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def now(): return datetime.now(timezone.utc).isoformat()
def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,v):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix(p.suffix+'.tmp'); t.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); os.replace(t,p)
def fail(path,msg): raise AssertionError(f'{path}: {msg}')

def init(run_dir,run_id):
    r=Path(run_dir); [ (r/x).mkdir(parents=True,exist_ok=True) for x in ['deliverables','dashboard','internal/state','internal/business','internal/design','internal/execution','internal/data','internal/defects','scripts/data','scripts/ui','scripts/api','scripts/temp','evidence','logs','downloads','scratch']]
    confirmations={'business_understanding_self_reviewed':False,'business_understanding_confirmed':False,'test_points_self_reviewed':False,'test_points_confirmed':False,'test_cases_self_reviewed':False,'test_cases_confirmed':False,'planning_self_reviewed':False,'execution_plan_confirmed':False}
    s={'run_id':run_id,'current_stage':'business-modeling','current_batch':None,'current_case':None,'current_worker':None,'current_reviewer':None,'last_event':None,'current_action':{'type':'build_business_understanding'},'batch_status':{},'open_defects':[],'blocked_items':[],'pending_user_inputs':[],
       'confirmations':confirmations,'artifacts':{},
       'current_batch_data_ready':False,'next_action':{'type':'build_business_understanding'},'updated_at':now()}
    write(r/'internal/state/run-status.json',s); return s

def set_flag(path,key,value=True):
    s=read(path)
    if key=='current_batch_data_ready': s[key]=bool(value)
    else:
        canonical=FLAG_ALIASES.get(key,key)
        if canonical not in s.setdefault('confirmations',{}): fail('confirmations',f'unknown flag {key}')
        s['confirmations'][canonical]=bool(value)
        for old,new in FLAG_ALIASES.items():
            if new==canonical: s['confirmations'][old]=bool(value)
    s['updated_at']=now(); write(path,s); return s

def _check_prereq(s,source,target):
    c=s.get('confirmations',{})
    if (source,target)==('business-modeling','case-design'):
        _require_artifact(s,'business_understanding',True)
        if not c.get('business_understanding_self_reviewed'): fail('transition','business understanding self-review must pass')
        if not c.get('business_understanding_confirmed'): fail('transition','business understanding must be user-confirmed')
    elif (source,target)==('case-design','execution-planning'):
        if not c.get('test_points_confirmed'): fail('transition','test points must be confirmed')
        _require_artifact(s,'test_points',True)
        _require_artifact(s,'test_cases',True)
        if not c.get('test_points_self_reviewed'): fail('transition','test points self-review must pass')
        if not c.get('test_cases_self_reviewed'): fail('transition','test cases self-review must pass')
        if not c.get('test_cases_confirmed'): fail('transition','test cases must be confirmed')
    elif (source,target)==('execution-planning','data-readiness'):
        _require_artifact(s,'execution_plan',True)
        if not c.get('planning_self_reviewed'): fail('transition','planning self-review must pass')
        if not c.get('execution_plan_confirmed'): fail('transition','execution plan must be user-confirmed')
    elif (source,target)==('data-readiness','execution-runtime'):
        if s.get('current_batch_data_ready') is not True: fail('transition','current Batch data must be ready')
    elif (source,target)==('result-review','closed'):
        if s.get('final_review_status')!='passed' or not s.get('final_review_ref'): fail('final_review_status','validated final review is required before closed')
        _require_final_review(s)

def _require_artifact(s,kind,confirmed=False):
    item=s.get('artifacts',{}).get(kind)
    if not isinstance(item,dict) or item.get('self_review_status')!='passed': fail(f'artifacts.{kind}','recorded artifact with passed self-review required')
    if confirmed and item.get('confirmation_status')!='confirmed': fail(f'artifacts.{kind}.confirmation_status','user confirmation required')
    p=Path(item.get('absolute_path',''))
    if not p.exists() or _digest(p)!=item.get('sha256'): fail(f'artifacts.{kind}','artifact missing or changed; re-record and re-review it')

def _require_final_review(s):
    p=Path(s.get('final_review_absolute_path',''))
    if not p.exists() or _digest(p)!=s.get('final_review_sha256'): fail('final_review_ref','validated final review is missing or changed')

def set_final_review(path,status):
    if status not in {'passed','not_ready'}: fail('final_review_status','passed|not_ready required')
    s=read(path)
    if status=='passed' and not s.get('final_review_ref'): fail('final_review_ref','record a validated final review before marking passed')
    s['final_review_status']=status; s['updated_at']=now(); write(path,s); return s

def record_artifact(state_path,kind,artifact_path,self_review_status='passed',confirmation_status=None):
    s=read(state_path); root=_run_root(state_path); p=Path(artifact_path)
    p=(root/p).resolve() if not p.is_absolute() else p.resolve()
    if not p.exists() or not p.is_file(): fail(f'artifacts.{kind}.path',f'file does not exist: {p}')
    try: rel=p.relative_to(root)
    except ValueError: fail(f'artifacts.{kind}.path','artifact must be inside the Run directory')
    if self_review_status!='passed': fail(f'artifacts.{kind}.self_review_status','must be passed before recording')
    if confirmation_status not in {None,'confirmed','pending'}: fail(f'artifacts.{kind}.confirmation_status','confirmed|pending|null required')
    old=s.setdefault('artifacts',{}).get(kind); digest=_digest(p)
    s['artifacts'][kind]={'path':str(rel),'absolute_path':str(p),'sha256':digest,'self_review_status':self_review_status,'confirmation_status':confirmation_status,'recorded_at':now()}
    c=s.setdefault('confirmations',{})
    mapping={'business_understanding':('business_understanding_self_reviewed','business_understanding_confirmed'),'test_points':('test_points_self_reviewed','test_points_confirmed'),'test_cases':('test_cases_self_reviewed','test_cases_confirmed'),'execution_plan':('planning_self_reviewed','execution_plan_confirmed')}
    if kind in mapping:
        c[mapping[kind][0]]=True; c[mapping[kind][1]]=confirmation_status=='confirmed'
    if old and old.get('sha256')!=digest:
        order=['business_understanding','test_points','test_cases','execution_plan']; index=order.index(kind) if kind in order else -1
        for downstream in order[index+1:]: s['artifacts'].pop(downstream,None)
        for flag in ['test_points_self_reviewed','test_points_confirmed','test_cases_self_reviewed','test_cases_confirmed','planning_self_reviewed','execution_plan_confirmed']:
            c[flag]=False
    s['updated_at']=now(); write(state_path,s); return s

def confirm_artifact(state_path,kind):
    s=read(state_path); item=s.get('artifacts',{}).get(kind)
    if not isinstance(item,dict): fail(f'artifacts.{kind}','record the self-reviewed artifact first')
    _require_artifact(s,kind,False); item['confirmation_status']='confirmed'; item['confirmed_at']=now()
    mapping={'business_understanding':'business_understanding_confirmed','test_points':'test_points_confirmed','test_cases':'test_cases_confirmed','execution_plan':'execution_plan_confirmed'}
    if kind in mapping: s.setdefault('confirmations',{})[mapping[kind]]=True
    s['updated_at']=now(); write(state_path,s); return s

def record_final_review(state_path,review_path):
    s=read(state_path); root=_run_root(state_path); p=Path(review_path)
    p=(root/p).resolve() if not p.is_absolute() else p.resolve()
    if not p.exists() or not p.is_file(): fail('final_review_ref','review file does not exist or is not a file')
    v=read(p)
    if v.get('ok') is not True or v.get('validator')!='test-result-review/scripts/final_review.py' or not isinstance(v.get('final_assessment'),dict): fail('final_review_ref','review file must be output from validated final review')
    source=Path(v.get('validated_input',''))
    if not source.is_absolute(): source=(root/source).resolve()
    try: source.relative_to(root)
    except ValueError: fail('final_review_ref','validated input must be inside the Run directory')
    if not source.exists() or not source.is_file() or _digest(source)!=v.get('validated_input_sha256'): fail('final_review_ref','validated input is missing or changed')
    try: rel=p.relative_to(root)
    except ValueError: fail('final_review_ref','review must be inside the Run directory')
    s['final_review_ref']=str(rel); s['final_review_absolute_path']=str(p); s['final_review_sha256']=_digest(p); s['final_review_status']='passed'; s['updated_at']=now(); write(state_path,s); return s

def transition(path,stage,next_type,batch=None,case=None,return_reason=None):
    if stage not in STAGES: fail('stage',f'unsupported {stage}')
    s=read(path); source=s.get('current_stage')
    if stage not in LEGAL.get(source,set()): fail('transition',f'illegal {source} -> {stage}')
    if (source,stage) in BACKWARD and not return_reason: fail('return_reason',f'required for backward transition {source}->{stage}')
    _check_prereq(s,source,stage)
    s.update(current_stage=stage,current_batch=batch,current_case=case,last_event={'type':'stage_transition','from':source,'to':stage,'at':now()},current_action={'type':next_type},next_action={'type':next_type},updated_at=now())
    if return_reason: s['return_reason']=return_reason
    if stage=='data-readiness': s['current_batch_data_ready']=False
    write(path,s); return s

def main():
    a=argparse.ArgumentParser(); sp=a.add_subparsers(dest='cmd',required=True)
    p=sp.add_parser('init'); p.add_argument('--run-dir',required=True); p.add_argument('--run-id',required=True)
    p=sp.add_parser('transition'); p.add_argument('--state',required=True); p.add_argument('--stage',required=True); p.add_argument('--next',required=True); p.add_argument('--batch'); p.add_argument('--case'); p.add_argument('--return-reason')
    p=sp.add_parser('set-flag'); p.add_argument('--state',required=True); p.add_argument('--key',required=True); p.add_argument('--value',choices=['true','false'],default='true')
    p=sp.add_parser('set-final-review'); p.add_argument('--state',required=True); p.add_argument('--status',choices=['passed','not_ready'],required=True)
    p=sp.add_parser('record-artifact'); p.add_argument('--state',required=True); p.add_argument('--kind',required=True); p.add_argument('--path',required=True); p.add_argument('--self-review',default='passed'); p.add_argument('--confirmation',choices=['confirmed','pending'])
    p=sp.add_parser('confirm-artifact'); p.add_argument('--state',required=True); p.add_argument('--kind',required=True)
    p=sp.add_parser('record-final-review'); p.add_argument('--state',required=True); p.add_argument('--review',required=True)
    p=sp.add_parser('show'); p.add_argument('--state',required=True)
    x=a.parse_args()
    if x.cmd=='init': v=init(x.run_dir,x.run_id)
    elif x.cmd=='transition': v=transition(x.state,x.stage,x.next,x.batch,x.case,x.return_reason)
    elif x.cmd=='set-flag': v=set_flag(x.state,x.key,x.value=='true')
    elif x.cmd=='set-final-review': v=set_final_review(x.state,x.status)
    elif x.cmd=='record-artifact': v=record_artifact(x.state,x.kind,x.path,x.self_review,x.confirmation)
    elif x.cmd=='confirm-artifact': v=confirm_artifact(x.state,x.kind)
    elif x.cmd=='record-final-review': v=record_final_review(x.state,x.review)
    else: v=read(x.state)
    print(json.dumps(v,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
