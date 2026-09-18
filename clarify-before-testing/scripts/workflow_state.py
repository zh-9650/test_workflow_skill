from __future__ import annotations
import argparse, hashlib, importlib.util, json, os
from pathlib import Path
from datetime import datetime, timezone

SCHEMA_VERSION=3
STAGES=['business-modeling','case-design','execution-planning','data-readiness','execution-runtime','defect-handling','result-review','closed']
LEGAL={
 'business-modeling':{'case-design'},
 'case-design':{'business-modeling','execution-planning'},
 'execution-planning':{'data-readiness'},
 'data-readiness':{'execution-runtime'},
 'execution-runtime':{'defect-handling','result-review','data-readiness','execution-planning','case-design'},
 'defect-handling':{'execution-runtime','data-readiness','result-review'},
 'result-review':{'closed'}, 'closed':set(),
}
BACKWARD={('case-design','business-modeling'),('execution-runtime','data-readiness'),('execution-runtime','execution-planning'),('execution-runtime','case-design'),('defect-handling','execution-runtime')}
ARTIFACT_FLAGS={
 'business-understanding':('business_self_review_passed','business_understanding_confirmed'),
 'test-points':('test_points_self_review_passed','test_points_confirmed'),
 'test-cases':('test_cases_self_review_passed','test_cases_confirmed'),
 'execution-plan':('planning_self_review_passed','execution_plan_confirmed'),
}
ARTIFACT_STAGE={'business-understanding':'business-modeling','test-points':'case-design','test-cases':'case-design','execution-plan':'execution-planning'}
DEFAULT_CONTRACT_INPUTS={
 'business-understanding':['internal/business/business-model.json'],
 'test-points':['internal/design/test-points.json'],
 'test-cases':['internal/design/test-cases.json'],
 'execution-plan':['internal/execution/execution-plan.json'],
}
DOWNSTREAM={
 'business-understanding':['business-understanding','test-points','test-cases','execution-plan'],
 'test-points':['test-points','test-cases','execution-plan'],
 'test-cases':['test-cases','execution-plan'],
 'execution-plan':['execution-plan'],
}

def now(): return datetime.now(timezone.utc).isoformat()
def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,v):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix(p.suffix+'.tmp'); t.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); os.replace(t,p)
def fail(path,msg): raise AssertionError(f'{path}: {msg}')
def sha256(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _run_dir_from_state(state_path): return Path(state_path).resolve().parents[2]

def _load_module(path,name):
    spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def init(run_dir,run_id):
    r=Path(run_dir)
    for x in ['deliverables','dashboard','internal/state','internal/business','internal/design','internal/execution','internal/data','internal/defects','scripts/data','scripts/ui','scripts/api','scripts/temp','evidence','logs','downloads','scratch']:
        (r/x).mkdir(parents=True,exist_ok=True)
    s={'schema_version':SCHEMA_VERSION,'run_id':run_id,'current_stage':'business-modeling','current_batch':None,'current_case':None,'current_worker':None,'current_reviewer':None,
       'last_event':None,'current_action':{'type':'build_business_understanding'},'next_action':{'type':'build_business_understanding'},
       'batch_status':{},'open_defects':[],'blocked_items':[],'pending_user_inputs':[],'artifacts':{},'confirmation_bindings':{},
       'confirmations':{'business_self_review_passed':False,'business_understanding_confirmed':False,'test_points_self_review_passed':False,'test_points_confirmed':False,'test_cases_self_review_passed':False,'test_cases_confirmed':False,'planning_self_review_passed':False,'execution_plan_confirmed':False},
       'current_batch_data_ready':False,'batch_data_status':{},'batch_data_bindings':{},'pending_resume':None,
       'final_review_status':None,'final_review_source':None,'current_design_subphase':None,'updated_at':now()}
    write(r/'internal/state/run-status.json',s); return s

def discover(root):
    root=Path(root); rows=[]
    if not root.exists(): return {'status':'none','runs':[]}
    for state_path in sorted(root.glob('*/internal/state/run-status.json')):
        try: s=read(state_path)
        except Exception: continue
        rows.append({'run_id':s.get('run_id'),'stage':s.get('current_stage'),'updated_at':s.get('updated_at'),'state_path':str(state_path),'run_dir':str(state_path.parents[2])})
    active=[r for r in rows if r['stage']!='closed']
    if len(active)==1: return {'status':'selected','run':active[0],'runs':rows}
    if not active: return {'status':'none_active','runs':rows}
    return {'status':'ambiguous','candidates':sorted(active,key=lambda x:x.get('updated_at') or '',reverse=True),'runs':rows}

def set_flag(path,key,value=True):
    fail('set_flag','review, confirmation, and data-readiness flags cannot be set directly; use the artifact or Batch-data binding commands')

def _resolve_contract_input(state_path,kind,explicit=None):
    if explicit:
        p=Path(explicit)
        if not p.exists(): fail('artifact.contract_input',f'file not found: {explicit}')
        return p.resolve()
    run=_run_dir_from_state(state_path)
    for rel in DEFAULT_CONTRACT_INPUTS.get(kind,[]):
        p=run/rel
        if p.exists(): return p.resolve()
    fail('artifact.contract_input',f'no internal contract input found for {kind}; pass --contract-input explicitly')

def _confirmed_cases_binding(s):
    b=s.get('confirmation_bindings',{}).get('test-cases')
    if not b: fail('execution-plan.confirmed_cases','test-cases must be confirmed before planning self-review')
    cp=Path(b.get('contract_path',''))
    if not cp.exists() or sha256(cp)!=b.get('contract_sha256'): fail('execution-plan.confirmed_cases','confirmed test-case contract input changed or disappeared')
    return cp,b

def _confirmed_plan_binding(s):
    b=s.get('confirmation_bindings',{}).get('execution-plan')
    if not b: fail('execution-plan','execution plan must be confirmed before Batch data can be bound')
    cp=Path(b.get('contract_path',''))
    if not cp.exists() or sha256(cp)!=b.get('contract_sha256'):
        fail('execution-plan','confirmed execution plan changed or disappeared')
    return cp,b

def _inside(path,root):
    try: path.resolve().relative_to(root.resolve()); return True
    except ValueError: return False

def set_batch_data_ready(state_path,batch_id,manifest_path):
    s=read(state_path)
    if s.get('current_stage')!='data-readiness': fail('batch_data.stage','Batch data can only be bound during data-readiness')
    if not batch_id: fail('batch_data.batch_id','required')
    if s.get('current_batch') not in (None,batch_id): fail('batch_data.batch_id',f'current Batch is {s.get("current_batch")}, not {batch_id}')
    run=_run_dir_from_state(state_path); mp=Path(manifest_path).resolve(); allowed=run/'internal/data/manifests'
    if not _inside(mp,allowed): fail('batch_data.manifest',f'manifest must be stored under {allowed}')
    if not mp.exists() or not mp.is_file(): fail('batch_data.manifest',f'file not found: {manifest_path}')
    plan_path,plan_binding=_confirmed_plan_binding(s); plan=read(plan_path); manifest=read(mp)
    if manifest.get('batch_id')!=batch_id: fail('batch_data.batch_id','manifest batch_id does not match the requested Batch')
    root=Path(__file__).resolve().parents[2]
    m=_load_module(root/'test-data-readiness/scripts/data_manifest.py','batch_data_manifest_bound')
    validation=m.validate(manifest,plan)
    rec={'batch_id':batch_id,'manifest_path':str(mp),'manifest_sha256':sha256(mp),
         'plan_path':str(plan_path),'plan_sha256':plan_binding['contract_sha256'],
         'validated_at':now(),'validation':validation}
    s.setdefault('batch_data_bindings',{})[batch_id]=rec
    s.setdefault('batch_data_status',{})[batch_id]='ready'
    s['current_batch']=batch_id; s['current_batch_data_ready']=True
    resume=s.get('pending_resume') if isinstance(s.get('pending_resume'),dict) and s['pending_resume'].get('batch_id')==batch_id else None
    s['last_event']={'type':'batch_data_ready','batch_id':batch_id,'at':now()}
    s['current_action']={'type':'batch_data_ready','batch_id':batch_id}
    s['next_action']=({'type':'resume_blocked_cases','batch_id':batch_id,'case_ids':resume.get('case_ids',[]),'bug_ref':resume.get('bug_ref')} if resume else {'type':'execute_batch','batch_id':batch_id})
    s['updated_at']=now(); write(state_path,s); return s

def _validate_contract(state_path,kind,contract_input,for_confirmation=False):
    root=Path(__file__).resolve().parents[2]
    data=read(contract_input)
    if kind=='business-understanding':
        m=_load_module(root/'test-business-modeling/scripts/business_contract.py','business_contract_bound')
        out=m.validate(data,require_confirmed=for_confirmation)
    elif kind=='test-points':
        s=read(state_path)
        bb=s.get('confirmation_bindings',{}).get('business-understanding')
        if not bb: fail('test-points.confirmed_business','business understanding must be confirmed before Test Point self-review')
        bp=Path(bb.get('contract_path',''))
        if not bp.exists() or sha256(bp)!=bb.get('contract_sha256'):
            fail('test-points.confirmed_business','confirmed business model changed or disappeared')
        confirmed_business=read(bp)
        m=_load_module(root/'test-point-design/scripts/test_point_contract.py','test_point_contract_bound')
        out=m.validate(data,confirmed_business,require_confirmed=for_confirmation)
    elif kind=='test-cases':
        s=read(state_path)
        pb=s.get('confirmation_bindings',{}).get('test-points')
        bb=s.get('confirmation_bindings',{}).get('business-understanding')
        if not pb: fail('test-cases.confirmed_points','test points must be confirmed before Case self-review')
        if not bb: fail('test-cases.confirmed_business','business understanding must be confirmed before Case self-review')
        pp=Path(pb.get('contract_path','')); bp=Path(bb.get('contract_path',''))
        if not pp.exists() or sha256(pp)!=pb.get('contract_sha256'):
            fail('test-cases.confirmed_points','confirmed test-point contract input changed or disappeared')
        if not bp.exists() or sha256(bp)!=bb.get('contract_sha256'):
            fail('test-cases.confirmed_business','confirmed business model changed or disappeared')
        confirmed_points=read(pp); confirmed_business=read(bp)
        m=_load_module(root/'test-case-design/scripts/case_contract.py','case_contract_bound')
        out=m.validate(data,confirmed_points,confirmed_business,require_confirmed=for_confirmation)
    elif kind=='execution-plan':
        s=read(state_path); confirmed_path,binding=_confirmed_cases_binding(s); confirmed=read(confirmed_path)
        m=_load_module(root/'test-execution-planning/scripts/execution_plan.py','execution_plan_contract_bound')
        out=m.validate(data,require_confirmed=False,confirmed_cases=confirmed,confirmed_cases_sha256=binding['contract_sha256'])
    else:
        fail('artifact.kind',f'unsupported contract-bound artifact {kind}')
    return out

def _clear_artifact_flags(s,kind):
    for k in DOWNSTREAM.get(kind,[kind]):
        if k in ARTIFACT_FLAGS:
            sf,cf=ARTIFACT_FLAGS[k]
            s['confirmations'][sf]=False; s['confirmations'][cf]=False
            s.get('confirmation_bindings',{}).pop(k,None)
    s['final_review_status']=None; s['final_review_source']=None
    s.get('artifacts',{}).pop('final-review',None)
    if 'execution-plan' in DOWNSTREAM.get(kind,[kind]):
        s['current_batch_data_ready']=False
        s['batch_data_status']={}
        s['batch_data_bindings']={}
        s['pending_resume']=None

def register_artifact(state_path,kind,artifact_path,self_review_status=None,contract_input=None,review_path=None):
    if kind not in ARTIFACT_FLAGS: fail('artifact.kind',f'unsupported {kind}')
    ap=Path(artifact_path).resolve()
    if not ap.exists() or not ap.is_file(): fail('artifact.path',f'file not found: {artifact_path}')
    s=read(state_path)
    if s.get('current_stage')!=ARTIFACT_STAGE[kind]: fail('artifact.stage',f'{kind} can only be registered during {ARTIFACT_STAGE[kind]}')
    # Any newly registered version invalidates this artifact and every downstream confirmation.
    _clear_artifact_flags(s,kind)
    cp=_resolve_contract_input(state_path,kind,contract_input)
    rec={'path':str(ap),'sha256':sha256(ap),'contract_path':str(cp),'contract_sha256':sha256(cp),'registered_at':now(),'self_review_status':self_review_status or 'not_reviewed'}
    if kind in {'business-understanding','test-points','test-cases'}:
        if not review_path:
            fail('artifact.review_path',f'{kind} requires the human-readable review summary file')
        rp=Path(review_path).resolve()
        if not rp.exists() or not rp.is_file():
            fail('artifact.review_path',f'file not found: {review_path}')
        rec['review_path']=str(rp); rec['review_sha256']=sha256(rp)
    if self_review_status=='passed':
        rec['contract_validation']=_validate_contract(state_path,kind,cp,for_confirmation=False)
        rec['ready_for_confirmation']=bool(rec['contract_validation'].get('ready_for_confirmation',True))
        s['confirmations'][ARTIFACT_FLAGS[kind][0]]=True
    s.setdefault('artifacts',{})[kind]=rec
    if kind=='business-understanding':
        s['current_design_subphase']=None
        if self_review_status!='passed': s['next_action']={'type':'revise_business_understanding'}
        elif rec.get('ready_for_confirmation'): s['next_action']={'type':'confirm_business_understanding'}
        else: s['next_action']={'type':'resolve_business_questions','question_ids':rec['contract_validation'].get('pending_blocking_questions',[])}
    elif kind=='test-points':
        s['current_design_subphase']='test-point-design'
        if self_review_status!='passed': s['next_action']={'type':'revise_test_points'}
        elif rec['contract_validation'].get('return_to_business_understanding'):
            s['next_action']={'type':'return_to_business_understanding','reason':'business expected remains undefined'}
        elif rec.get('ready_for_confirmation'): s['next_action']={'type':'confirm_test_points'}
        else: s['next_action']={'type':'resolve_test_point_questions','question_ids':rec['contract_validation'].get('pending_questions',[])}
    elif kind=='test-cases':
        s['current_design_subphase']='test-case-design'
        if self_review_status!='passed': s['next_action']={'type':'revise_test_cases'}
        elif rec['contract_validation'].get('return_to_business_understanding'):
            s['next_action']={'type':'return_to_business_understanding','reason':'business expected remains undefined'}
        elif rec['contract_validation'].get('return_to_test_point_design'):
            s['next_action']={'type':'return_to_test_point_design','reason':'test mechanism is missing'}
        elif rec.get('ready_for_confirmation'): s['next_action']={'type':'confirm_test_cases'}
        else: s['next_action']={'type':'resolve_test_case_questions','question_ids':rec['contract_validation'].get('pending_blocking_questions',[])}
    s['last_event']={'type':'artifact_registered','kind':kind,'at':now()}; s['updated_at']=now(); write(state_path,s); return s

def _assert_record_current(s,kind):
    rec=s.get('artifacts',{}).get(kind)
    if not rec: fail('artifact',f'{kind} is not registered')
    ap=Path(rec.get('path','')); cp=Path(rec.get('contract_path',''))
    if not ap.exists() or sha256(ap)!=rec.get('sha256'): fail(f'artifact.{kind}','deliverable changed or disappeared after registration')
    if not cp.exists() or sha256(cp)!=rec.get('contract_sha256'): fail(f'artifact.{kind}','internal contract input changed or disappeared after self-review')
    if kind in {'business-understanding','test-points','test-cases'}:
        rp=Path(rec.get('review_path',''))
        if not rp.exists() or sha256(rp)!=rec.get('review_sha256'):
            fail(f'artifact.{kind}','human-readable review summary changed or disappeared after registration')
    binding=s.get('confirmation_bindings',{}).get(kind)
    if binding:
        if binding.get('sha256')!=rec.get('sha256') or binding.get('contract_sha256')!=rec.get('contract_sha256'):
            fail(f'confirmation_bindings.{kind}','binding does not match current registered artifact version')
        if kind in {'business-understanding','test-points','test-cases'} and binding.get('review_sha256')!=rec.get('review_sha256'):
            fail(f'confirmation_bindings.{kind}','review summary binding does not match current registered artifact version')
    return rec

def confirm_artifact(state_path,kind,artifact_path,confirmed_scope='current confirmed scope'):
    if kind not in ARTIFACT_FLAGS: fail('artifact.kind',f'unsupported confirmable artifact {kind}')
    s=read(state_path)
    if s.get('current_stage')!=ARTIFACT_STAGE[kind]: fail('artifact.stage',f'{kind} can only be confirmed during {ARTIFACT_STAGE[kind]}')
    rec=_assert_record_current(s,kind)
    ap=Path(artifact_path).resolve()
    if str(ap)!=rec.get('path'): fail('artifact.path','confirmation must target the currently registered artifact path')
    self_flag,confirm_flag=ARTIFACT_FLAGS[kind]
    if rec.get('self_review_status')!='passed' or s.get('confirmations',{}).get(self_flag) is not True:
        fail('confirmation','registered artifact must have passed the required self-review and structure checks before user confirmation')
    # Re-run the stricter final-confirmation validation so unresolved blocking decisions cannot slip through.
    final_validation=_validate_contract(state_path,kind,Path(rec['contract_path']),for_confirmation=True)
    if final_validation.get('ready_for_confirmation') is False:
        fail('confirmation','artifact still has unresolved blocking decisions')
    s['confirmations'][confirm_flag]=True
    binding={'sha256':rec['sha256'],'path':rec['path'],'contract_sha256':rec['contract_sha256'],'contract_path':rec['contract_path'],'confirmed_scope':confirmed_scope,'confirmed_at':now()}
    if kind in {'business-understanding','test-points','test-cases'}:
        binding.update(review_path=rec['review_path'],review_sha256=rec['review_sha256'])
    s.setdefault('confirmation_bindings',{})[kind]=binding
    if kind=='business-understanding':
        s['current_design_subphase']=None
        s['next_action']={'type':'enter_case_design','subphase':'test-point-design'}
    elif kind=='test-points':
        s['current_design_subphase']='test-case-design'
        s['next_action']={'type':'design_test_cases'}
    elif kind=='test-cases':
        s['current_design_subphase']=None
        s['next_action']={'type':'plan_execution'}
    s['last_event']={'type':'artifact_confirmed','kind':kind,'at':now()}; s['updated_at']=now(); write(state_path,s); return s

def _require_current_confirmed(s,kind,msg):
    sf,cf=ARTIFACT_FLAGS[kind]
    if not s.get('confirmations',{}).get(sf) or not s.get('confirmations',{}).get(cf): fail('transition',msg)
    rec=_assert_record_current(s,kind)
    if kind not in s.get('confirmation_bindings',{}): fail('transition',msg)
    return rec

def _check_prereq(s,source,target,target_batch=None):
    if (source,target)==('business-modeling','case-design'):
        _require_current_confirmed(s,'business-understanding','business understanding must be contract-validated, self-reviewed, artifact-bound and user-confirmed')
    elif (source,target)==('case-design','execution-planning'):
        _require_current_confirmed(s,'test-points','test points must be contract-validated, self-reviewed, artifact-bound and confirmed')
        _require_current_confirmed(s,'test-cases','test cases must be contract-validated, self-reviewed, artifact-bound and confirmed')
    elif (source,target)==('execution-planning','data-readiness'):
        _require_current_confirmed(s,'execution-plan','execution plan must be contract-validated, self-reviewed, artifact-bound and confirmed')
    elif (source,target)==('data-readiness','execution-runtime'):
        bid=target_batch or s.get('current_batch')
        binding=s.get('batch_data_bindings',{}).get(bid)
        if not bid or s.get('current_batch_data_ready') is not True or s.get('batch_data_status',{}).get(bid)!='ready' or not binding:
            fail('transition','current Batch data must be contract-validated and bound before Runtime')
        mp=Path(binding.get('manifest_path','')); pp=Path(binding.get('plan_path',''))
        if not mp.exists() or sha256(mp)!=binding.get('manifest_sha256'):
            fail('transition','bound Batch data manifest changed or disappeared')
        plan_path,plan_binding=_confirmed_plan_binding(s)
        if pp.resolve()!=plan_path.resolve() or binding.get('plan_sha256')!=plan_binding.get('contract_sha256'):
            fail('transition','Batch data binding does not match the current confirmed execution plan')
    elif (source,target)==('result-review','closed'):
        if s.get('final_review_status')!='passed' or not s.get('final_review_source'): fail('transition','validated final review artifact must be bound before closing Run')
        src=s['final_review_source']; p=Path(src.get('path',''))
        if not p.exists() or sha256(p)!=src.get('sha256'): fail('transition','final review artifact changed after validation')

def set_final_review_from_file(state_path,review_file):
    rp=Path(review_file).resolve()
    if not rp.exists(): fail('final_review_source',f'file not found: {review_file}')
    data=read(rp)
    contract=Path(__file__).resolve().parents[2]/'test-result-review/scripts/final_review.py'
    m=_load_module(contract,'final_review_contract_bound')
    run_dir=_run_dir_from_state(state_path)
    out=m.validate(data,run_dir=run_dir)
    s=read(state_path); s['final_review_status']='passed'; s['final_review_source']={'path':str(rp),'sha256':sha256(rp),'validated_at':now(),'conclusion':out.get('final_assessment',{}).get('conclusion')}
    s.setdefault('artifacts',{})['final-review']=s['final_review_source']; s['last_event']={'type':'final_review_validated','at':now()}; s['next_action']={'type':'close_run'}; s['updated_at']=now(); write(state_path,s); return s

def _normal_batch_data_transition(s,source,target,batch):
    if source not in {'execution-runtime','defect-handling'} or target!='data-readiness' or not batch: return False
    action=s.get('next_action',{})
    act_type=action.get('type')
    act_bid=action.get('batch_id')
    if act_type in {'prepare_batch_data','prepare_resumed_cases_data'} and (not act_bid or act_bid==batch):
        return True
    b_status=s.get('batch_status',{}).get(batch)
    if b_status in {'pending','needs_rework'}:
        return True
    cur_data_st=s.get('batch_data_status',{}).get(batch)
    if cur_data_st in {None,'unprepared','preparing'} and batch!=s.get('current_batch'):
        return True
    return False

def transition(path,stage,next_type,batch=None,case=None,return_reason=None):
    if stage not in STAGES: fail('stage',f'unsupported {stage}')
    s=read(path); source=s.get('current_stage')
    if stage not in LEGAL.get(source,set()): fail('transition',f'illegal {source} -> {stage}')
    normal_batch_loop=_normal_batch_data_transition(s,source,stage,batch)
    if (source,stage) in BACKWARD and not return_reason and not normal_batch_loop: fail('return_reason',f'required for corrective transition {source}->{stage}')
    _check_prereq(s,source,stage,batch)
    previous_next=dict(s.get('next_action') or {})
    next_act={'type':next_type}
    if batch: next_act['batch_id']=batch
    if case: next_act['case_id']=case
    s.update(current_stage=stage,current_batch=batch,current_case=case,current_worker=None,current_reviewer=None,last_event={'type':'stage_transition','from':source,'to':stage,'at':now()},current_action={'type':next_type},next_action=next_act,updated_at=now())
    if stage=='case-design':
        s['current_design_subphase']='test-case-design' if s.get('confirmations',{}).get('test_points_confirmed') else 'test-point-design'
    elif stage!='case-design':
        s['current_design_subphase']=None
    if return_reason: s['return_reason']=return_reason
    if stage=='data-readiness':
        if batch:
            s.setdefault('batch_data_status',{})[batch]='preparing'
            s['current_batch_data_ready']=(s.get('batch_data_status',{}).get(batch)=='ready')
        else:
            s['current_batch_data_ready']=False
        if previous_next.get('type')=='prepare_resumed_cases_data' and previous_next.get('batch_id')==batch:
            s['pending_resume']={'batch_id':batch,'case_ids':previous_next.get('case_ids',[]),'bug_ref':previous_next.get('bug_ref')}
        else: s['pending_resume']=None
    write(path,s); return s

def main():
    a=argparse.ArgumentParser(); sp=a.add_subparsers(dest='cmd',required=True)
    p=sp.add_parser('init'); p.add_argument('--run-dir',required=True); p.add_argument('--run-id',required=True)
    p=sp.add_parser('discover'); p.add_argument('--root',default='work/test-runs')
    p=sp.add_parser('transition'); p.add_argument('--state',required=True); p.add_argument('--stage',required=True); p.add_argument('--next',required=True); p.add_argument('--batch'); p.add_argument('--case'); p.add_argument('--return-reason')
    p=sp.add_parser('set-flag'); p.add_argument('--state',required=True); p.add_argument('--key',required=True); p.add_argument('--value',choices=['true','false'],default='true')
    p=sp.add_parser('set-batch-data-ready'); p.add_argument('--state',required=True); p.add_argument('--batch',required=True); p.add_argument('--manifest',required=True)
    p=sp.add_parser('register-artifact'); p.add_argument('--state',required=True); p.add_argument('--kind',required=True); p.add_argument('--path',required=True); p.add_argument('--review-path'); p.add_argument('--self-review-status',choices=['passed','failed']); p.add_argument('--contract-input')
    p=sp.add_parser('confirm-artifact'); p.add_argument('--state',required=True); p.add_argument('--kind',required=True); p.add_argument('--path',required=True); p.add_argument('--scope',default='current confirmed scope')
    p=sp.add_parser('set-final-review'); p.add_argument('--state',required=True); p.add_argument('--review-file',required=True)
    p=sp.add_parser('show'); p.add_argument('--state',required=True)
    x=a.parse_args()
    if x.cmd=='init': v=init(x.run_dir,x.run_id)
    elif x.cmd=='discover': v=discover(x.root)
    elif x.cmd=='transition': v=transition(x.state,x.stage,x.next,x.batch,x.case,x.return_reason)
    elif x.cmd=='set-flag': v=set_flag(x.state,x.key,x.value=='true')
    elif x.cmd=='set-batch-data-ready': v=set_batch_data_ready(x.state,x.batch,x.manifest)
    elif x.cmd=='register-artifact': v=register_artifact(x.state,x.kind,x.path,x.self_review_status,x.contract_input,x.review_path)
    elif x.cmd=='confirm-artifact': v=confirm_artifact(x.state,x.kind,x.path,x.scope)
    elif x.cmd=='set-final-review': v=set_final_review_from_file(x.state,x.review_file)
    else: v=read(x.state)
    print(json.dumps(v,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
