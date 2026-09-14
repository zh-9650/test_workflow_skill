from copy import deepcopy
import importlib.util
import sys
from pathlib import Path
SCRIPT_DIR=str(Path(__file__).resolve().parent)
if SCRIPT_DIR not in sys.path: sys.path.insert(0,SCRIPT_DIR)
from batch_task_builder import build as build_task
from retest_task import build as build_retest
from worker_review import validate as validate_worker_review
from reviewer_contract import validate as validate_reviewer
from execution_control import validate as validate_case_result

STATES={'pending','running','self_review','reviewing','needs_rework','completed','blocked','return_upstream','retest_running','retest_self_review','retest_reviewing'}

def fail(path,msg): raise AssertionError(f'{path}: {msg}')

def _validate_manifest_runtime(data_manifest):
    p=Path(__file__).resolve().parents[2]/'test-data-readiness/scripts/data_manifest.py'
    spec=importlib.util.spec_from_file_location('runtime_data_manifest_contract',p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    v=deepcopy(data_manifest); out=m.validate(v); return out, v

def _validate_execution_plan_runtime(plan):
    p=Path(__file__).resolve().parents[2]/'test-execution-planning/scripts/execution_plan.py'
    spec=importlib.util.spec_from_file_location('runtime_execution_plan_contract',p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m.validate(deepcopy(plan))

def _sync_event_files(base,event):
    state=Path(base)/'internal/state/run-status.json'; dashboard=Path(base)/'dashboard/dashboard-data.json'
    if state.exists() and dashboard.exists():
        p=Path(__file__).resolve().parent/'dashboard_update.py'
        spec=importlib.util.spec_from_file_location('runtime_dashboard_update',p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        m.apply_event_files(state,dashboard,event)

def _ensure_dashboard(base,plan):
    state=Path(base)/'internal/state/run-status.json'; dashboard=Path(base)/'dashboard/dashboard-data.json'
    dashboard.parent.mkdir(parents=True,exist_ok=True)
    p=Path(__file__).resolve().parent/'dashboard_update.py'
    spec=importlib.util.spec_from_file_location('runtime_dashboard_update_init',p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    m.initialize_runtime_files(state,dashboard,plan)
    shell=Path(__file__).resolve().parent/'dashboard.py'
    spec=importlib.util.spec_from_file_location('runtime_dashboard_shell',shell); shell_mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(shell_mod)
    index=Path(base)/'dashboard/index.html'
    if not index.exists(): shell_mod.write_dashboard(index)

def _sync_case_events(base,batch_id,results):
    for r in results:
        cid=r['case_id']; _sync_event_files(base,{'type':'case_started','batch_id':batch_id,'case_id':cid,'worker_id':'ExecutionWorker'})
        _sync_event_files(base,{'type':'case_finished','batch_id':batch_id,'case_id':cid,'status':r.get('status'),'actual_execution':r.get('actual_execution'),'blocked_reason_type':r.get('blocked_reason_type')})

def batch_precheck(plan,batch_id,data_manifest,execution_context):
    batches={b['id']:b for b in plan.get('batches',[])}
    if batch_id not in batches: return {'status':'return_to_planning','reason':f'unknown batch {batch_id}'}
    if not execution_context or execution_context.get('environment_ready') is not True:
        return {'status':'blocked','reason':'execution environment/account/tools not ready'}
    if data_manifest.get('batch_id') != batch_id:
        return {'status':'return_to_data','reason':'data manifest belongs to another batch'}
    try:
        readiness,_normalized=_validate_manifest_runtime(data_manifest)
    except AssertionError as e:
        return {'status':'return_to_data','reason':str(e)}
    if readiness.get('readiness',{}).get('ready') is not True:
        return {'status':'return_to_data','reason':readiness.get('readiness',{}).get('reason') or 'batch data not ready'}
    return {'status':'ready','reason':'precheck passed'}

def _index_results(results,path='worker_results'):
    if not isinstance(results,list): fail(path,'list required')
    ids=[r.get('case_id') for r in results]
    if any(x in (None,'') for x in ids): fail(path,'every result requires case_id')
    if len(ids)!=len(set(ids)):
        dup=next(x for x in ids if ids.count(x)>1); fail(path,f'duplicate result for case_id={dup}')
    return {r['case_id']:r for r in results}

def _dependency_status(dep,local_actual,dependency_context):
    if dep in local_actual: return local_actual[dep].get('status')
    ctx=dependency_context.get(dep)
    if not ctx: fail(f'dependency_context.{dep}','cross-batch dependency context missing')
    return ctx.get('final_result') or ctx.get('status')

def _validate_dependencies(planned_case,actual,dependency_context):
    cid=planned_case['case_id']; bad=[]
    for dep in planned_case.get('dependencies',[]) or []:
        st=_dependency_status(dep,actual,dependency_context)
        if st not in {'PASS','PASS_AFTER_FIX'}: bad.append(dep)
    if bad:
        r=actual[cid]
        if r.get('status')!='BLOCKED' or r.get('blocked_reason_type')!='upstream_case':
            fail(f'{cid}.status',f'depends on unresolved upstream {bad}; must be BLOCKED(upstream_case)')
        affected=r.get('affected_by')
        vals=set(affected if isinstance(affected,list) else str(affected or '').split(','))
        if not set(bad).intersection(vals): fail(f'{cid}.affected_by',f'must identify unresolved dependency {bad}')

def _validate_result_set(task,results,path='worker_results',evidence_base=None):
    planned={c['case_id']:c for c in task['cases']}; actual=_index_results(results,path)
    if set(planned) != set(actual):
        missing=sorted(set(planned)-set(actual)); extra=sorted(set(actual)-set(planned))
        fail(path,f'result case set must equal task case set; missing={missing}, extra={extra}')
    for cid in task['case_order']:
        validate_case_result(planned[cid],actual[cid],evidence_base)
        _validate_dependencies(planned[cid],actual,task.get('dependency_context',{}))
    return [deepcopy(actual[cid]) for cid in task['case_order']]

class RuntimeOrchestrator:
    def __init__(self,plan,batch_id,data_manifest,execution_context,case_result_ledger=None):
        self.plan=plan; self.batch_id=batch_id; self.data_manifest=data_manifest; self.execution_context=execution_context; self.case_result_ledger=case_result_ledger or {}
        self.precheck=batch_precheck(plan,batch_id,data_manifest,execution_context)
        self.task=None; self.case_results=[]; self.worker_self_review=None; self.reviewer=None; self.active_retest_task=None
        self.status='pending' if self.precheck['status']=='ready' else ('blocked' if self.precheck['status']=='blocked' else 'return_upstream'); self.retest_count=0
    def create_task(self):
        if self.precheck['status']!='ready': fail('precheck',f'cannot create task: {self.precheck}')
        self.task=build_task(self.plan,self.batch_id,'internal/execution/execution-context.yaml',f'internal/data/manifests/{self.batch_id}-data-manifest.json',case_result_ledger=self.case_result_ledger)
        return deepcopy(self.task)
    def start_worker(self):
        if self.task is None: self.create_task()
        self.status='running'; self.task['status']='running'; return self.status
    def submit_worker_results(self,results):
        if self.status!='running': fail('status','worker results only accepted while running')
        self.case_results=_validate_result_set(self.task,results); self.status='self_review'; return self.status
    def submit_worker_self_review(self,review):
        if self.status!='self_review': fail('status','self review only accepted after worker results')
        validate_worker_review(review,self.task['case_order'],self.case_results)
        self.worker_self_review=deepcopy(review); self.status='reviewing'; return self.status
    def submit_reviewer(self,review):
        if self.status!='reviewing': fail('status','reviewer only accepted after passed worker self-review')
        validate_reviewer(review,self.task['case_order'],self.case_results); self.reviewer=deepcopy(review)
        if review['status']=='passed': self.status='completed'; return {'status':'completed'}
        if review['status']=='rework_required':
            self.status='needs_rework'; self.retest_count+=1; self.active_retest_task=build_retest(self.task,review['retest_case_ids'],self.retest_count,self.case_results)
            return {'status':'needs_rework','retest_task':deepcopy(self.active_retest_task)}
        self.status='return_upstream'; return {'status':'return_upstream','return_stage':review['return_stage'],'findings':review['findings']}
    def apply_retest(self,retest_results,worker_review,reviewer_review):
        if self.status!='needs_rework' or not self.active_retest_task: fail('status','no retest requested')
        validated=_validate_result_set(self.active_retest_task,retest_results,'retest_results')
        ids=self.active_retest_task['case_order']; validate_worker_review(worker_review,ids,validated); validate_reviewer(reviewer_review,ids,validated)
        if reviewer_review['status']!='passed': fail('reviewer.status','retest reviewer must pass to close rework')
        by={r['case_id']:r for r in self.case_results}
        history=[]
        for r in validated:
            old=deepcopy(by.get(r['case_id'])); by[r['case_id']]=deepcopy(r); history.append({'case_id':r['case_id'],'previous':old,'retest':deepcopy(r)})
        self.case_results=[by[cid] for cid in self.task['case_order']]
        self.worker_self_review=deepcopy(worker_review); self.reviewer=deepcopy(reviewer_review); self.status='completed'
        return {'status':'completed','retest_history':history}
    def snapshot(self):
        return {'batch_id':self.batch_id,'status':self.status,'precheck':deepcopy(self.precheck),'case_ids':self.task['case_order'] if self.task else [],'case_results':deepcopy(self.case_results),'worker_self_review':deepcopy(self.worker_self_review),'reviewer':deepcopy(self.reviewer),'dependency_context':deepcopy((self.task or {}).get('dependency_context',{}))}

def build_defect_candidates(batch_snapshot):
    if batch_snapshot.get('reviewer',{}).get('status') != 'passed': return []
    out=[]
    for r in batch_snapshot.get('case_results',[]):
        if r.get('status')=='FAIL' and r.get('reason_type')=='product_issue':
            out.append({'source_batch':batch_snapshot.get('batch_id'),'source_case':r.get('case_id'),'expected':r.get('expected'),'actual':r.get('actual'),'evidence_refs':r.get('evidence_refs',[]),'reviewer_confirmed':True})
    return out

# ---- File-backed orchestration API ----
import argparse as _argparse, json as _json, os as _os
from pathlib import Path as _Path

def _read_json(path): return _json.loads(_Path(path).read_text(encoding='utf-8'))
def _write_json(path,value):
    p=_Path(path); p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix(p.suffix+'.tmp'); t.write_text(_json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); _os.replace(t,p)
CASE_LEDGER_REL='internal/execution/results/case-results-ledger.json'

def _ledger_path(base): return _Path(base)/CASE_LEDGER_REL

def _ensure_case_ledger(base,plan):
    path=_ledger_path(base)
    ledger=_read_json(path) if path.exists() else {'cases':{},'updated_at':None}
    rows=ledger.setdefault('cases',{})
    for c in plan.get('cases',[]):
        cid=c['case_id']
        rows.setdefault(cid,{'case_id':cid,'batch_id':c.get('batch_id'),'status':'PENDING','final_result':None,'reviewer_confirmed':False,'updated_at':None})
    _write_json(path,ledger)
    return ledger

def _ledger_final_results(ledger):
    out={}
    for cid,item in ledger.get('cases',{}).items():
        st=item.get('final_result') or item.get('status')
        if item.get('reviewer_confirmed') is True and st in {'PASS','FAIL','BLOCKED','PASS_AFTER_FIX'}:
            out[cid]=item
    return out

def _commit_results_to_ledger(base,task,results,source='batch_review'):
    path=_ledger_path(base)
    if not path.exists(): fail('case_result_ledger','ledger must be initialized before committing results')
    ledger=_read_json(path); rows=ledger.setdefault('cases',{})
    planned={c['case_id']:c for c in task.get('cases',[])}
    for r in results:
        cid=r['case_id']; st=r.get('final_result') or r.get('status')
        if st not in {'PASS','FAIL','BLOCKED','PASS_AFTER_FIX'}: fail(f'case_result_ledger.{cid}.status',f'cannot commit non-final status {st}')
        current=rows.setdefault(cid,{'case_id':cid,'batch_id':planned.get(cid,{}).get('batch_id') or task.get('batch_id')})
        current.update({'case_id':cid,'batch_id':planned.get(cid,{}).get('batch_id') or task.get('batch_id'),'status':r.get('status'),'final_result':st,'reviewer_confirmed':True,'source':source,'updated_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()})
    ledger['updated_at']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(); _write_json(path,ledger); return ledger

def prepare_run_files(plan_path,batch_id,manifest_path,context_path,run_dir):
    plan=_read_json(plan_path); manifest=_read_json(manifest_path); context=_read_json(context_path); base=_Path(run_dir)
    _validate_execution_plan_runtime(plan)
    _ensure_dashboard(base,plan)
    ledger=_ensure_case_ledger(base,plan); final_results=_ledger_final_results(ledger)
    pre=batch_precheck(plan,batch_id,manifest,context); state_path=base/f'internal/execution/runtime-state/{batch_id}-state.json'
    state={'batch_id':batch_id,'status':'pending' if pre['status']=='ready' else ('blocked' if pre['status']=='blocked' else 'return_upstream'),'precheck':pre,'task_ref':None,'worker_results_ref':None,'worker_self_review':None,'reviewer':None,'retest_tasks':[],'active_retest':None,'case_result_ledger_ref':CASE_LEDGER_REL}
    if pre['status']=='ready':
        task=build_task(plan,batch_id,'internal/execution/execution-context.yaml',f'internal/data/manifests/{batch_id}-data-manifest.json',case_result_ledger=final_results)
        task_path=base/f'internal/execution/tasks/{batch_id}-task.json'; _write_json(task_path,task); state['task_ref']=str(task_path.relative_to(base))
    _write_json(state_path,state); return state

def accept_worker_results_files(run_dir,batch_id,results_path):
    base=_Path(run_dir); state_path=base/f'internal/execution/runtime-state/{batch_id}-state.json'; state=_read_json(state_path)
    if state.get('status') not in {'pending','running'}: fail('status',f'cannot accept worker results while {state.get("status")}')
    task=_read_json(base/state['task_ref']); results=_read_json(results_path); validated=_validate_result_set(task,results,evidence_base=base)
    out=base/f'internal/execution/results/{batch_id}-worker-results.json'; _write_json(out,validated)
    state.update(status='self_review',worker_results_ref=str(out.relative_to(base))); _write_json(state_path,state); _sync_case_events(base,batch_id,validated); return state

def accept_self_review_files(run_dir,batch_id,review_path):
    base=_Path(run_dir); state_path=base/f'internal/execution/runtime-state/{batch_id}-state.json'; state=_read_json(state_path)
    if state.get('status')!='self_review': fail('status','self review only after worker results')
    task=_read_json(base/state['task_ref']); results=_read_json(base/state['worker_results_ref']); review=_read_json(review_path); validate_worker_review(review,task['case_order'],results)
    state.update(status='reviewing',worker_self_review=review); _write_json(state_path,state); _sync_event_files(base,{'type':'review_started','batch_id':batch_id,'reviewer_id':'ResultReviewer'}); return state

def accept_reviewer_files(run_dir,batch_id,review_path):
    base=_Path(run_dir); state_path=base/f'internal/execution/runtime-state/{batch_id}-state.json'; state=_read_json(state_path)
    if state.get('status')!='reviewing': fail('status','reviewer only after passed worker self-review')
    task=_read_json(base/state['task_ref']); results=_read_json(base/state['worker_results_ref']); review=_read_json(review_path); validate_reviewer(review,task['case_order'],results); state['reviewer']=review; retest_ref=None
    if review['status']=='passed':
        state['status']='completed'; _commit_results_to_ledger(base,task,results,'batch_reviewer_passed')
    elif review['status']=='return_upstream': state['status']='return_upstream'; state['return_stage']=review['return_stage']
    else:
        state['status']='needs_rework'; seq=len(state.get('retest_tasks',[]))+1; retest=build_retest(task,review['retest_case_ids'],seq,_read_json(base/state['worker_results_ref']))
        rp=base/f'internal/execution/tasks/{batch_id}-retest-{seq:03d}.json'; _write_json(rp,retest); retest_ref=str(rp.relative_to(base)); state.setdefault('retest_tasks',[]).append(retest_ref); state['active_retest']={'task_ref':retest_ref,'sequence':seq,'results_ref':None,'self_review':None,'reviewer':None}
    _write_json(state_path,state); _sync_event_files(base,{'type':'review_finished','batch_id':batch_id,'status':review.get('status'),'reviewer_id':'ResultReviewer','retest_case_ids':review.get('retest_case_ids',[])}); return {'state':state,'retest_task_ref':retest_ref}

def accept_retest_results_files(run_dir,batch_id,results_path):
    base=_Path(run_dir); sp=base/f'internal/execution/runtime-state/{batch_id}-state.json'; state=_read_json(sp)
    if state.get('status')!='needs_rework' or not state.get('active_retest'): fail('status','no active retest')
    task=_read_json(base/state['active_retest']['task_ref']); results=_read_json(results_path); validated=_validate_result_set(task,results,'retest_results',base)
    seq=state['active_retest']['sequence']; out=base/f'internal/execution/results/{batch_id}-retest-{seq:03d}-results.json'; _write_json(out,validated)
    state['active_retest']['results_ref']=str(out.relative_to(base)); state['status']='retest_self_review'; _write_json(sp,state); _sync_case_events(base,batch_id,validated); return state

def accept_retest_self_review_files(run_dir,batch_id,review_path):
    base=_Path(run_dir); sp=base/f'internal/execution/runtime-state/{batch_id}-state.json'; state=_read_json(sp)
    if state.get('status')!='retest_self_review': fail('status','retest self review only after retest results')
    ar=state['active_retest']; task=_read_json(base/ar['task_ref']); results=_read_json(base/ar['results_ref']); review=_read_json(review_path); validate_worker_review(review,task['case_order'],results)
    ar['self_review']=review; state['status']='retest_reviewing'; _write_json(sp,state); _sync_event_files(base,{'type':'review_started','batch_id':batch_id,'reviewer_id':'RetestReviewer'}); return state

def accept_retest_reviewer_files(run_dir,batch_id,review_path):
    base=_Path(run_dir); sp=base/f'internal/execution/runtime-state/{batch_id}-state.json'; state=_read_json(sp)
    if state.get('status')!='retest_reviewing': fail('status','retest reviewer only after passed retest self-review')
    ar=state['active_retest']; task=_read_json(base/ar['task_ref']); retest_results=_read_json(base/ar['results_ref']); review=_read_json(review_path); validate_reviewer(review,task['case_order'],retest_results); ar['reviewer']=review
    if review['status']=='passed':
        original=_read_json(base/state['worker_results_ref']); by={r['case_id']:r for r in original}; retest=_read_json(base/ar['results_ref'])
        for r in retest: by[r['case_id']]=r
        task0=_read_json(base/state['task_ref']); merged=[by[c] for c in task0['case_order']]; _write_json(base/state['worker_results_ref'],merged)
        state['worker_self_review']=ar['self_review']; state['reviewer']=review; state['status']='completed'; state['active_retest']=None
        _commit_results_to_ledger(base,task0,merged,'retest_reviewer_passed')
    elif review['status']=='return_upstream': state['status']='return_upstream'; state['return_stage']=review['return_stage']
    else:
        seq=len(state.get('retest_tasks',[]))+1; rt=build_retest(_read_json(base/state['task_ref']),review['retest_case_ids'],seq,_read_json(base/state['worker_results_ref'])); rp=base/f'internal/execution/tasks/{batch_id}-retest-{seq:03d}.json'; _write_json(rp,rt); state['retest_tasks'].append(str(rp.relative_to(base))); state['active_retest']={'task_ref':str(rp.relative_to(base)),'sequence':seq,'results_ref':None,'self_review':None,'reviewer':None}; state['status']='needs_rework'
    _write_json(sp,state); _sync_event_files(base,{'type':'review_finished','batch_id':batch_id,'status':'passed' if state.get('status')=='completed' else review.get('status'),'reviewer_id':'RetestReviewer','retest_case_ids':review.get('retest_case_ids',[])}); return state

def _cli():
    a=_argparse.ArgumentParser(); sp=a.add_subparsers(dest='cmd',required=True)
    p=sp.add_parser('prepare'); p.add_argument('--plan',required=True); p.add_argument('--batch',required=True); p.add_argument('--manifest',required=True); p.add_argument('--context',required=True); p.add_argument('--run-dir',required=True)
    for name in ['worker-results','self-review','reviewer','retest-results','retest-self-review','retest-reviewer']:
        p=sp.add_parser(name); p.add_argument('--run-dir',required=True); p.add_argument('--batch',required=True); p.add_argument('--input' if name.startswith('retest') else ('--results' if name=='worker-results' else '--review'),required=True)
    x=a.parse_args()
    if x.cmd=='prepare': out=prepare_run_files(x.plan,x.batch,x.manifest,x.context,x.run_dir)
    elif x.cmd=='worker-results': out=accept_worker_results_files(x.run_dir,x.batch,x.results)
    elif x.cmd=='self-review': out=accept_self_review_files(x.run_dir,x.batch,x.review)
    elif x.cmd=='reviewer': out=accept_reviewer_files(x.run_dir,x.batch,x.review)
    elif x.cmd=='retest-results': out=accept_retest_results_files(x.run_dir,x.batch,x.input)
    elif x.cmd=='retest-self-review': out=accept_retest_self_review_files(x.run_dir,x.batch,x.input)
    else: out=accept_retest_reviewer_files(x.run_dir,x.batch,x.input)
    print(_json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__': _cli()
