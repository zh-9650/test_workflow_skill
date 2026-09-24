from copy import deepcopy
import importlib.util, hashlib, shutil, tempfile
import json
from datetime import datetime, timezone
from pathlib import Path
from batch_task_builder import build as build_task, validate as validate_task, EXECUTION_SCHEMA_VERSION, seal_task
from retest_task import build as build_retest
from worker_review import validate as validate_worker_review
from reviewer_contract import validate as validate_reviewer
from execution_control import validate as validate_case_result

STATES={'pending','waiting_for_worker','running','self_review','waiting_for_reviewer','reviewing','needs_rework','completed','blocked','return_upstream','retest_running','retest_self_review','retest_waiting_for_reviewer','retest_reviewing'}
HOST_DISPATCH_SOURCES={'codex_subagent_tool','claude_task_tool'}

def fail(path,msg): raise AssertionError(f'{path}: {msg}')

def _load_module(path,name):
    spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def _validate_manifest_runtime(data_manifest,plan,run_dir=None):
    p=Path(__file__).resolve().parents[2]/'test-data-readiness/scripts/data_manifest.py'
    m=_load_module(p,'runtime_data_manifest_contract')
    v=deepcopy(data_manifest); out=m.validate(v,plan,run_dir); return out,v

def batch_precheck(plan,batch_id,data_manifest,execution_context,run_dir=None):
    batches={b['id']:b for b in plan.get('batches',[])}
    if batch_id not in batches: return {'status':'return_to_planning','reason':f'unknown batch {batch_id}'}
    if not execution_context or execution_context.get('environment_ready') is not True: return {'status':'blocked','reason':'execution environment/account/tools not ready'}
    if data_manifest.get('batch_id')!=batch_id: return {'status':'return_to_data','reason':'data manifest belongs to another batch'}
    try: readiness,_normalized=_validate_manifest_runtime(data_manifest,plan,run_dir)
    except AssertionError as e: return {'status':'return_to_data','reason':str(e)}
    if readiness.get('readiness',{}).get('ready') is not True: return {'status':'return_to_data','reason':readiness.get('readiness',{}).get('reason') or 'batch data not ready'}
    return {'status':'ready','reason':'precheck passed'}

def _index_results(results,path='worker_results'):
    if not isinstance(results,list): fail(path,'list required')
    ids=[r.get('case_id') for r in results]
    if any(x in (None,'') for x in ids): fail(path,'every result requires case_id')
    if len(ids)!=len(set(ids)): fail(path,f'duplicate result for case_id={next(x for x in ids if ids.count(x)>1)}')
    return {r['case_id']:r for r in results}

def _result_status_summary(results):
    rows=results if isinstance(results,list) else [results]
    cases={row.get('case_id'):row.get('status') for row in rows if isinstance(row,dict)}
    statuses=set(cases.values())
    if not statuses: fail('result_status','Worker output must contain Case result statuses')
    if statuses=={'PASS'}: overall='PASS'
    elif 'FAIL' in statuses: overall='FAIL'
    elif 'NEEDS_REVIEW' in statuses: overall='NEEDS_REVIEW'
    elif 'BLOCKED' in statuses: overall='BLOCKED'
    elif len(statuses)==1: overall=next(iter(statuses))
    else: overall='MIXED'
    return {'overall':overall,'cases':cases}

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
        self.precheck=batch_precheck(plan,batch_id,data_manifest,execution_context,self.run_dir)
        self.task=None; self.case_results=[]; self.worker_self_review=None; self.reviewer=None; self.active_retest_task=None
        self.status='pending' if self.precheck['status']=='ready' else ('blocked' if self.precheck['status']=='blocked' else 'return_upstream'); self.retest_count=0
    def create_task(self):
        if self.precheck['status']!='ready': fail('precheck',f'cannot create task: {self.precheck}')
        self.task=build_task(self.plan,self.batch_id,'internal/execution/execution-context.yaml',f'internal/data/manifests/{self.batch_id}-data-manifest.json',case_result_ledger=self.case_result_ledger); return deepcopy(self.task)
    def start_worker(self):
        fail('dispatch','in-memory execution is disabled; register an actual host Worker dispatch receipt')
    def submit_worker_results(self,results):
        fail('worker_results','direct in-memory result submission is disabled; use the file-backed host dispatch flow')
    def submit_worker_self_review(self,review):
        fail('worker_self_review','in-memory self-review is disabled; use the receipt-bound file-backed flow')
    def submit_reviewer(self,review):
        fail('reviewer','in-memory review submission is disabled; use a fresh host Reviewer dispatch receipt')
    def apply_retest(self,retest_results,worker_review,reviewer_review):
        fail('retest','in-memory retest is disabled; retest requires a new Worker and Reviewer dispatch')
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

def _canonical_sha256(value):
    raw=_json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()

def _parse_time(value,path):
    try: return datetime.fromisoformat(value.replace('Z','+00:00'))
    except (AttributeError,TypeError,ValueError): fail(path,'valid ISO timestamp required')

def _validate_host_receipt(receipt,role,task,worker_session_id=None):
    if not isinstance(receipt,dict): fail('dispatch_receipt','object required')
    if receipt.get('agent_role')!=role: fail('dispatch_receipt.agent_role',f'must be {role}')
    if receipt.get('task_id')!=task.get('task_id') or receipt.get('task_hash')!=task.get('task_hash'):
        fail('dispatch_receipt','task ID/hash does not match the frozen dispatched task')
    session=receipt.get('agent_session_id')
    if not isinstance(session,str) or not session.strip(): fail('dispatch_receipt.agent_session_id','actual host Agent session identity required')
    if worker_session_id is not None and session==worker_session_id:
        fail('dispatch_receipt.agent_session_id','Reviewer must use a new independent Agent session')
    if receipt.get('dispatch_source') not in HOST_DISPATCH_SOURCES:
        fail('dispatch_receipt.dispatch_source',f'must identify a supported host dispatch tool: {sorted(HOST_DISPATCH_SOURCES)}')
    if not isinstance(receipt.get('host_dispatch_ref'),str) or not receipt['host_dispatch_ref'].strip():
        fail('dispatch_receipt.host_dispatch_ref','host dispatch call/task reference required')
    _parse_time(receipt.get('started_at'),'dispatch_receipt.started_at')
    return session

def _case_artifact_manifest(base,task,results):
    root=_Path(base).resolve(); planned={c['case_id']:c for c in task['cases']}; manifest={}
    for result in results:
        cid=result['case_id']; refs=[]; run=result.get('automation_run') or {}; official=run.get('official_run') or {}
        refs.extend([run.get('script_ref'),official.get('report_ref'),result.get('recording_ref'),result.get('video_ref')])
        for row in result.get('expected_results',[]):
            for ref in row.get('evidence_refs',row.get('evidence',[])) or []:
                refs.append(ref.get('path') or ref.get('ref') if isinstance(ref,dict) else ref)
        for ref in result.get('evidence_refs',[]) or []: refs.append(ref.get('path') or ref.get('ref') if isinstance(ref,dict) else ref)
        for ref in refs:
            if not ref: continue
            path=_Path(ref); path=(path if path.is_absolute() else root/path).resolve()
            try: rel=path.relative_to(root).as_posix()
            except ValueError: fail(f'{cid}.artifacts','artifact escapes the current Run')
            if not path.is_file(): fail(f'{cid}.artifacts',f'missing referenced artifact {rel}')
            manifest[rel]=_sha256(path)
    return dict(sorted(manifest.items()))

def _snapshot_case_artifacts(base,task,results):
    root=_Path(base).resolve(); source_manifest=_case_artifact_manifest(root,task,results)
    snapshot_key=hashlib.sha256(task['task_id'].encode('utf-8')).hexdigest()[:16]
    snapshot_root=root/'internal/execution/snapshots'/snapshot_key
    manifest={}
    for index,(source_ref,source_hash) in enumerate(source_manifest.items(),start=1):
        source=root/source_ref; snapshot=snapshot_root/source_ref
        snapshot=snapshot_root/f'{index:03d}-{_Path(source_ref).name}'
        try: snapshot.resolve().relative_to(root)
        except ValueError: fail('artifact_snapshot','snapshot path escapes the current Run')
        if not snapshot.exists():
            snapshot.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,snapshot)
        snapshot_ref=snapshot.relative_to(root).as_posix(); snapshot_hash=_sha256(snapshot)
        if snapshot_hash!=source_hash: fail(f'artifact_snapshot.{source_ref}','copied content hash differs from frozen Worker artifact')
        manifest[source_ref]={'snapshot_ref':snapshot_ref,'sha256':snapshot_hash}
    return manifest

def _validate_artifact_snapshot(base,reviewer_task):
    root=_Path(base).resolve(); manifest=reviewer_task.get('artifact_snapshot_manifest')
    if not isinstance(manifest,dict) or not manifest: fail('reviewer_task.artifact_snapshot_manifest','immutable artifact snapshot manifest required')
    if reviewer_task.get('artifact_snapshot_sha256')!=_canonical_sha256(manifest):
        fail('reviewer_task.artifact_snapshot_sha256','does not match the frozen snapshot manifest')
    for source_ref,item in manifest.items():
        snapshot_ref=item.get('snapshot_ref') if isinstance(item,dict) else None
        expected_hash=item.get('sha256') if isinstance(item,dict) else None
        if not isinstance(snapshot_ref,str) or not isinstance(expected_hash,str): fail('reviewer_task.artifact_snapshot_manifest','invalid snapshot entry')
        path=(root/snapshot_ref).resolve()
        try: path.relative_to(root)
        except ValueError: fail('reviewer_task.artifact_snapshot_manifest','snapshot path escapes the current Run')
        if not path.is_file() or _sha256(path)!=expected_hash: fail(f'artifact_snapshot.{source_ref}','frozen artifact is missing or changed')

def _validate_worker_recovery_history(base,history,task=None,batch_id=None):
    root=_Path(base).resolve()
    rows=history or []; previous_replacement=None
    task_cases={row.get('case_id') for row in (task or {}).get('cases',[]) if isinstance(row,dict)}
    for index,row in enumerate(rows):
        record_ref=row.get('record_ref'); record_path=(root/record_ref).resolve() if isinstance(record_ref,str) else root
        try: record_path.relative_to(root)
        except ValueError: fail('worker_recovery_history.record_ref','must stay within the current Run')
        if not record_path.is_file() or _sha256(record_path)!=row.get('record_sha256'):
            fail(f'worker_recovery_history[{index}].record_ref','recovery record is missing or changed')
        record=_read_json(record_path); terminal_ref=record.get('terminal_evidence_ref')
        if task is not None:
            if (record.get('task_id')!=task.get('task_id') or record.get('task_hash')!=task.get('task_hash')
                or record.get('batch_id')!= (batch_id or task.get('batch_id'))):
                fail(f'worker_recovery_history[{index}]','recovery record must bind the current frozen Batch Task')
            if record.get('case_id') not in task_cases:
                fail(f'worker_recovery_history[{index}].case_id','must belong to the current frozen Batch Task')
        terminal=(root/terminal_ref).resolve() if isinstance(terminal_ref,str) else root
        try: terminal.relative_to(root)
        except ValueError: fail(f'worker_recovery_history[{index}].terminal_evidence_ref','must stay within the current Run')
        if not terminal.is_file() or _sha256(terminal)!=record.get('terminal_evidence_sha256'):
            fail(f'worker_recovery_history[{index}].terminal_evidence_ref','terminal failure evidence is missing or changed')
        for source_ref,item in (record.get('artifacts') or {}).items():
            snapshot_ref=item.get('snapshot_ref') if isinstance(item,dict) else None
            artifact=(root/snapshot_ref).resolve() if isinstance(snapshot_ref,str) else root
            try: artifact.relative_to(root)
            except ValueError: fail(f'worker_recovery_history[{index}].artifacts','snapshot must stay within the current Run')
            if not artifact.is_file() or _sha256(artifact)!=item.get('sha256'):
                fail(f'worker_recovery_history[{index}].artifacts[{source_ref}]','interrupted attempt snapshot is missing or changed')
        previous=row.get('previous_worker_receipt') or {}; replacement=row.get('replacement_worker_receipt') or {}
        if record.get('previous_worker_receipt')!=previous or record.get('replacement_worker_receipt')!=replacement:
            fail(f'worker_recovery_history[{index}]','reviewed recovery record does not bind both exact host receipts')
        if previous.get('agent_session_id')==replacement.get('agent_session_id'):
            fail(f'worker_recovery_history[{index}]','replacement Worker must be a distinct host session')
        if previous_replacement and previous.get('agent_session_id')!=previous_replacement:
            fail(f'worker_recovery_history[{index}]','recovery sessions do not form a continuous replacement chain')
        previous_replacement=replacement.get('agent_session_id')

def _validate_frozen_artifacts(base,reviewer_task,task,results):
    _validate_artifact_snapshot(base,reviewer_task)
    recovery=reviewer_task.get('worker_recovery_history',[])
    _validate_worker_recovery_history(base,recovery,task,batch_id=reviewer_task.get('batch_id'))
    if recovery and reviewer_task.get('worker_session_id')!=(recovery[-1].get('replacement_worker_receipt') or {}).get('agent_session_id'):
        fail('reviewer_task.worker_recovery_history','final Worker session must be the last registered replacement session')
    snapshot_hashes={ref:item.get('sha256') for ref,item in reviewer_task['artifact_snapshot_manifest'].items()}
    if snapshot_hashes!=reviewer_task.get('artifact_sha256'):
        fail('reviewer_task.artifact_sha256','must exactly match the immutable artifact snapshot hashes')

def validate_result_from_snapshot(base,reviewer_task,plan_case,result):
    """Validate a historical result against its immutable reviewer-input artifacts."""
    _validate_artifact_snapshot(base,reviewer_task)
    with tempfile.TemporaryDirectory(prefix='test-run-artifact-snapshot-') as temp_dir:
        root=_Path(temp_dir)
        for source_ref,item in reviewer_task['artifact_snapshot_manifest'].items():
            source=(_Path(base)/item['snapshot_ref']).resolve()
            target=(root/source_ref).resolve()
            try: target.relative_to(root.resolve())
            except ValueError: fail('artifact_snapshot_manifest','source artifact path escapes the temporary validation root')
            target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,target)
        return validate_case_result(plan_case,result,evidence_root=root)

def _build_reviewer_task(base,batch_id,task,task_ref,results_ref,self_review_ref,results,self_review,sequence=1):
    root=_Path(base); result_hash=_sha256(root/results_ref); self_review_hash=_sha256(root/self_review_ref)
    value={
        'schema_version':EXECUTION_SCHEMA_VERSION,
        'workflow_version':__import__('batch_task_builder').WORKFLOW_VERSION,
        'task_id':f'{batch_id}-reviewer-{sequence:03d}',
        'agent_role':'result_reviewer',
        'batch_id':batch_id,
        'case_order':list(task['case_order']),
        'worker_task_id':task['task_id'],
        'worker_task_hash':task['task_hash'],
        'worker_session_id':None,
        'results_ref':results_ref,
        'results_sha256':result_hash,
        'worker_self_review_ref':self_review_ref,
        'worker_self_review_sha256':self_review_hash,
        'artifact_sha256':_case_artifact_manifest(root,task,results),
        'artifact_snapshot_manifest':_snapshot_case_artifacts(root,task,results),
        'created_at':datetime.now(timezone.utc).isoformat(),
    }
    value['artifact_snapshot_sha256']=_canonical_sha256(value['artifact_snapshot_manifest'])
    value['worker_session_id']=self_review.get('agent_session_id')
    value['task_hash']=_canonical_sha256(value)
    return value

def _validate_reviewer_task_hash(task):
    payload={k:v for k,v in task.items() if k!='task_hash'}
    if task.get('task_hash')!=_canonical_sha256(payload): fail('reviewer_task.task_hash','does not match its frozen payload')

def _dispatch_dir(base): return _Path(base)/'internal/execution/dispatch'

def _run_relative_ref(base,path):
    root=_Path(base).resolve(); target=_Path(path).resolve()
    try: return target.relative_to(root).as_posix()
    except ValueError: fail('dispatch_receipt.outputs','output must be stored inside the current Run')

def _prior_agent_sessions(state):
    sessions=set()
    for key in ('worker_dispatch_receipt','reviewer_dispatch_receipt'):
        value=(state.get(key) or {}).get('agent_session_id')
        if value: sessions.add(value)
    for item in state.get('retest_history',[]):
        for key in ('worker_dispatch_receipt','reviewer_dispatch_receipt'):
            value=(item.get(key) or {}).get('agent_session_id')
            if value: sessions.add(value)
        for recovery in item.get('worker_recovery_history',[]):
            for key in ('previous_worker_receipt','replacement_worker_receipt'):
                value=(recovery.get(key) or {}).get('agent_session_id')
                if value: sessions.add(value)
    active=state.get('active_retest') or {}
    for key in ('worker_dispatch_receipt','reviewer_dispatch_receipt'):
        value=(active.get(key) or {}).get('agent_session_id')
        if value: sessions.add(value)
    for recovery in active.get('worker_recovery_history',[]):
        for key in ('previous_worker_receipt','replacement_worker_receipt'):
            value=(recovery.get(key) or {}).get('agent_session_id')
            if value: sessions.add(value)
    return sessions

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

def _automation_dashboard_summary(base,result):
    run=result.get('automation_run') or {}; official=run.get('official_run') or {}
    script_ref=run.get('script_ref'); script_hash=run.get('script_sha256'); report_ref=official.get('report_ref')
    script_path=(_Path(base)/script_ref).resolve() if script_ref else None
    script_ok=bool(script_path and script_path.is_file() and _sha256(script_path)==script_hash)
    report_path=(_Path(base)/report_ref).resolve() if report_ref else None
    report_ok=bool(report_path and report_path.is_file())
    refs=[]
    for row in result.get('expected_results',[]): refs.extend(row.get('evidence_refs',[]) or [])
    refs.extend(result.get('evidence_refs',[]) or [])
    evidence_files=[]
    for ref in refs:
        raw=(ref.get('path') or ref.get('ref')) if isinstance(ref,dict) else ref
        if raw:
            path=(_Path(base)/raw).resolve()
            try: path.relative_to(_Path(base).resolve())
            except ValueError: continue
            evidence_files.append(path.is_file())
    return {'script_ref':script_ref,'script_sha256':script_hash,'script_status':'verified' if script_ok else 'missing_or_hash_mismatch',
            'runner':run.get('runner'),'driver':run.get('driver'),'static_check':run.get('static_check'),
            'debug_attempt_count':len(run.get('debug_attempts',[])),'official_run_id':official.get('run_id'),
            'official_run_status':'completed' if report_ok else 'missing','official_run_exit_code':official.get('exit_code'),
            'evidence_status':'present' if evidence_files and all(evidence_files) else 'missing','evidence_count':len(evidence_files),
            'recording_status':'completed' if (result.get('recording_ref') or result.get('video_ref')) else 'pending'}

def _ensure_case_ledger(base,plan):
    path=_ledger_path(base); ledger=_read_json(path) if path.exists() else {'cases':{},'updated_at':None}; rows=ledger.setdefault('cases',{})
    for c in plan.get('cases',[]): rows.setdefault(c['case_id'],{'case_id':c['case_id'],'batch_id':c.get('batch_id'),'status':'PENDING','final_result':None,'reviewer_confirmed':False,'updated_at':None})
    _write_json(path,ledger); return ledger

def _assert_parallel_batch_eligibility(base,plan,batch_id,manifest):
    state_dir=base/'internal/execution/runtime-state'
    active=[]
    active_states={'waiting_for_worker','running','self_review','waiting_for_reviewer','reviewing','needs_rework','retest_running','retest_self_review','retest_waiting_for_reviewer','retest_reviewing'}
    for path in state_dir.glob('*-state.json') if state_dir.exists() else []:
        state=_read_json(path)
        if state.get('status') in active_states: active.append(state.get('batch_id'))
    group=set(active)|{batch_id}
    if len(group)<2: return
    run_state=_read_json(base/'internal/state/run-status.json')
    approved=set(run_state.get('parallel_batch_ids',[]))
    if not group<=approved: fail('parallel_batches','concurrent Batch Runtime requires Router-approved parallel_batch_ids; otherwise complete the current Batch first')
    batches={b['id']:b for b in plan.get('batches',[])}
    if any(bid not in batches or batches[bid].get('parallel_safe') is not True for bid in group):
        fail('parallel_batches','every concurrently active Batch must be marked parallel_safe in confirmed Planning')
    case_batch={c['case_id']:c.get('batch_id') for c in plan.get('cases',[])}
    for c in plan.get('cases',[]):
        if c.get('batch_id') in group and any(case_batch.get(dep) in group for dep in c.get('dependencies',[]) or []):
            fail('parallel_batches',f'{c["case_id"]} depends on a Case in another concurrently active Batch')
    refs_by_batch={}
    for bid in group:
        if bid==batch_id: current=manifest
        else:
            rs=_read_json(base/'internal/state/run-status.json'); binding=rs.get('batch_data_bindings',{}).get(bid)
            if not binding: fail('parallel_batches',f'Batch {bid} has no bound Data Manifest')
            current=_read_json(binding['manifest_path'])
        refs={str(o.get('object_ref')) for o in current.get('objects',[]) if o.get('object_ref')}
        if any(refs & previous for previous in refs_by_batch.values()):
            fail('parallel_batches','concurrent Batch Data Manifests reuse business object references; isolated data is required')
        refs_by_batch[bid]=refs

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
        if st in {'FAIL','BLOCKED'} and not current.get('initial_result'): current['initial_result']=st
        if source=='unblocked_cases_reviewer_passed':
            if (current.get('final_result') or current.get('status'))!='BLOCKED' or not isinstance(current.get('runtime_result'),dict) or current['runtime_result'].get('status')!='BLOCKED':
                fail(f'case_result_ledger.{cid}','resume can only replace a preserved Reviewer-confirmed BLOCKED result')
            current['blocked_runtime_result']=deepcopy(current['runtime_result'])
            current['resume_result']=deepcopy(r)
            current['resume_task_id']=task.get('task_id')
            current['resume_task_hash']=task.get('task_hash')
            current['resume_bug_ref']=task.get('bug_ref')
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
    allowed={'retest_running'} if retest else {'running'}
    if state.get('status') not in allowed: fail('status',f'cannot start case while {state.get("status")}')
    task,partial,holder=_active_case_context(base,state,retest)
    receipt=holder.get('worker_dispatch_receipt')
    if not receipt: fail('worker_dispatch','actual Worker host dispatch receipt is required before Case execution')
    session=receipt.get('agent_session_id')
    if not worker_id or worker_id!=session: fail('worker_id','must equal the dispatched Worker Agent session identity')
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
    receipt=holder.get('worker_dispatch_receipt') or {}
    for key,expected in [('agent_session_id',receipt.get('agent_session_id')),('task_id',task.get('task_id')),('task_hash',task.get('task_hash'))]:
        result_key='agent_session_id' if key=='agent_session_id' else key
        if result.get(result_key)!=expected: fail(f'{cid}.{result_key}',f'must bind to dispatched Worker and frozen Task')
    validate_case_result(planned[cid],result,evidence_root=base)
    actual={k:deepcopy(v) for k,v in partial.items()}; actual[cid]=deepcopy(result)
    _validate_dependencies(planned[cid],actual,task.get('dependency_context',{}))
    partial[cid]=deepcopy(result); holder['current_case']=None; holder['current_worker']=None; holder['last_completed_case']=cid
    _emit_dashboard(base,{'type':'case_finished','batch_id':batch_id,'case_id':cid,'status':result['status'],'actual_execution':result.get('actual_execution'),'blocked_reason_type':result.get('blocked_reason_type'),'blocked_reason':result.get('blocked_reason'),'bug_ref':result.get('bug_ref'),'automation_summary':_automation_dashboard_summary(base,result),'recording_status':'completed' if (result.get('recording_ref') or result.get('video_ref')) else None})
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
    _assert_parallel_batch_eligibility(base,plan,batch_id,manifest)
    _ensure_dashboard(base,plan)
    ledger=_ensure_case_ledger(base,plan); final_results=_ledger_final_results(ledger); pre=batch_precheck(plan,batch_id,manifest,context,base); state_path=base/f'internal/execution/runtime-state/{batch_id}-state.json'
    if state_path.exists(): fail('runtime_state','Batch Runtime is already initialized; resume its current state instead of preparing over its history')
    state={'batch_id':batch_id,'status':'waiting_for_worker' if pre['status']=='ready' else ('blocked' if pre['status']=='blocked' else 'return_upstream'),'precheck':pre,'task_ref':None,'worker_results_ref':None,'worker_self_review_ref':None,'worker_self_review':None,'worker_dispatch_receipt':None,'reviewer_task_ref':None,'reviewer_dispatch_receipt':None,'reviewer':None,'review_history':[],'retest_history':[],'retest_tasks':[],'active_retest':None,'partial_case_results':{},'current_case':None,'current_worker':None,'case_result_ledger_ref':CASE_LEDGER_REL}
    if pre['status']=='ready':
        task=build_task(plan,batch_id,'internal/execution/execution-context.yaml',f'internal/data/manifests/{batch_id}-data-manifest.json',case_result_ledger=final_results); task_path=base/f'internal/execution/tasks/{batch_id}-task.json'; _write_json(task_path,task); state['task_ref']=str(task_path.relative_to(base))
        dispatch=_dispatch_dir(base); _write_json(dispatch/f'{batch_id}-worker-task.json',task)
        _emit_dashboard(base,{'type':'batch_started','batch_id':batch_id,'worker_id':None,'current_action':'dispatch_execution_worker'})
    _write_json(state_path,state); return state

def register_worker_dispatch_files(run_dir,batch_id,receipt_path,retest=False):
    base=_Path(run_dir); sp=base/f'internal/execution/runtime-state/{batch_id}-state.json'; state=_read_json(sp)
    expected_status='needs_rework' if retest else 'waiting_for_worker'
    active_status='retest_running' if retest else 'running'
    if state.get('status')==active_status:
        holder=state.get('active_retest') if retest else state
        if holder.get('current_case') is not None or holder.get('partial_case_results'):
            fail('worker_dispatch','dispatch replay is only safe before the Worker starts its first Case')
        saved=holder.get('worker_dispatch_receipt') or {}; requested=_read_json(receipt_path)
        if any(saved.get(k)!=requested.get(k) for k in ('task_id','task_hash','agent_session_id','host_dispatch_ref')):
            fail('worker_dispatch','an active Worker dispatch exists; retry must identify the exact saved host receipt')
        _emit_dashboard(base,{'type':'worker_dispatched','batch_id':batch_id,'worker_id':saved.get('agent_session_id'),'current_action':'execute_batch','retest':retest})
        return state
    if retest:
        if state.get('status')!=expected_status or not state.get('active_retest'): fail('status','Retest Worker can dispatch only after Reviewer requests local rework')
        holder=state['active_retest']; task=_read_task(base,holder['task_ref'])
    else:
        if state.get('status')!=expected_status: fail('status','Worker dispatch receipt is accepted only for a prepared Batch')
        holder=state; task=_read_task(base,state['task_ref'])
    receipt=_read_json(receipt_path); session=_validate_host_receipt(receipt,'execution_worker',task)
    if retest and session in _prior_agent_sessions(state):
        fail('dispatch_receipt.agent_session_id','Retest Worker must use a new Agent session, distinct from all prior Worker and Reviewer sessions')
    receipt=deepcopy(receipt); receipt['accepted_at']=datetime.now(timezone.utc).isoformat(); receipt['receipt_status']='dispatched'
    out=_dispatch_dir(base)/f'{batch_id}-worker-receipt{("-retest-"+str(holder.get("sequence"))) if retest else ""}.json'; _write_json(out,receipt)
    holder['worker_dispatch_receipt']=receipt; holder['worker_receipt_ref']=str(out.relative_to(base))
    state['status']='retest_running' if retest else 'running'
    _write_json(sp,state); _emit_dashboard(base,{'type':'worker_dispatched','batch_id':batch_id,'worker_id':session,'receipt_status':'dispatched','current_action':'execute_batch','retest':retest})
    return state

def recover_worker_dispatch_files(run_dir,batch_id,receipt_path,terminal_evidence_path,retest=False):
    """Replace only a host-confirmed failed Worker before its active Case is committed."""
    base=_Path(run_dir); sp=base/f'internal/execution/runtime-state/{batch_id}-state.json'; state=_read_json(sp)
    required_status='retest_running' if retest else 'running'
    if state.get('status')!=required_status: fail('status',f'Worker recovery requires {required_status}')
    holder=state.get('active_retest') if retest else state
    if retest and not holder: fail('active_retest','no active Retest exists')
    previous=holder.get('worker_dispatch_receipt') or {}
    if previous.get('receipt_status')!='dispatched': fail('worker_recovery','only a dispatched, unfinished host Worker can be recovered')
    case_id=holder.get('current_case')
    if not case_id: fail('worker_recovery.current_case','an interrupted active Case is required')
    if holder.get('partial_case_results'):
        fail('worker_recovery.partial_case_results','cannot replace a Worker after it has committed any Case in this Task')
    task_ref=holder.get('task_ref') if retest else state.get('task_ref')
    task=_read_task(base,task_ref)
    if case_id not in task.get('case_order',[]): fail('worker_recovery.current_case','is not in the frozen Task')
    evidence=_read_json(terminal_evidence_path)
    old_session=previous.get('agent_session_id')
    if (evidence.get('status')!='failed' or evidence.get('agent_session_id')!=old_session
            or evidence.get('host_dispatch_ref')!=previous.get('host_dispatch_ref')
            or evidence.get('task_id')!=task.get('task_id') or evidence.get('task_hash')!=task.get('task_hash')
            or not isinstance(evidence.get('reason'),str) or not evidence['reason'].strip()):
        fail('worker_recovery.terminal_evidence','must bind the observed terminal failure to the exact previous host session and frozen Task')
    observed=evidence.get('observed_at'); _parse_time(observed,'worker_recovery.terminal_evidence.observed_at')
    if evidence.get('observed_via') not in HOST_DISPATCH_SOURCES:
        fail('worker_recovery.terminal_evidence.observed_via','must identify the host dispatch surface where failure was observed')
    new_receipt=_read_json(receipt_path); new_session=_validate_host_receipt(new_receipt,'execution_worker',task)
    if new_session in _prior_agent_sessions(state):
        fail('worker_recovery.receipt.agent_session_id','replacement Worker must be a new host Agent session')

    # Preserve the unfinished attempt's exact script and all Case evidence before
    # the replacement Worker is allowed to rerun and overwrite shared evidence paths.
    planned={row['case_id']:row for row in task.get('cases',[])}; case=planned[case_id]
    artifact_refs=[]
    script_ref=(case.get('automation') or {}).get('script_target')
    if script_ref: artifact_refs.append(script_ref)
    case_evidence=base/'evidence'/batch_id/case_id
    if case_evidence.exists(): artifact_refs.extend(p.relative_to(base).as_posix() for p in case_evidence.rglob('*') if p.is_file())
    recovery_seq=len(holder.get('worker_recovery_history',[]))+1
    recovery_root=base/'internal/execution/interrupted-attempts'/f'{batch_id}-recovery-{recovery_seq:03d}'
    artifacts={}
    for index,ref in enumerate(sorted(set(artifact_refs)),start=1):
        source=(base/ref).resolve()
        try: source.relative_to(base.resolve())
        except ValueError: fail('worker_recovery.artifacts','source artifact escapes the current Run')
        if not source.is_file(): continue
        target=recovery_root/f'{index:03d}-{source.name}'
        target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,target)
        copied_hash=_sha256(target); source_hash=_sha256(source)
        if copied_hash!=source_hash: fail('worker_recovery.artifacts','interrupted artifact snapshot hash mismatch')
        artifacts[ref]={'snapshot_ref':target.relative_to(base).as_posix(),'sha256':source_hash}
    terminal_ref=_run_relative_ref(base,terminal_evidence_path)
    terminal_hash=_sha256(terminal_evidence_path)
    new_receipt=deepcopy(new_receipt); new_receipt['accepted_at']=datetime.now(timezone.utc).isoformat(); new_receipt['receipt_status']='dispatched'; new_receipt['recovery_sequence']=recovery_seq
    record={
        'schema_version':1,'batch_id':batch_id,'task_id':task['task_id'],'task_hash':task['task_hash'],
        'case_id':case_id,'previous_worker_receipt':deepcopy(previous),'terminal_evidence_ref':terminal_ref,
        'terminal_evidence_sha256':terminal_hash,'artifacts':artifacts,'observed_at':observed,
        'replacement_worker_receipt':deepcopy(new_receipt),
    }
    record_path=_dispatch_dir(base)/f'{batch_id}-worker-recovery-{recovery_seq:03d}.json'; _write_json(record_path,record)
    record_ref=str(record_path.relative_to(base)).replace('\\','/')
    receipt_out=_dispatch_dir(base)/f'{batch_id}-worker-receipt{("-retest-"+str(holder.get("sequence"))) if retest else ""}-recovery-{recovery_seq:03d}.json'; _write_json(receipt_out,new_receipt)
    holder.setdefault('worker_recovery_history',[]).append({'record_ref':record_ref,'record_sha256':_sha256(record_path),'previous_worker_receipt':deepcopy(previous),'replacement_worker_receipt':deepcopy(new_receipt)})
    holder['worker_dispatch_receipt']=new_receipt; holder['worker_receipt_ref']=str(receipt_out.relative_to(base)).replace('\\','/'); holder['current_worker']=None
    _write_json(sp,state)
    _emit_dashboard(base,{'type':'worker_dispatched','batch_id':batch_id,'worker_id':new_session,'receipt_status':'dispatched','current_action':'execute_batch','retest':retest,'recovery':True})
    return state

def register_reviewer_dispatch_files(run_dir,batch_id,receipt_path,retest=False):
    base=_Path(run_dir); sp=base/f'internal/execution/runtime-state/{batch_id}-state.json'; state=_read_json(sp)
    expected_status='retest_waiting_for_reviewer' if retest else 'waiting_for_reviewer'
    active_status='retest_reviewing' if retest else 'reviewing'
    if state.get('status')==active_status:
        holder=state.get('active_retest') if retest else state
        saved=holder.get('reviewer_dispatch_receipt') or {}; requested=_read_json(receipt_path)
        if any(saved.get(k)!=requested.get(k) for k in ('task_id','task_hash','agent_session_id','host_dispatch_ref')):
            fail('reviewer_dispatch','an active Reviewer dispatch exists; retry must identify the exact saved host receipt')
        _emit_dashboard(base,{'type':'reviewer_dispatched','batch_id':batch_id,'reviewer_id':saved.get('agent_session_id'),'retest':retest})
        return state
    if retest:
        if state.get('status')!=expected_status: fail('status','Retest Reviewer dispatch requires completed Retest Worker self-review')
        holder=state['active_retest']; task=_read_json(base/holder['reviewer_task_ref']); worker=holder.get('worker_dispatch_receipt') or {}
        worker_task=_read_task(base,holder['task_ref'])
    else:
        if state.get('status')!=expected_status: fail('status','Reviewer dispatch requires completed Worker self-review')
        holder=state; task=_read_json(base/state['reviewer_task_ref']); worker=state.get('worker_dispatch_receipt') or {}
        worker_task=_read_task(base,state['task_ref'])
    _validate_reviewer_task_hash(task)
    _validate_worker_recovery_history(base,task.get('worker_recovery_history',[]),worker_task,batch_id=batch_id)
    session=_validate_host_receipt(_read_json(receipt_path),'result_reviewer',task,worker.get('agent_session_id'))
    if retest and session in _prior_agent_sessions(state):
        fail('dispatch_receipt.agent_session_id','Retest Reviewer must use a new Agent session, distinct from all prior Worker and Reviewer sessions')
    receipt=_read_json(receipt_path); receipt=deepcopy(receipt); receipt['accepted_at']=datetime.now(timezone.utc).isoformat(); receipt['receipt_status']='dispatched'
    suffix=f'-retest-{holder.get("sequence")}' if retest else ''
    out=_dispatch_dir(base)/f'{batch_id}-reviewer-receipt{suffix}.json'; _write_json(out,receipt)
    holder['reviewer_dispatch_receipt']=receipt; holder['reviewer_receipt_ref']=str(out.relative_to(base))
    state['status']='retest_reviewing' if retest else 'reviewing'
    _write_json(sp,state); _emit_dashboard(base,{'type':'reviewer_dispatched','batch_id':batch_id,'reviewer_id':session,'receipt_status':'dispatched','retest':retest})
    return state

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
    pre=batch_precheck(_read_json(plan_path),batch_id,_read_json(manifest_path),_read_json(context_path),base)
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
    seal_task(task); validate_task(task)
    rp=base/f'internal/execution/tasks/{batch_id}-retest-{seq:03d}.json'; _write_json(rp,task); rel=str(rp.relative_to(base))
    state.setdefault('retest_tasks',[]).append(rel)
    state['active_retest']={'mode':'resume_after_regression','task_ref':rel,'sequence':seq,'results_ref':None,'self_review':None,'reviewer':None,'partial_case_results':{},'current_case':None,'current_worker':None,'bug_ref':task.get('bug_ref')}
    state['status']='needs_rework'; state['precheck']=pre; _write_json(sp,state)
    _emit_dashboard(base,{'type':'batch_started','batch_id':batch_id,'worker_id':None,'current_action':'resume_blocked_cases'})
    return {'state':state,'resume_task_ref':rel}

def prepare_product_regression_files(run_dir,batch_id,bug_ref,case_ids,regression_id=None):
    base=_Path(run_dir); rs=_read_json(base/'internal/state/run-status.json')
    if rs.get('current_stage')!='defect-handling': fail('regression.stage','product Regression can only start in defect-handling')
    dashboard=_read_json(base/'dashboard/dashboard-data.json'); defect=next((d for d in dashboard.get('defects',[]) if d.get('id')==bug_ref),None)
    if not defect or defect.get('status')!='pending_regression': fail('regression.bug_ref','Bug must be marked pending_regression before Worker dispatch')
    sp=base/f'internal/execution/runtime-state/{batch_id}-state.json'; state=_read_json(sp)
    if state.get('status')!='completed' or state.get('active_retest') is not None: fail('regression.runtime_state','a completed, Reviewer-checked Batch with no active Retest is required')
    ledger=_read_json(_ledger_path(base)); rows=ledger.get('cases',{}); wanted=list(dict.fromkeys(case_ids or []))
    if not wanted: fail('regression.case_ids','original FAIL and impact Case IDs are required')
    def has_preserved_failure(item):
        if item.get('initial_result')=='FAIL': return True
        return item.get('initial_result')=='BLOCKED' and item.get('source')=='unblocked_cases_reviewer_passed' and isinstance(item.get('resume_result'),dict) and item['resume_result'].get('status')=='FAIL' and item.get('runtime_result')==item.get('resume_result')
    originals={cid for cid in wanted if has_preserved_failure(rows.get(cid,{}))}
    global_originals=[cid for cid,item in rows.items() if has_preserved_failure(item) and (item.get('bug_ref')==bug_ref or item.get('existing_bug_ref')==bug_ref)]
    if not originals and not global_originals: fail('regression.original_case_ids','Regression requires a preserved initial FAIL linked to this Bug in the Run')
    for cid in wanted:
        item=rows.get(cid)
        if not item or item.get('reviewer_confirmed') is not True: fail(f'regression.{cid}','every Regression Case must have a Reviewer-confirmed baseline')
        if cid in originals and item.get('bug_ref')!=bug_ref and item.get('existing_bug_ref')!=bug_ref: fail(f'regression.{cid}.bug_ref','must match the Bug linked to the original FAIL')
    original_task=_read_task(base,state['task_ref']); original_results=_read_json(base/(state.get('final_results_ref') or state['worker_results_ref']))
    seq=len(state.get('retest_tasks',[]))+1; regression_id=regression_id or f'{batch_id}-regression-{seq:03d}'
    if not isinstance(regression_id,str) or not regression_id.strip() or any(c in regression_id for c in '/\\'):
        fail('regression.regression_id','must be a non-empty Run-local identifier')
    task=build_retest(original_task,wanted,seq,original_results)
    task.update({'operation_mode':'product_regression','regression_id':regression_id,'bug_ref':bug_ref})
    seal_task(task); validate_task(task)
    task_path=base/f'internal/execution/tasks/{batch_id}-{regression_id}-task.json'; _write_json(task_path,task); rel=str(task_path.relative_to(base))
    state.setdefault('retest_tasks',[]).append(rel)
    state['active_retest']={'mode':'product_regression','regression_id':regression_id,'bug_ref':bug_ref,'task_ref':rel,'sequence':seq,'results_ref':None,'self_review_ref':None,'self_review':None,'reviewer_task_ref':None,'worker_dispatch_receipt':None,'reviewer_dispatch_receipt':None,'reviewer':None,'partial_case_results':{},'current_case':None,'current_worker':None}
    state['status']='needs_rework'; _write_json(sp,state)
    dispatch=_dispatch_dir(base); _write_json(dispatch/f'{batch_id}-{regression_id}-worker-task.json',task)
    return {'state':state,'regression_id':regression_id,'task_ref':rel,'case_ids':wanted}

def accept_worker_results_files(run_dir,batch_id,results_path):
    fail('worker_results','direct Batch result submission is disabled; execute each Case through case-start -> case-finish so dashboard/recovery state stays canonical')

def accept_self_review_files(run_dir,batch_id,review_path):
    base=_Path(run_dir); state_path=base/f'internal/execution/runtime-state/{batch_id}-state.json'; state=_read_json(state_path)
    if state.get('status')!='self_review': fail('status','Worker self-review only after all official Case results')
    task=_read_task(base,state['task_ref']); results_ref=state['worker_results_ref']; results=_read_json(base/results_ref)
    receipt=state.get('worker_dispatch_receipt') or {}; result_hash=_sha256(base/results_ref)
    review=_read_json(review_path)
    validate_worker_review(review,task['case_order'],results,task_id=task['task_id'],task_hash=task['task_hash'],worker_session_id=receipt.get('agent_session_id'),results_sha256=result_hash)
    dispatch=_dispatch_dir(base); self_ref=str((dispatch/f'{batch_id}-worker-self-review.json').relative_to(base)); _write_json(base/self_ref,review)
    receipt=deepcopy(receipt); receipt.update({'finished_at':datetime.now(timezone.utc).isoformat(),'receipt_status':'completed','result_status':_result_status_summary(results),'outputs':{results_ref:_sha256(base/results_ref),self_ref:_sha256(base/self_ref)}})
    receipt_ref=dispatch/f'{batch_id}-worker-receipt.json'; _write_json(receipt_ref,receipt)
    reviewer_task=_build_reviewer_task(base,batch_id,task,state['task_ref'],results_ref,self_ref,results,review)
    if state.get('worker_recovery_history'):
        recovery_history=deepcopy(state['worker_recovery_history'])
        _validate_worker_recovery_history(base,recovery_history,task,batch_id=batch_id)
        reviewer_task['worker_recovery_history']=recovery_history
        reviewer_task['task_hash']=_canonical_sha256({k:v for k,v in reviewer_task.items() if k!='task_hash'})
    reviewer_path=dispatch/f'{batch_id}-reviewer-task.json'; _write_json(reviewer_path,reviewer_task)
    state.update(status='waiting_for_reviewer',worker_dispatch_receipt=receipt,worker_self_review=review,worker_self_review_ref=self_ref,reviewer_task_ref=str(reviewer_path.relative_to(base)),frozen_results_sha256=result_hash,frozen_artifact_sha256=reviewer_task['artifact_sha256'])
    _write_json(state_path,state); _emit_dashboard(base,{'type':'worker_completed','batch_id':batch_id,'worker_id':receipt.get('agent_session_id'),'receipt_status':'completed','result_status':receipt['result_status']}); return state

def accept_reviewer_files(run_dir,batch_id,review_path):
    base=_Path(run_dir); state_path=base/f'internal/execution/runtime-state/{batch_id}-state.json'; state=_read_json(state_path)
    if state.get('status')!='reviewing': fail('status','Reviewer result only accepted after host Reviewer dispatch receipt')
    task=_read_task(base,state['task_ref']); reviewer_task=_read_json(base/state['reviewer_task_ref']); _validate_reviewer_task_hash(reviewer_task)
    results_ref=state['worker_results_ref']; results=_read_json(base/results_ref); review=_read_json(review_path)
    if _sha256(base/results_ref)!=reviewer_task.get('results_sha256'): fail('reviewer_task.results_sha256','Worker results changed after Reviewer dispatch')
    self_ref=state.get('worker_self_review_ref')
    if not self_ref or _sha256(base/self_ref)!=reviewer_task.get('worker_self_review_sha256'): fail('reviewer_task.worker_self_review_sha256','Worker self-review changed after Reviewer dispatch')
    _validate_frozen_artifacts(base,reviewer_task,task,results)
    worker_session=(state.get('worker_dispatch_receipt') or {}).get('agent_session_id'); reviewer_receipt=state.get('reviewer_dispatch_receipt') or {}; reviewer_session=reviewer_receipt.get('agent_session_id')
    validate_reviewer(review,task['case_order'],results,reviewer_task=reviewer_task,worker_session_id=worker_session,reviewer_session_id=reviewer_session,results_sha256=reviewer_task['results_sha256'])
    state['reviewer']=review; state.setdefault('review_history',[]).append({'type':'initial_or_batch_review','review':deepcopy(review),'reviewer_task_hash':reviewer_task['task_hash']}); retest_ref=None
    reviewer_output_ref=_run_relative_ref(base,review_path)
    reviewer_receipt=deepcopy(reviewer_receipt); reviewer_receipt.update({'finished_at':datetime.now(timezone.utc).isoformat(),'receipt_status':'completed','result_status':review['status'],'outputs':{reviewer_output_ref:_sha256(review_path)}}); _write_json(_dispatch_dir(base)/f'{batch_id}-reviewer-receipt.json',reviewer_receipt); state['reviewer_dispatch_receipt']=reviewer_receipt
    reviewer_id=reviewer_session; _emit_dashboard(base,{'type':'review_started','batch_id':batch_id,'reviewer_id':reviewer_id})
    unhandled_fail_case_ids=[]
    if review['status']=='passed':
        state['status']='completed'; _commit_results_to_ledger(base,task,results,'batch_reviewer_passed')
        unhandled_fail_case_ids=_unhandled_fail_case_ids(base,results)
    elif review['status']=='return_upstream': state['status']='return_upstream'; state['return_stage']=review['return_stage']
    else:
        state['status']='needs_rework'; seq=len(state.get('retest_tasks',[]))+1; retest=build_retest(task,review['retest_case_ids'],seq,_read_json(base/state['worker_results_ref'])); rp=base/f'internal/execution/tasks/{batch_id}-retest-{seq:03d}.json'; _write_json(rp,retest); retest_ref=str(rp.relative_to(base)); state.setdefault('retest_tasks',[]).append(retest_ref); state['active_retest']={'task_ref':retest_ref,'sequence':seq,'results_ref':None,'self_review_ref':None,'self_review':None,'reviewer_task_ref':None,'worker_dispatch_receipt':None,'reviewer_dispatch_receipt':None,'reviewer':None,'partial_case_results':{},'current_case':None,'current_worker':None}
    _write_json(state_path,state); _emit_dashboard(base,{'type':'review_finished','batch_id':batch_id,'reviewer_id':reviewer_id,'reviewer_receipt_status':'completed','reviewer_result_status':review['status'],'status':review['status'],'retest_case_ids':review.get('retest_case_ids',[]),'return_stage':review.get('return_stage'),'unhandled_fail_case_ids':unhandled_fail_case_ids})
    return {'state':state,'retest_task_ref':retest_ref}

def accept_retest_results_files(run_dir,batch_id,results_path):
    fail('retest_results','direct retest Batch result submission is disabled; execute each retest Case through retest-case-start -> retest-case-finish')

def accept_retest_self_review_files(run_dir,batch_id,review_path):
    base=_Path(run_dir); sp=base/f'internal/execution/runtime-state/{batch_id}-state.json'; state=_read_json(sp)
    if state.get('status')!='retest_self_review': fail('status','retest self review only after retest results')
    ar=state['active_retest']; task=_read_task(base,ar['task_ref']); results_ref=ar['results_ref']; results=_read_json(base/results_ref); review=_read_json(review_path); receipt=ar.get('worker_dispatch_receipt') or {}; result_hash=_sha256(base/results_ref)
    validate_worker_review(review,task['case_order'],results,task_id=task['task_id'],task_hash=task['task_hash'],worker_session_id=receipt.get('agent_session_id'),results_sha256=result_hash)
    dispatch=_dispatch_dir(base); self_ref=str((dispatch/f'{batch_id}-retest-{ar["sequence"]:03d}-worker-self-review.json').relative_to(base)); _write_json(base/self_ref,review)
    receipt=deepcopy(receipt); receipt.update({'finished_at':datetime.now(timezone.utc).isoformat(),'receipt_status':'completed','result_status':_result_status_summary(results),'outputs':{results_ref:_sha256(base/results_ref),self_ref:_sha256(base/self_ref)}}); _write_json(dispatch/f'{batch_id}-worker-receipt-retest-{ar["sequence"]}.json',receipt)
    reviewer_task=_build_reviewer_task(base,batch_id,task,ar['task_ref'],results_ref,self_ref,results,review,sequence=ar['sequence']+1)
    if ar.get('worker_recovery_history'):
        recovery_history=deepcopy(ar['worker_recovery_history'])
        _validate_worker_recovery_history(base,recovery_history,task,batch_id=batch_id)
        reviewer_task['worker_recovery_history']=recovery_history
        reviewer_task['task_hash']=_canonical_sha256({k:v for k,v in reviewer_task.items() if k!='task_hash'})
    reviewer_path=dispatch/f'{batch_id}-retest-{ar["sequence"]:03d}-reviewer-task.json'; _write_json(reviewer_path,reviewer_task)
    ar.update(worker_dispatch_receipt=receipt,self_review_ref=self_ref,self_review=review,reviewer_task_ref=str(reviewer_path.relative_to(base)),frozen_results_sha256=result_hash,frozen_artifact_sha256=reviewer_task['artifact_sha256']); state['status']='retest_waiting_for_reviewer'; _write_json(sp,state)
    _emit_dashboard(base,{'type':'worker_completed','batch_id':batch_id,'worker_id':receipt.get('agent_session_id'),'receipt_status':'completed','result_status':receipt['result_status'],'retest':True}); return state

def accept_retest_reviewer_files(run_dir,batch_id,review_path):
    base=_Path(run_dir); sp=base/f'internal/execution/runtime-state/{batch_id}-state.json'; state=_read_json(sp)
    if state.get('status')!='retest_reviewing': fail('status','Retest Reviewer result requires a fresh host dispatch receipt')
    ar=state['active_retest']; task=_read_task(base,ar['task_ref']); reviewer_task=_read_json(base/ar['reviewer_task_ref']); _validate_reviewer_task_hash(reviewer_task); _validate_worker_recovery_history(base,reviewer_task.get('worker_recovery_history',[]),task,batch_id=batch_id); results_ref=ar['results_ref']; retest_results=_read_json(base/results_ref); review=_read_json(review_path)
    if _sha256(base/results_ref)!=reviewer_task.get('results_sha256'): fail('reviewer_task.results_sha256','Retest results changed after Reviewer dispatch')
    if _sha256(base/ar['self_review_ref'])!=reviewer_task.get('worker_self_review_sha256'): fail('reviewer_task.worker_self_review_sha256','Retest Worker self-review changed after Reviewer dispatch')
    _validate_frozen_artifacts(base,reviewer_task,task,retest_results)
    worker_session=(ar.get('worker_dispatch_receipt') or {}).get('agent_session_id'); reviewer_receipt=ar.get('reviewer_dispatch_receipt') or {}; reviewer_session=reviewer_receipt.get('agent_session_id')
    validate_reviewer(review,task['case_order'],retest_results,reviewer_task=reviewer_task,worker_session_id=worker_session,reviewer_session_id=reviewer_session,results_sha256=reviewer_task['results_sha256']); ar['reviewer']=review; reviewer_id=reviewer_session; _emit_dashboard(base,{'type':'review_started','batch_id':batch_id,'reviewer_id':reviewer_id,'retest':True})
    unhandled_fail_case_ids=[]
    reviewer_output_ref=_run_relative_ref(base,review_path)
    reviewer_receipt=deepcopy(reviewer_receipt); reviewer_receipt.update({'finished_at':datetime.now(timezone.utc).isoformat(),'receipt_status':'completed','result_status':review['status'],'outputs':{reviewer_output_ref:_sha256(review_path)}})
    ar['reviewer_dispatch_receipt']=reviewer_receipt
    _write_json(_dispatch_dir(base)/f'{batch_id}-reviewer-receipt-retest-{ar["sequence"]}.json',reviewer_receipt)
    retest_record={'task_ref':ar['task_ref'],'results_ref':ar['results_ref'],'self_review_ref':ar.get('self_review_ref'),'reviewer_task_ref':ar['reviewer_task_ref'],'review':deepcopy(review),'worker_self_review':deepcopy(ar['self_review']),'worker_dispatch_receipt':deepcopy(ar['worker_dispatch_receipt']),'reviewer_dispatch_receipt':reviewer_receipt,'worker_recovery_history':deepcopy(ar.get('worker_recovery_history',[])),'mode':ar.get('mode'),'regression_id':ar.get('regression_id'),'bug_ref':ar.get('bug_ref')}
    state.setdefault('retest_history',[]).append(retest_record)
    state.setdefault('review_history',[]).append({'type':'local_retest_review','review':deepcopy(review),'reviewer_task_hash':reviewer_task['task_hash']})
    if review['status']=='passed':
        current_ref=state.get('final_results_ref') or state['worker_results_ref']
        original=_read_json(base/current_ref); by={r['case_id']:r for r in original}; retest=_read_json(base/ar['results_ref'])
        for r in retest: by[r['case_id']]=r
        task0=_read_task(base,state['task_ref']); merged=[by[c] for c in task0['case_order']]
        resume_mode=ar.get('mode')=='resume_after_regression'; product_regression=ar.get('mode')=='product_regression'
        if not resume_mode and not product_regression: _validate_result_set(task0,merged,'merged_retest_results',base)
        initial_worker=deepcopy(state.get('worker_self_review') or {})
        initial_reviewer=deepcopy(state.get('reviewer') or {})
        if product_regression:
            prior=[entry for entry in state.get('retest_history',[]) if entry.get('mode')=='product_regression' and entry.get('regression_id')==ar.get('regression_id')]
            aggregate={}
            for attempt in prior+[retest_record]:
                for result in _read_json(base/attempt['results_ref']): aggregate[result['case_id']]=deepcopy(result)
            aggregate_ref=f'internal/execution/results/{batch_id}-{ar.get("regression_id")}-final-regression-results.json'
            _write_json(base/aggregate_ref,[aggregate[cid] for cid in aggregate])
            state['product_regression_results_ref']=aggregate_ref
        else:
            aggregate_worker=_compose_worker_review(initial_worker,ar['self_review'],task0['case_order'])
            aggregate_reviewer=_compose_reviewer_review(initial_reviewer,review,task0['case_order'])
            merged_ref=f'internal/execution/results/{batch_id}-merged-after-retest-{ar["sequence"]:03d}.json'
            _write_json(base/merged_ref,merged); state['final_results_ref']=merged_ref
            state['worker_self_review']=aggregate_worker; state['reviewer']=aggregate_reviewer
        state['status']='completed'; state['active_retest']=None
        if resume_mode: _commit_results_to_ledger(base,task,retest,'unblocked_cases_reviewer_passed')
        elif not product_regression: _commit_results_to_ledger(base,task0,merged,'retest_reviewer_passed')
        unhandled_fail_case_ids=_unhandled_fail_case_ids(base,retest if product_regression else merged)
    elif review['status']=='return_upstream': state['status']='return_upstream'; state['return_stage']=review['return_stage']
    else:
        seq=len(state.get('retest_tasks',[]))+1; baseline_ref=state.get('final_results_ref') or state.get('product_regression_results_ref') or state['worker_results_ref']; rt=build_retest(_read_task(base,state['task_ref']),review['retest_case_ids'],seq,_read_json(base/baseline_ref))
        if ar.get('mode')=='product_regression': rt.update({'operation_mode':'product_regression','regression_id':ar.get('regression_id'),'bug_ref':ar.get('bug_ref')}); __import__('batch_task_builder').seal_task(rt); validate_task(rt)
        rp=base/f'internal/execution/tasks/{batch_id}-retest-{seq:03d}.json'; _write_json(rp,rt); state['retest_tasks'].append(str(rp.relative_to(base))); state['active_retest']={'task_ref':str(rp.relative_to(base)),'sequence':seq,'results_ref':None,'self_review_ref':None,'self_review':None,'reviewer_task_ref':None,'worker_dispatch_receipt':None,'reviewer_dispatch_receipt':None,'reviewer':None,'partial_case_results':{},'current_worker':None,'partial_case_results':{},'current_case':None,'mode':ar.get('mode'),'regression_id':ar.get('regression_id'),'bug_ref':ar.get('bug_ref')}; state['status']='needs_rework'
    _write_json(sp,state); _emit_dashboard(base,{'type':'review_finished','batch_id':batch_id,'reviewer_id':reviewer_id,'reviewer_receipt_status':'completed','reviewer_result_status':review['status'],'status':review['status'],'retest_case_ids':review.get('retest_case_ids',[]),'return_stage':review.get('return_stage'),'unhandled_fail_case_ids':unhandled_fail_case_ids,'retest':True}); return state

def _cli():
    a=_argparse.ArgumentParser(); sp=a.add_subparsers(dest='cmd',required=True)
    p=sp.add_parser('prepare'); p.add_argument('--plan',required=True); p.add_argument('--batch',required=True); p.add_argument('--manifest',required=True); p.add_argument('--context',required=True); p.add_argument('--run-dir',required=True)
    p=sp.add_parser('resume-blocked-prepare'); p.add_argument('--run-dir',required=True); p.add_argument('--batch',required=True); p.add_argument('--cases',required=True,help='comma-separated Case IDs approved by the Router'); p.add_argument('--bug-ref')
    p=sp.add_parser('regression-prepare'); p.add_argument('--run-dir',required=True); p.add_argument('--batch',required=True); p.add_argument('--cases',required=True,help='comma-separated original FAIL and confirmed impact Case IDs'); p.add_argument('--bug-ref',required=True); p.add_argument('--regression-id')
    for name in ['worker-dispatch','reviewer-dispatch']:
        p=sp.add_parser(name); p.add_argument('--run-dir',required=True); p.add_argument('--batch',required=True); p.add_argument('--receipt',required=True); p.add_argument('--retest',action='store_true')
    p=sp.add_parser('worker-recover-dispatch'); p.add_argument('--run-dir',required=True); p.add_argument('--batch',required=True); p.add_argument('--receipt',required=True); p.add_argument('--terminal-evidence',required=True); p.add_argument('--retest',action='store_true')
    for name in ['case-start','retest-case-start']:
        p=sp.add_parser(name); p.add_argument('--run-dir',required=True); p.add_argument('--batch',required=True); p.add_argument('--case',required=True); p.add_argument('--worker-id',required=True)
    for name in ['case-finish','retest-case-finish']:
        p=sp.add_parser(name); p.add_argument('--run-dir',required=True); p.add_argument('--batch',required=True); p.add_argument('--result',required=True)
    for name in ['self-review','reviewer','retest-self-review','retest-reviewer']:
        p=sp.add_parser(name); p.add_argument('--run-dir',required=True); p.add_argument('--batch',required=True); p.add_argument('--input' if name.startswith('retest') else '--review',required=True)
    x=a.parse_args()
    if x.cmd=='prepare': out=prepare_run_files(x.plan,x.batch,x.manifest,x.context,x.run_dir)
    elif x.cmd=='resume-blocked-prepare': out=prepare_resumed_cases_files(x.run_dir,x.batch,[v.strip() for v in x.cases.split(',') if v.strip()],x.bug_ref)
    elif x.cmd=='regression-prepare': out=prepare_product_regression_files(x.run_dir,x.batch,x.bug_ref,[v.strip() for v in x.cases.split(',') if v.strip()],x.regression_id)
    elif x.cmd=='worker-dispatch': out=register_worker_dispatch_files(x.run_dir,x.batch,x.receipt,x.retest)
    elif x.cmd=='worker-recover-dispatch': out=recover_worker_dispatch_files(x.run_dir,x.batch,x.receipt,x.terminal_evidence,x.retest)
    elif x.cmd=='reviewer-dispatch': out=register_reviewer_dispatch_files(x.run_dir,x.batch,x.receipt,x.retest)
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
