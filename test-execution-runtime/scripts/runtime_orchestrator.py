from copy import deepcopy
import importlib.util, hashlib
from pathlib import Path
from batch_task_builder import build as build_task, validate as validate_task, EXECUTION_SCHEMA_VERSION
from retest_task import build as build_retest
from worker_review import validate as validate_worker_review
from reviewer_contract import validate as validate_reviewer
from execution_control import validate as validate_case_result

STATES={'pending','running','self_review','reviewing','needs_rework','completed','blocked','return_upstream','retest_running','retest_self_review','retest_reviewing'}

def fail(path,msg): raise AssertionError(f'{path}: {msg}')

def _load_module(path,name):
    spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def _validate_manifest_runtime(data_manifest,plan):
    p=Path(__file__).resolve().parents[2]/'test-data-readiness/scripts/data_manifest.py'
    m=_load_module(p,'runtime_data_manifest_contract')
    v=deepcopy(data_manifest); out=m.validate(v,plan); return out,v

def batch_precheck(plan,batch_id,data_manifest,execution_context):
    batches={b['id']:b for b in plan.get('batches',[])}
    if batch_id not in batches: return {'status':'return_to_planning','reason':f'unknown batch {batch_id}'}
    if not execution_context or execution_context.get('environment_ready') is not True: return {'status':'blocked','reason':'execution environment/account/tools not ready'}
    if data_manifest.get('batch_id')!=batch_id: return {'status':'return_to_data','reason':'data manifest belongs to another batch'}
    try: readiness,_normalized=_validate_manifest_runtime(data_manifest,plan)
    except AssertionError as e: return {'status':'return_to_data','reason':str(e)}
    if readiness.get('readiness',{}).get('ready') is not True: return {'status':'return_to_data','reason':readiness.get('readiness',{}).get('reason') or 'batch data not ready'}
    return {'status':'ready','reason':'precheck passed'}

def _index_results(results,path='worker_results'):
    if not isinstance(results,list): fail(path,'list required')
    ids=[r.get('case_id') for r in results]
    if any(x in (None,'') for x in ids): fail(path,'every result requires case_id')
    if len(ids)!=len(set(ids)): fail(path,f'duplicate result for case_id={next(x for x in ids if ids.count(x)>1)}')
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
        if r.get('status')!='BLOCKED' or r.get('blocked_reason_type')!='upstream_case': fail(f'{cid}.status',f'depends on unresolved upstream {bad}; must be BLOCKED(upstream_case)')
        affected=r.get('affected_by'); vals=set(affected if isinstance(affected,list) else str(affected or '').split(','))
        if not set(bad).intersection(vals): fail(f'{cid}.affected_by',f'must identify unresolved dependency {bad}')

def _validate_result_set(task,results,path='worker_results',evidence_root=None):
    planned={c['case_id']:c for c in task['cases']}; actual=_index_results(results,path)
    if set(planned)!=set(actual): fail(path,f'result case set must equal task case set; missing={sorted(set(planned)-set(actual))}, extra={sorted(set(actual)-set(planned))}')
    for cid in task['case_order']:
        validate_case_result(planned[cid],actual[cid],evidence_root=evidence_root)
        _validate_dependencies(planned[cid],actual,task.get('dependency_context',{}))
    return [deepcopy(actual[cid]) for cid in task['case_order']]

class RuntimeOrchestrator:
    def __init__(self,plan,batch_id,data_manifest,execution_context,case_result_ledger=None,run_dir=None):
        self.plan=plan; self.batch_id=batch_id; self.data_manifest=data_manifest; self.execution_context=execution_context; self.case_result_ledger=case_result_ledger or {}; self.run_dir=Path(run_dir) if run_dir else None
        self.precheck=batch_precheck(plan,batch_id,data_manifest,execution_context)
        self.task=None; self.case_results=[]; self.worker_self_review=None; self.reviewer=None; self.active_retest_task=None
        self.status='pending' if self.precheck['status']=='ready' else ('blocked' if self.precheck['status']=='blocked' else 'return_upstream'); self.retest_count=0
    def create_task(self):
        if self.precheck['status']!='ready': fail('precheck',f'cannot create task: {self.precheck}')
        self.task=build_task(self.plan,self.batch_id,'internal/execution/execution-context.yaml',f'internal/data/manifests/{self.batch_id}-data-manifest.json',case_result_ledger=self.case_result_ledger); return deepcopy(self.task)
    def start_worker(self):
        if self.task is None: self.create_task()
        self.status='running'; self.task['status']='running'; return self.status
    def submit_worker_results(self,results):
        if self.status!='running': fail('status','worker results only accepted while running')
        self.case_results=_validate_result_set(self.task,results,evidence_root=self.run_dir); self.status='self_review'; return self.status
    def submit_worker_self_review(self,review):
        if self.status!='self_review': fail('status','self review only accepted after worker results')
        validate_worker_review(review,self.task['case_order'],self.case_results); self.worker_self_review=deepcopy(review); self.status='reviewing'; return self.status
    def submit_reviewer(self,review):
        if self.status!='reviewing': fail('status','reviewer only accepted after passed worker self-review')
        validate_reviewer(review,self.task['case_order'],self.case_results); self.reviewer=deepcopy(review)
        if review['status']=='passed': self.status='completed'; return {'status':'completed'}
        if review['status']=='rework_required':
            self.status='needs_rework'; self.retest_count+=1; self.active_retest_task=build_retest(self.task,review['retest_case_ids'],self.retest_count,self.case_results); return {'status':'needs_rework','retest_task':deepcopy(self.active_retest_task)}
        self.status='return_upstream'; return {'status':'return_upstream','return_stage':review['return_stage'],'findings':review['findings']}
    def apply_retest(self,retest_results,worker_review,reviewer_review):
        if self.status!='needs_rework' or not self.active_retest_task: fail('status','no retest requested')
        validated=_validate_result_set(self.active_retest_task,retest_results,'retest_results',self.run_dir)
        ids=self.active_retest_task['case_order']; validate_worker_review(worker_review,ids,validated); validate_reviewer(reviewer_review,ids,validated)
        if reviewer_review['status']!='passed': fail('reviewer.status','retest reviewer must pass to close rework')
        original_worker=deepcopy(self.worker_self_review); original_reviewer=deepcopy(self.reviewer)
        by={r['case_id']:r for r in self.case_results}; history=[]
        for r in validated:
            old=deepcopy(by.get(r['case_id'])); by[r['case_id']]=deepcopy(r); history.append({'case_id':r['case_id'],'previous':old,'retest':deepcopy(r)})
        merged=[by[cid] for cid in self.task['case_order']]
        _validate_result_set(self.task,merged,'merged_retest_results',self.run_dir)
        aggregate_worker=_compose_worker_review(original_worker,worker_review,self.task['case_order'])
        aggregate_reviewer=_compose_reviewer_review(original_reviewer,reviewer_review,self.task['case_order'])
        validate_worker_review(aggregate_worker,self.task['case_order'],merged); validate_reviewer(aggregate_reviewer,self.task['case_order'],merged)
        self.case_results=merged; self.worker_self_review=aggregate_worker; self.reviewer=aggregate_reviewer; self.status='completed'
        return {'status':'completed','retest_history':history}
    def snapshot(self):
        return {'batch_id':self.batch_id,'status':self.status,'precheck':deepcopy(self.precheck),'case_ids':self.task['case_order'] if self.task else [],'case_results':deepcopy(self.case_results),'worker_self_review':deepcopy(self.worker_self_review),'reviewer':deepcopy(self.reviewer),'dependency_context':deepcopy((self.task or {}).get('dependency_context',{}))}

def build_defect_candidates(batch_snapshot):
    if batch_snapshot.get('reviewer',{}).get('status')!='passed': return []
    return [{'source_batch':batch_snapshot.get('batch_id'),'source_case':r.get('case_id'),'expected':r.get('expected'),'actual':r.get('actual'),'evidence_refs':r.get('evidence_refs',[]),'reviewer_confirmed':True} for r in batch_snapshot.get('case_results',[]) if r.get('status')=='FAIL' and r.get('reason_type')=='product_issue']

# ---- File-backed orchestration API ----
import argparse as _argparse, json as _json, os as _os
from pathlib import Path as _Path

def _read_json(path): return _json.loads(_Path(path).read_text(encoding='utf-8'))
def _read_task(base,ref):
    task=_read_json(_Path(base)/ref)
    validate_task(task)
    return task
def _write_json(path,value):
    p=_Path(path); p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix(p.suffix+'.tmp'); t.write_text(_json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); _os.replace(t,p)
CASE_LEDGER_REL='internal/execution/results/case-results-ledger.json'
def _ledger_path(base): return _Path(base)/CASE_LEDGER_REL


def _sha256(path): return hashlib.sha256(_Path(path).read_bytes()).hexdigest()

def _assert_confirmed_plan_binding(base,plan_path):
    state_path=_Path(base)/'internal/state/run-status.json'
    if not state_path.exists(): fail('execution_plan_binding','run-status.json is required before Runtime starts')
    s=_read_json(state_path); binding=s.get('confirmation_bindings',{}).get('execution-plan')
    if s.get('current_stage')!='execution-runtime':
        fail('execution_plan_binding',f'Runtime can only start during execution-runtime, current stage is {s.get("current_stage")}')
    if not binding: fail('execution_plan_binding','execution plan must be AI-reviewed and user-confirmed before Runtime')
    bound=_Path(binding.get('contract_path','')).resolve(); actual=_Path(plan_path).resolve()
    if bound!=actual: fail('execution_plan_binding',f'Runtime must use the confirmed execution plan: {bound}')
    if not actual.exists() or _sha256(actual)!=binding.get('contract_sha256'):
        fail('execution_plan_binding','confirmed execution plan changed or disappeared after confirmation')
    case_binding=s.get('confirmation_bindings',{}).get('test-cases')
    if not case_binding: fail('execution_plan_binding','confirmed test-case binding is missing')
    cp=_Path(case_binding.get('contract_path',''))
    if not cp.exists() or _sha256(cp)!=case_binding.get('contract_sha256'):
        fail('execution_plan_binding','confirmed test cases changed or disappeared after Planning confirmation')
    plan=_read_json(actual)
    if plan.get('confirmed_cases_sha256')!=case_binding.get('contract_sha256'):
        fail('execution_plan_binding','execution plan is not bound to the current confirmed Case version')
    return s

def _assert_bound_batch_data(base,batch_id,manifest_path,plan_path):
    state_path=_Path(base)/'internal/state/run-status.json'; s=_read_json(state_path)
    binding=s.get('batch_data_bindings',{}).get(batch_id)
    if s.get('batch_data_status',{}).get(batch_id)!='ready' or not binding:
        fail('batch_data_binding',f'{batch_id} data must be validated and bound by the Router before Runtime')
    actual_manifest=_Path(manifest_path).resolve(); bound_manifest=_Path(binding.get('manifest_path','')).resolve()
    if actual_manifest!=bound_manifest or not actual_manifest.exists() or _sha256(actual_manifest)!=binding.get('manifest_sha256'):
        fail('batch_data_binding',f'Runtime must use the unchanged bound manifest for {batch_id}')
    actual_plan=_Path(plan_path).resolve(); bound_plan=_Path(binding.get('plan_path','')).resolve()
    if actual_plan!=bound_plan or _sha256(actual_plan)!=binding.get('plan_sha256'):
        fail('batch_data_binding',f'{batch_id} data binding does not match the current execution plan')
    return binding

def _merge_findings(*reviews):
    out=[]
    for r in reviews:
        for f in (r or {}).get('findings',[]):
            if f not in out: out.append(f)
    return out

def _compose_worker_review(original,retest,all_case_ids):
    checks={k: bool((original or {}).get('checks',{}).get(k)) and bool((retest or {}).get('checks',{}).get(k)) for k in ['all_cases_checked','all_expected_checked','execution_method_checked','evidence_binding_checked','failure_classification_checked','file_cleanup_checked']}
    return {'status':'passed','checked_case_ids':list(all_case_ids),'checks':checks,'findings':_merge_findings(original,retest),'composed_from':['initial_batch_self_review','local_retest_self_review']}

def _compose_reviewer_review(original,retest,all_case_ids):
    checks={k: bool((original or {}).get('checks',{}).get(k)) and bool((retest or {}).get('checks',{}).get(k)) for k in ['completeness_checked','method_consistency_checked','judgement_checked','evidence_checked','abnormal_classification_checked']}
    return {'schema_version':EXECUTION_SCHEMA_VERSION,'status':'passed','checked_case_ids':list(all_case_ids),'checks':checks,'findings':_merge_findings(original,retest),'retest_case_ids':[],'return_stage':None,'composed_from':['initial_batch_review','local_retest_review']}

def _dashboard_module(): return _load_module(Path(__file__).with_name('dashboard_update.py'),'runtime_dashboard_update')
def _dashboard_shell_module(): return _load_module(Path(__file__).with_name('dashboard.py'),'runtime_dashboard_shell')
def _dashboard_paths(base): return _Path(base)/'internal/state/run-status.json',_Path(base)/'dashboard/dashboard-data.json'
def _ensure_dashboard(base,plan):
    state_path,data_path=_dashboard_paths(base); index=_Path(base)/'dashboard/index.html'
    if not index.exists(): _dashboard_shell_module().write_dashboard(index)
    dmod=_dashboard_module()
    if not data_path.exists(): dmod.initialize_runtime_files(state_path,data_path,plan)
def _emit_dashboard(base,event):
    state_path,data_path=_dashboard_paths(base)
    if data_path.exists(): return _dashboard_module().apply_event_files(state_path,data_path,event)
    return None

def _ensure_case_ledger(base,plan):
    path=_ledger_path(base); ledger=_read_json(path) if path.exists() else {'cases':{},'updated_at':None}; rows=ledger.setdefault('cases',{})
    for c in plan.get('cases',[]): rows.setdefault(c['case_id'],{'case_id':c['case_id'],'batch_id':c.get('batch_id'),'status':'PENDING','final_result':None,'reviewer_confirmed':False,'updated_at':None})
    _write_json(path,ledger); return ledger

def _ledger_final_results(ledger):
    out={}
    for cid,item in ledger.get('cases',{}).items():
        st=item.get('final_result') or item.get('status')
        if item.get('reviewer_confirmed') is True and st in {'PASS','FAIL','BLOCKED','PASS_AFTER_FIX'}: out[cid]=item
    return out

def _commit_results_to_ledger(base,task,results,source='batch_review'):
    path=_ledger_path(base)
    if not path.exists(): fail('case_result_ledger','ledger must be initialized before committing results')
    ledger=_read_json(path); rows=ledger.setdefault('cases',{}); planned={c['case_id']:c for c in task.get('cases',[])}
    ts=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
    for r in results:
        cid=r['case_id']; st=r.get('final_result') or r.get('status')
        if st not in {'PASS','FAIL','BLOCKED','PASS_AFTER_FIX'}: fail(f'case_result_ledger.{cid}.status',f'cannot commit non-final status {st}')
        current=rows.setdefault(cid,{'case_id':cid,'batch_id':planned.get(cid,{}).get('batch_id') or task.get('batch_id')})
        if st=='FAIL' and not current.get('initial_result'): current['initial_result']='FAIL'
        current.update({'case_id':cid,'batch_id':planned.get(cid,{}).get('batch_id') or task.get('batch_id'),'status':r.get('status'),'final_result':st,'reviewer_confirmed':True,'source':source,'runtime_result':deepcopy(r),'updated_at':ts})
        if r.get('bug_ref'): current['bug_ref']=r['bug_ref']
        if r.get('existing_bug_ref'): current['existing_bug_ref']=r['existing_bug_ref']
    ledger['updated_at']=ts; _write_json(path,ledger); return ledger

def _unhandled_fail_case_ids(base,results):
    ledger=_read_json(_ledger_path(base)); rows=ledger.get('cases',{})
    out=[]
    for r in results:
        if r.get('status')!='FAIL': continue
        item=rows.get(r.get('case_id'),{})
        if not (r.get('bug_ref') or r.get('existing_bug_ref') or r.get('no_bug_reason') or item.get('bug_ref') or item.get('existing_bug_ref') or item.get('no_bug_reason')):
            out.append(r['case_id'])
    return out


def _active_case_context(base,state,retest=False):
    if retest:
        ar=state.get('active_retest')
        if not ar: fail('status','no active retest')
        task=_read_task(base,ar['task_ref'])
        partial=ar.setdefault('partial_case_results',{})
        return task,partial,ar
    if not state.get('task_ref'): fail('status','batch task is not prepared')
    task=_read_task(base,state['task_ref'])
    partial=state.setdefault('partial_case_results',{})
    return task,partial,state

def start_case_files(run_dir,batch_id,case_id,worker_id=None,retest=False):
    base=_Path(run_dir); sp=base/f'internal/execution/runtime-state/{batch_id}-state.json'; state=_read_json(sp)
    allowed={'needs_rework','retest_running'} if retest else {'pending','running'}
    if state.get('status') not in allowed: fail('status',f'cannot start case while {state.get("status")}')
    task,partial,holder=_active_case_context(base,state,retest)
    order=list(task.get('case_order',[]))
    if case_id not in order: fail('case_id',f'{case_id} is not in current task')
    current=holder.get('current_case')
    if current and current!=case_id: fail('current_case',f'{current} is still active; finish or restart it before {case_id}')
    idx=order.index(case_id); missing=[cid for cid in order[:idx] if cid not in partial]
    if missing: fail('case_order',f'Batch is serial; earlier cases not completed: {missing}')
    # Restarting the same interrupted Case is allowed. A completed Case is not silently rerun.
    if case_id in partial: fail('case_id',f'{case_id} is already completed in this task; use Reviewer-requested retest flow to rerun it')
    holder['current_case']=case_id; holder['current_worker']=worker_id; holder['case_started_at']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
    state['status']='retest_running' if retest else 'running'
    _write_json(sp,state)
    _emit_dashboard(base,{'type':'case_started','batch_id':batch_id,'case_id':case_id,'worker_id':worker_id,'current_action':'execute_case'})
    return state

def finish_case_files(run_dir,batch_id,result_path,retest=False):
    base=_Path(run_dir); sp=base/f'internal/execution/runtime-state/{batch_id}-state.json'; state=_read_json(sp)
    expected_status='retest_running' if retest else 'running'
    if state.get('status')!=expected_status: fail('status',f'cannot finish case while {state.get("status")}')
    task,partial,holder=_active_case_context(base,state,retest)
    result=_read_json(result_path)
    if isinstance(result,list):
        if len(result)!=1: fail('case_result','case-finish accepts exactly one result object')
        result=result[0]
    if not isinstance(result,dict): fail('case_result','object required')
    cid=result.get('case_id')
    if not cid or cid!=holder.get('current_case'): fail('case_id',f'result must belong to active case {holder.get("current_case")}')
    planned={c['case_id']:c for c in task.get('cases',[])}
    if cid not in planned: fail('case_id',f'{cid} is not in current task')
    validate_case_result(planned[cid],result,evidence_root=base)
    actual={k:deepcopy(v) for k,v in partial.items()}; actual[cid]=deepcopy(result)
    _validate_dependencies(planned[cid],actual,task.get('dependency_context',{}))
    partial[cid]=deepcopy(result); holder['current_case']=None; holder['current_worker']=None; holder['last_completed_case']=cid
    _emit_dashboard(base,{'type':'case_finished','batch_id':batch_id,'case_id':cid,'status':result['status'],'actual_execution':result.get('actual_execution'),'blocked_reason_type':result.get('blocked_reason_type'),'blocked_reason':result.get('blocked_reason'),'bug_ref':result.get('bug_ref')})
    order=list(task.get('case_order',[]))
    if all(x in partial for x in order):
        complete=[deepcopy(partial[x]) for x in order]
        _validate_result_set(task,complete,'case_level_results',base)
        if retest:
            ar=state['active_retest']; seq=ar['sequence']; out=base/f'internal/execution/results/{batch_id}-retest-{seq:03d}-results.json'; _write_json(out,complete)
            ar['results_ref']=str(out.relative_to(base)); state['status']='retest_self_review'
        else:
            out=base/f'internal/execution/results/{batch_id}-worker-results.json'; _write_json(out,complete)
            state['worker_results_ref']=str(out.relative_to(base)); state['status']='self_review'
    _write_json(sp,state)
    return state

def prepare_run_files(plan_path,batch_id,manifest_path,context_path,run_dir):
    base=_Path(run_dir); _assert_confirmed_plan_binding(base,plan_path); _assert_bound_batch_data(base,batch_id,manifest_path,plan_path)
    plan=_read_json(plan_path); manifest=_read_json(manifest_path); context=_read_json(context_path)
    _ensure_dashboard(base,plan)
    ledger=_ensure_case_ledger(base,plan); final_results=_ledger_final_results(ledger); pre=batch_precheck(plan,batch_id,manifest,context); state_path=base/f'internal/execution/runtime-state/{batch_id}-state.json'
    state={'batch_id':batch_id,'status':'pending' if pre['status']=='ready' else ('blocked' if pre['status']=='blocked' else 'return_upstream'),'precheck':pre,'task_ref':None,'worker_results_ref':None,'worker_self_review':None,'reviewer':None,'review_history':[],'retest_history':[],'retest_tasks':[],'active_retest':None,'partial_case_results':{},'current_case':None,'current_worker':None,'case_result_ledger_ref':CASE_LEDGER_REL}
    if pre['status']=='ready':
        task=build_task(plan,batch_id,'internal/execution/execution-context.yaml',f'internal/data/manifests/{batch_id}-data-manifest.json',case_result_ledger=final_results); task_path=base/f'internal/execution/tasks/{batch_id}-task.json'; _write_json(task_path,task); state['task_ref']=str(task_path.relative_to(base)); _emit_dashboard(base,{'type':'batch_started','batch_id':batch_id,'worker_id':None,'current_action':'execute_batch'})
    _write_json(state_path,state); return state

def prepare_resumed_cases_files(run_dir,batch_id,case_ids,bug_ref=None):
    base=_Path(run_dir); run_state_path=base/'internal/state/run-status.json'; run_state=_read_json(run_state_path)
    plan_binding=run_state.get('confirmation_bindings',{}).get('execution-plan') or {}
    plan_path=_Path(plan_binding.get('contract_path',''))
    if not plan_path.exists(): fail('execution_plan_binding','confirmed execution plan is missing')
    _assert_confirmed_plan_binding(base,plan_path)
    data_binding=run_state.get('batch_data_bindings',{}).get(batch_id) or {}
    manifest_path=_Path(data_binding.get('manifest_path',''))
    _assert_bound_batch_data(base,batch_id,manifest_path,plan_path)
    pending=run_state.get('pending_resume') or {}
    wanted=list(dict.fromkeys(case_ids or []))
    if not wanted: fail('resume.case_ids','at least one unblocked Case is required')
    if pending.get('batch_id')!=batch_id or set(pending.get('case_ids',[]))!=set(wanted):
        fail('resume.case_ids','must exactly match the Router-approved unblocked Cases for this Batch')
    if bug_ref and pending.get('bug_ref') and bug_ref!=pending.get('bug_ref'):
        fail('resume.bug_ref','does not match the Router-approved regression')

    sp=base/f'internal/execution/runtime-state/{batch_id}-state.json'
    if not sp.exists(): fail('resume.runtime_state','the blocked Batch has no prior runtime state')
    state=_read_json(sp)
    if state.get('status')!='completed' or not state.get('task_ref') or not state.get('worker_results_ref'):
        fail('resume.runtime_state','only a completed, reviewer-checked Batch can resume Cases unblocked by regression')
    task0=_read_task(base,state['task_ref']); original=_read_json(base/state['worker_results_ref']); original_by=_index_results(original,'resume.original_results')
    unknown=set(wanted)-set(task0.get('case_order',[]))
    if unknown: fail('resume.case_ids',f'Cases do not belong to {batch_id}: {sorted(unknown)}')
    ledger=_read_json(_ledger_path(base)); ledger_rows=ledger.get('cases',{})
    for cid in wanted:
        if original_by[cid].get('status')!='BLOCKED': fail(f'resume.{cid}','only previously BLOCKED Cases can resume after regression')
        item=ledger_rows.get(cid,{})
        if item.get('reviewer_confirmed') is not True or (item.get('final_result') or item.get('status'))!='BLOCKED':
            fail(f'resume.{cid}','BLOCKED result must already be reviewer-confirmed in the global ledger')

    context_path=base/task0.get('execution_context_ref','')
    pre=batch_precheck(_read_json(plan_path),batch_id,_read_json(manifest_path),_read_json(context_path))
    if pre.get('status')!='ready': fail('resume.precheck',pre.get('reason') or 'Batch is not ready')
    seq=len(state.get('retest_tasks',[]))+1
    task=build_retest(task0,wanted,seq,original)
    final_results=_ledger_final_results(ledger)
    for case in task.get('cases',[]):
        for dep in case.get('dependencies',[]) or []:
            if dep in wanted: continue
            item=final_results.get(dep)
            if not item or (item.get('final_result') or item.get('status')) not in {'PASS','PASS_AFTER_FIX'}:
                fail(f'resume.{case["case_id"]}.dependencies[{dep}]','dependency is not reviewer-confirmed PASS/PASS_AFTER_FIX after regression')
            task.setdefault('dependency_context',{})[dep]=deepcopy(item)
    task['data_manifest_ref']=str(manifest_path.resolve().relative_to(base.resolve()))
    task['resume_reason']='unblocked_after_regression'; task['bug_ref']=bug_ref or pending.get('bug_ref')
    rp=base/f'internal/execution/tasks/{batch_id}-retest-{seq:03d}.json'; _write_json(rp,task); rel=str(rp.relative_to(base))
    state.setdefault('retest_tasks',[]).append(rel)
    state['active_retest']={'mode':'resume_after_regression','task_ref':rel,'sequence':seq,'results_ref':None,'self_review':None,'reviewer':None,'partial_case_results':{},'current_case':None,'current_worker':None,'bug_ref':task.get('bug_ref')}
    state['status']='needs_rework'; state['precheck']=pre; _write_json(sp,state)
    _emit_dashboard(base,{'type':'batch_started','batch_id':batch_id,'worker_id':None,'current_action':'resume_blocked_cases'})
    return {'state':state,'resume_task_ref':rel}

def accept_worker_results_files(run_dir,batch_id,results_path):
    fail('worker_results','direct Batch result submission is disabled; execute each Case through case-start -> case-finish so dashboard/recovery state stays canonical')

def accept_self_review_files(run_dir,batch_id,review_path):
    base=_Path(run_dir); state_path=base/f'internal/execution/runtime-state/{batch_id}-state.json'; state=_read_json(state_path)
    if state.get('status')!='self_review': fail('status','self review only after worker results')
    task=_read_task(base,state['task_ref']); results=_read_json(base/state['worker_results_ref']); review=_read_json(review_path); validate_worker_review(review,task['case_order'],results)
    state.update(status='reviewing',worker_self_review=review); _write_json(state_path,state); return state

def accept_reviewer_files(run_dir,batch_id,review_path):
    base=_Path(run_dir); state_path=base/f'internal/execution/runtime-state/{batch_id}-state.json'; state=_read_json(state_path)
    if state.get('status')!='reviewing': fail('status','reviewer only after passed worker self-review')
    task=_read_task(base,state['task_ref']); results=_read_json(base/state['worker_results_ref']); review=_read_json(review_path); validate_reviewer(review,task['case_order'],results); state['reviewer']=review; state.setdefault('review_history',[]).append({'type':'initial_or_batch_review','review':deepcopy(review)}); retest_ref=None
    reviewer_id=review.get('reviewer_id') or 'result-reviewer'; _emit_dashboard(base,{'type':'review_started','batch_id':batch_id,'reviewer_id':reviewer_id})
    unhandled_fail_case_ids=[]
    if review['status']=='passed':
        state['status']='completed'; _commit_results_to_ledger(base,task,results,'batch_reviewer_passed')
        unhandled_fail_case_ids=_unhandled_fail_case_ids(base,results)
    elif review['status']=='return_upstream': state['status']='return_upstream'; state['return_stage']=review['return_stage']
    else:
        state['status']='needs_rework'; seq=len(state.get('retest_tasks',[]))+1; retest=build_retest(task,review['retest_case_ids'],seq,_read_json(base/state['worker_results_ref'])); rp=base/f'internal/execution/tasks/{batch_id}-retest-{seq:03d}.json'; _write_json(rp,retest); retest_ref=str(rp.relative_to(base)); state.setdefault('retest_tasks',[]).append(retest_ref); state['active_retest']={'task_ref':retest_ref,'sequence':seq,'results_ref':None,'self_review':None,'reviewer':None,'partial_case_results':{},'current_case':None,'current_worker':None}
    _write_json(state_path,state); _emit_dashboard(base,{'type':'review_finished','batch_id':batch_id,'reviewer_id':reviewer_id,'status':review['status'],'retest_case_ids':review.get('retest_case_ids',[]),'return_stage':review.get('return_stage'),'unhandled_fail_case_ids':unhandled_fail_case_ids})
    return {'state':state,'retest_task_ref':retest_ref}

def accept_retest_results_files(run_dir,batch_id,results_path):
    fail('retest_results','direct retest Batch result submission is disabled; execute each retest Case through retest-case-start -> retest-case-finish')

def accept_retest_self_review_files(run_dir,batch_id,review_path):
    base=_Path(run_dir); sp=base/f'internal/execution/runtime-state/{batch_id}-state.json'; state=_read_json(sp)
    if state.get('status')!='retest_self_review': fail('status','retest self review only after retest results')
    ar=state['active_retest']; task=_read_task(base,ar['task_ref']); results=_read_json(base/ar['results_ref']); review=_read_json(review_path); validate_worker_review(review,task['case_order'],results); ar['self_review']=review; state['status']='retest_reviewing'; _write_json(sp,state); return state

def accept_retest_reviewer_files(run_dir,batch_id,review_path):
    base=_Path(run_dir); sp=base/f'internal/execution/runtime-state/{batch_id}-state.json'; state=_read_json(sp)
    if state.get('status')!='retest_reviewing': fail('status','retest reviewer only after passed retest self-review')
    ar=state['active_retest']; task=_read_task(base,ar['task_ref']); retest_results=_read_json(base/ar['results_ref']); review=_read_json(review_path); validate_reviewer(review,task['case_order'],retest_results); ar['reviewer']=review; reviewer_id=review.get('reviewer_id') or 'result-reviewer'; _emit_dashboard(base,{'type':'review_started','batch_id':batch_id,'reviewer_id':reviewer_id})
    unhandled_fail_case_ids=[]
    if review['status']=='passed':
        original=_read_json(base/state['worker_results_ref']); by={r['case_id']:r for r in original}; retest=_read_json(base/ar['results_ref'])
        for r in retest: by[r['case_id']]=r
        task0=_read_task(base,state['task_ref']); merged=[by[c] for c in task0['case_order']]
        resume_mode=ar.get('mode')=='resume_after_regression'
        if not resume_mode: _validate_result_set(task0,merged,'merged_retest_results',base)
        initial_worker=deepcopy(state.get('worker_self_review') or {})
        initial_reviewer=deepcopy(state.get('reviewer') or {})
        aggregate_worker=_compose_worker_review(initial_worker,ar['self_review'],task0['case_order'])
        aggregate_reviewer=_compose_reviewer_review(initial_reviewer,review,task0['case_order'])
        validate_worker_review(aggregate_worker,task0['case_order'],merged); validate_reviewer(aggregate_reviewer,task0['case_order'],merged)
        _write_json(base/state['worker_results_ref'],merged)
        state.setdefault('retest_history',[]).append({'task_ref':ar['task_ref'],'results_ref':ar['results_ref'],'self_review':deepcopy(ar['self_review']),'reviewer':deepcopy(review)})
        state.setdefault('review_history',[]).append({'type':'local_retest_review','review':deepcopy(review)})
        state['worker_self_review']=aggregate_worker; state['reviewer']=aggregate_reviewer; state['status']='completed'; state['active_retest']=None
        if resume_mode: _commit_results_to_ledger(base,task,retest,'unblocked_cases_reviewer_passed')
        else: _commit_results_to_ledger(base,task0,merged,'retest_reviewer_passed')
        unhandled_fail_case_ids=_unhandled_fail_case_ids(base,merged)
    elif review['status']=='return_upstream': state['status']='return_upstream'; state['return_stage']=review['return_stage']
    else:
        seq=len(state.get('retest_tasks',[]))+1; rt=build_retest(_read_task(base,state['task_ref']),review['retest_case_ids'],seq,_read_json(base/state['worker_results_ref'])); rp=base/f'internal/execution/tasks/{batch_id}-retest-{seq:03d}.json'; _write_json(rp,rt); state['retest_tasks'].append(str(rp.relative_to(base))); state['active_retest']={'task_ref':str(rp.relative_to(base)),'sequence':seq,'results_ref':None,'self_review':None,'reviewer':None,'partial_case_results':{},'current_case':None,'current_worker':None}; state['status']='needs_rework'
    _write_json(sp,state); _emit_dashboard(base,{'type':'review_finished','batch_id':batch_id,'reviewer_id':reviewer_id,'status':review['status'],'retest_case_ids':review.get('retest_case_ids',[]),'return_stage':review.get('return_stage'),'unhandled_fail_case_ids':unhandled_fail_case_ids}); return state

def _cli():
    a=_argparse.ArgumentParser(); sp=a.add_subparsers(dest='cmd',required=True)
    p=sp.add_parser('prepare'); p.add_argument('--plan',required=True); p.add_argument('--batch',required=True); p.add_argument('--manifest',required=True); p.add_argument('--context',required=True); p.add_argument('--run-dir',required=True)
    p=sp.add_parser('resume-blocked-prepare'); p.add_argument('--run-dir',required=True); p.add_argument('--batch',required=True); p.add_argument('--cases',required=True,help='comma-separated Case IDs approved by the Router'); p.add_argument('--bug-ref')
    for name in ['case-start','retest-case-start']:
        p=sp.add_parser(name); p.add_argument('--run-dir',required=True); p.add_argument('--batch',required=True); p.add_argument('--case',required=True); p.add_argument('--worker-id')
    for name in ['case-finish','retest-case-finish']:
        p=sp.add_parser(name); p.add_argument('--run-dir',required=True); p.add_argument('--batch',required=True); p.add_argument('--result',required=True)
    for name in ['self-review','reviewer','retest-self-review','retest-reviewer']:
        p=sp.add_parser(name); p.add_argument('--run-dir',required=True); p.add_argument('--batch',required=True); p.add_argument('--input' if name.startswith('retest') else '--review',required=True)
    x=a.parse_args()
    if x.cmd=='prepare': out=prepare_run_files(x.plan,x.batch,x.manifest,x.context,x.run_dir)
    elif x.cmd=='resume-blocked-prepare': out=prepare_resumed_cases_files(x.run_dir,x.batch,[v.strip() for v in x.cases.split(',') if v.strip()],x.bug_ref)
    elif x.cmd=='case-start': out=start_case_files(x.run_dir,x.batch,x.case,x.worker_id,False)
    elif x.cmd=='case-finish': out=finish_case_files(x.run_dir,x.batch,x.result,False)
    elif x.cmd=='retest-case-start': out=start_case_files(x.run_dir,x.batch,x.case,x.worker_id,True)
    elif x.cmd=='retest-case-finish': out=finish_case_files(x.run_dir,x.batch,x.result,True)
    elif x.cmd=='self-review': out=accept_self_review_files(x.run_dir,x.batch,x.review)
    elif x.cmd=='reviewer': out=accept_reviewer_files(x.run_dir,x.batch,x.review)
    elif x.cmd=='retest-self-review': out=accept_retest_self_review_files(x.run_dir,x.batch,x.input)
    else: out=accept_retest_reviewer_files(x.run_dir,x.batch,x.input)
    print(_json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__': _cli()
