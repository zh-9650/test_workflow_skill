import argparse, json, importlib.util, hashlib
from pathlib import Path
from datetime import datetime, timezone


def fail(path,msg): raise AssertionError(f'{path}: {msg}')
def _load(path,name):
    spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def _load_execution_control(): return _load(Path(__file__).resolve().parents[2]/'test-execution-runtime/scripts/execution_control.py','shared_execution_control')
def _sha256(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _now(): return datetime.now(timezone.utc).isoformat()

def _dashboard(run_dir,event):
    p=Path(__file__).resolve().parents[2]/'test-execution-runtime/scripts/dashboard_update.py'; m=_load(p,'defect_dashboard_update'); base=Path(run_dir); state=base/'internal/state/run-status.json'; data=base/'dashboard/dashboard-data.json'
    if not event.get('stage'): event['stage']='defect-handling'
    if data.exists(): return m.apply_event_files(state,data,event)
    return None

def _inside(path,root):
    try: path.resolve().relative_to(root.resolve()); return True
    except ValueError: return False

def _run_evidence_file(run_dir,ref,allowed_roots,path):
    base=Path(run_dir).resolve(); p=Path(ref); p=(p if p.is_absolute() else base/p).resolve()
    if not any(_inside(p,r) for r in allowed_roots): fail(path,f'evidence must belong to one of the source Case evidence directories: {p}')
    if not p.exists() or not p.is_file(): fail(path,f'evidence file does not exist: {p}')
    return p

def _load_confirmed_plan(run_dir):
    base=Path(run_dir).resolve(); plan_path=base/'internal/execution/execution-plan.json'; state_path=base/'internal/state/run-status.json'
    if not plan_path.exists(): fail('execution_plan','missing current execution plan')
    if not state_path.exists(): fail('execution_plan','run-status.json missing')
    state=json.loads(state_path.read_text(encoding='utf-8')); binding=state.get('confirmation_bindings',{}).get('execution-plan')
    if not binding: fail('execution_plan','execution plan is not user-confirmed/bound')
    if Path(binding.get('contract_path','')).resolve()!=plan_path.resolve() or _sha256(plan_path)!=binding.get('contract_sha256'):
        fail('execution_plan','confirmed execution plan changed or binding does not match')
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    return plan_path,plan

def validate_data_readiness_review(run_dir,ref,batch_id,case_ids):
    base=Path(run_dir).resolve()
    if not isinstance(ref,str) or not ref: fail('data_readiness_review_ref','Run-relative review file required')
    path=(base/ref).resolve()
    if not _inside(path,base/'internal/data/reviews') or not path.is_file():
        fail('data_readiness_review_ref','must be a real file under internal/data/reviews')
    review=json.loads(path.read_text(encoding='utf-8'))
    if review.get('schema_version')!=3 or review.get('source_kind')!='data_readiness' or review.get('status')!='passed':
        fail('data_readiness_review','v3 passed data_readiness review required')
    if review.get('batch_id')!=batch_id or set(review.get('affected_case_ids',[]))!=set(case_ids):
        fail('data_readiness_review','review Batch/Case scope must exactly match the defect source')
    if review.get('legal_reproduction_verified') is not True or not review.get('blocked_reason'):
        fail('data_readiness_review','legal reproduction and blocked reason required')
    artifacts={}
    for name,root in [('reviewer_task','internal/data/reviews'),('reviewer_receipt','internal/data/reviews'),('preparation_failure','evidence'),('host_events','internal/data/reviews')]:
        p=(base/str(review.get(name+'_ref',''))).resolve()
        if not _inside(p,base/root) or not p.is_file() or _sha256(p)!=review.get(name+'_sha256'):
            fail('data_readiness_review.'+name,'real artifact and matching SHA-256 required')
        artifacts[name]=json.loads(p.read_text(encoding='utf-8'))
    task=artifacts['reviewer_task']; receipt=artifacts['reviewer_receipt']; failure=artifacts['preparation_failure']
    session=review.get('reviewer_session_id')
    if not session or session==failure.get('preparer_session_id') or not failure.get('preparer_session_id'):
        fail('data_readiness_review.reviewer_session_id','fresh Reviewer must differ from data preparer')
    if (receipt.get('agent_role')!='result_reviewer' or receipt.get('receipt_status')!='completed'
        or receipt.get('agent_session_id')!=session or receipt.get('dispatch_source') not in {'codex_subagent_tool','claude_task_tool','antigravity_subagent_tool'}
        or not receipt.get('host_dispatch_ref') or receipt.get('task_id')!=task.get('task_id')
        or receipt.get('task_hash')!=review['reviewer_task_sha256']):
        fail('data_readiness_review.reviewer_receipt','completed host Reviewer receipt must bind exact Task and session')
    if task.get('batch_id')!=batch_id or set(task.get('case_ids',[]))!=set(case_ids) or task.get('preparation_failure_sha256')!=review['preparation_failure_sha256']:
        fail('data_readiness_review.reviewer_task','must freeze Batch, Case scope and preparation failure')
    if failure.get('batch_id')!=batch_id or set(failure.get('affected_case_ids',[]))!=set(case_ids) or failure.get('legal_reproduction') is not True:
        fail('data_readiness_review.preparation_failure','must bind legally reproduced preparation failure')
    events=artifacts['host_events'].get('events')
    if not isinstance(events,list): fail('data_readiness_review.host_events','raw ordered host dispatch/completion events required')
    dispatch=[e for e in events if e.get('event_type')=='agent_dispatched' and e.get('call_id')==receipt['host_dispatch_ref']]
    completed=[e for e in events if e.get('event_type')=='agent_completed' and e.get('call_id')==receipt['host_dispatch_ref']]
    if len(dispatch)!=1 or len(completed)!=1: fail('data_readiness_review.host_events','exact Reviewer dispatch and completion required')
    for event in dispatch+completed:
        if event.get('agent_session_id')!=session or event.get('task_sha256')!=review['reviewer_task_sha256']:
            fail('data_readiness_review.host_events','host event session and Task must match receipt')
    try:
        prepared=datetime.fromisoformat(failure['completed_at'].replace('Z','+00:00'))
        started=datetime.fromisoformat(dispatch[0]['at'].replace('Z','+00:00'))
        finished=datetime.fromisoformat(completed[0]['at'].replace('Z','+00:00'))
    except (KeyError,TypeError,ValueError): fail('data_readiness_review.host_events','valid preparation/dispatch/completion timestamps required')
    if any(t.tzinfo is None for t in (prepared,started,finished)):
        fail('data_readiness_review.host_events','timezone-aware timestamps required')
    if events.index(dispatch[0])>=events.index(completed[0]) or not prepared<=started<finished:
        fail('data_readiness_review.host_events','Reviewer must be dispatched after preparation and complete after dispatch')
    return review

def validate(v):
    for k in ['defect_id','source_cases','source_batch','reviewer_confirmed','duplicate_check','root_cause_group','payload','self_review','submission']:
        if k not in v: fail(k,'required')
    if not v['source_cases']: fail('source_cases','non-empty required')
    if not v['source_batch']: fail('source_batch','required')
    if v['reviewer_confirmed'] is not True: fail('reviewer_confirmed','must be true before formal bug handling')
    dc=v['duplicate_check']
    if dc.get('performed') is not True: fail('duplicate_check.performed','must be true')
    if dc.get('result') not in {'new','existing'}: fail('duplicate_check.result','new|existing required')
    if dc['result']=='existing' and not dc.get('existing_bug_ref'): fail('duplicate_check.existing_bug_ref','required for existing bug')
    payload=v['payload']; req=['title','project','module','developer','severity','environment','preconditions','steps','actual','expected','reproduction_rate','evidence_refs']
    for k in req:
        if k not in payload or payload[k] in (None,'',[]): fail(f'payload.{k}','required')
    if v['self_review'].get('status')!='passed': fail('self_review.status','must be passed before submission')
    sub=v['submission']
    if sub.get('status') not in {'submitted','failed','not_submitted_existing'}: fail('submission.status','invalid')
    if dc['result']=='new':
        if sub.get('status')=='not_submitted_existing': fail('submission.status','new bug cannot use not_submitted_existing')
        if sub.get('status')=='submitted' and not sub.get('bug_ref'): fail('submission.bug_ref','required after submitted')
        if sub.get('status')=='failed' and sub.get('bug_ref'): fail('submission.bug_ref','failed submission must not declare bug_ref')
    else:
        if sub.get('status')!='not_submitted_existing': fail('submission.status','existing bug must use not_submitted_existing')
        if sub.get('bug_ref')!=dc.get('existing_bug_ref'): fail('submission.bug_ref','must equal existing_bug_ref')
    return {'ok':True,'defect_id':v['defect_id'],'submission_status':sub.get('status'),'bug_ref':dc.get('existing_bug_ref') or sub.get('bug_ref')}

def _baseline_case_map(plan):
    rows={c.get('case_id'):c for c in plan.get('cases',[])}
    if None in rows: fail('execution_plan.cases','case_id required')
    return rows

def _assert_task_matches_plan(task,batch_id,case_ids,planned,path):
    task_rows={c.get('case_id'):c for c in task.get('cases',[]) if isinstance(c,dict)}
    if (task.get('batch_id')!=batch_id or task.get('case_order')!=case_ids or
            set(task_rows)!=set(case_ids) or len(task_rows)!=len(task.get('cases',[]))):
        fail(path,'frozen Worker Task Case scope/order must exactly match the confirmed Execution Plan Batch')
    for cid in case_ids:
        if task_rows[cid]!=planned[cid]:
            fail(f'{path}.cases[{cid}]','frozen Worker Task Case must exactly match the confirmed Execution Plan Case')

def _load_reviewed_runtime_batch(run_dir,batch_id,plan_batch,planned,final_mod,worker_mod,reviewer_mod,runtime_mod,run_sessions):
    base=Path(run_dir).resolve(); p=f'runtime_batches[{batch_id}]'; state_path=base/'internal/execution/runtime-state'/f'{batch_id}-state.json'
    if not state_path.is_file(): fail(f'{p}.runtime_state',f'missing completed Runtime state for planned Batch {batch_id}')
    state=json.loads(state_path.read_text(encoding='utf-8'))
    if state.get('batch_id')!=batch_id or state.get('status')!='completed':
        fail(f'{p}.runtime_state','must be the completed state for the planned Batch')
    task_path,task=final_mod._run_json(base,state.get('task_ref',''),f'{p}.task_ref')
    planned_ids=plan_batch.get('case_ids',[])
    planned_rows={cid:planned[cid] for cid in planned_ids if cid in planned}
    _assert_task_matches_plan(task,batch_id,planned_ids,planned,f'{p}.task_ref')
    _,initial_results=final_mod._run_json(base,state.get('worker_results_ref',''),f'{p}.worker_results_ref')
    final_mod._validate_runtime_receipts(base,batch_id,state,task,initial_results,worker_mod,reviewer_mod,runtime_mod,run_sessions)

    # Local retests are Runtime Worker Tasks too; their scope may be a subset,
    # but every frozen Case must remain identical to the confirmed plan.
    for index,entry in enumerate(state.get('retest_history',[])):
        if entry.get('mode')=='product_regression': continue
        rtask_path,rtask=final_mod._run_json(base,entry.get('task_ref',''),f'{p}.retest_history[{index}].task_ref')
        retest_ids=rtask.get('case_order',[])
        if not retest_ids or any(cid not in planned_ids for cid in retest_ids):
            fail(f'{p}.retest_history[{index}].task_ref','local Retest Case scope must be a non-empty subset of confirmed Batch scope')
        _assert_task_matches_plan(rtask,batch_id,retest_ids,planned,f'{p}.retest_history[{index}].task_ref')

    results_ref=state.get('final_results_ref') or state.get('worker_results_ref')
    _,canonical_results=final_mod._run_json(base,results_ref,f'{p}.final_results_ref')
    if not isinstance(canonical_results,list): fail(f'{p}.final_results_ref','Runtime result list required')
    canonical_by={result.get('case_id'):result for result in canonical_results if isinstance(result,dict)}
    if len(canonical_by)!=len(canonical_results) or set(canonical_by)!=set(planned_ids):
        fail(f'{p}.final_results_ref','unique Runtime results must exactly match the confirmed plan Batch scope')
    for entry in state.get('retest_history',[]):
        review=entry.get('review') or {}
        if review.get('status')!='passed' or entry.get('mode')=='product_regression': continue
        _,retest_results=final_mod._run_json(base,entry.get('results_ref',''),f'{p}.retest_history.results_ref')
        if not isinstance(retest_results,list): fail(f'{p}.retest_history.results_ref','Runtime result list required')
        for result in retest_results: canonical_by[result.get('case_id')]=result
    for cid in planned_ids:
        final_mod._validate_case_result_snapshot(base,planned_rows[cid],canonical_by.get(cid,{}),{batch_id:state},runtime_mod)
    return state,canonical_by,task

def _validate_regression_runtime(regression,baseline_plan,run_dir):
    base=Path(run_dir).resolve(); runtime_refs=regression.get('runtime_evidence')
    if not isinstance(runtime_refs,list) or not runtime_refs: fail('runtime_evidence','completed Regression requires real per-Batch Runtime Worker/Reviewer evidence')
    runtime_root=Path(__file__).resolve().parents[2]/'test-execution-runtime/scripts'
    import sys
    if str(runtime_root) not in sys.path: sys.path.insert(0,str(runtime_root))
    final_mod=_load(Path(__file__).resolve().parents[2]/'test-result-review/scripts/final_review.py','regression_runtime_final_review')
    execution=_load_execution_control(); worker=_load(runtime_root/'worker_review.py','regression_runtime_worker_review')
    reviewer=_load(runtime_root/'reviewer_contract.py','regression_runtime_reviewer_contract')
    runtime=_load(runtime_root/'runtime_orchestrator.py','regression_runtime_orchestrator')
    plan_cases=_baseline_case_map(baseline_plan); merged={}; seen_task_refs=set(); sessions=set(); proof=[]; order_keys=[]
    batch_order={b.get('id'):i for i,b in enumerate(baseline_plan.get('batches',[]))}
    for i,ref in enumerate(runtime_refs):
        p=f'runtime_evidence[{i}]'; bid=ref.get('batch_id') if isinstance(ref,dict) else None
        if not bid or bid not in batch_order: fail(p+'.batch_id','planned Batch ID required')
        state_path=base/'internal/execution/runtime-state'/f'{bid}-state.json'
        if not state_path.is_file(): fail(p+'.batch_id',f'missing Runtime state for {bid}')
        state=json.loads(state_path.read_text(encoding='utf-8'))
        task_ref=ref.get('task_ref'); task_path=(base/task_ref).resolve() if isinstance(task_ref,str) else base
        try: task_path.relative_to(base)
        except ValueError: fail(p+'.task_ref','must stay within current Run')
        matches=[]
        for entry in state.get('retest_history',[]):
            entry_path=(base/entry.get('task_ref','')).resolve()
            if entry_path==task_path: matches.append(entry)
        if len(matches)!=1: fail(p+'.task_ref','must identify exactly one completed Runtime Regression Worker/Reviewer history')
        entry=matches[0]; task=json.loads(task_path.read_text(encoding='utf-8'))
        normalized_task_ref=str(task_path.relative_to(base)).replace('\\','/')
        if normalized_task_ref in seen_task_refs: fail(p+'.task_ref','duplicate Runtime Regression task reference')
        seen_task_refs.add(normalized_task_ref)
        history_index=state.get('retest_history',[]).index(entry)
        order_keys.append((batch_order[bid],history_index))
        if entry.get('mode')!='product_regression' or task.get('operation_mode')!='product_regression': fail(p+'.task_ref','Runtime Task is not a product Regression')
        if task.get('regression_id')!=regression.get('regression_id') or task.get('bug_ref')!=regression.get('bug_ref'):
            fail(p+'.task_ref','Runtime Regression Task must bind the same Regression and Bug IDs')
        for key in ['target_environment','deployment_version','deployment_event_ref','deployment_event_sha256']:
            if task.get(key)!=regression.get(key) or entry.get(key)!=regression.get(key):
                fail(p+'.'+key,'Task and completed Runtime history must bind the exact Regression deployment')
        if task.get('batch_id')!=bid: fail(p+'.task_ref','Runtime Regression Task Batch mismatch')
        if task.get('task_hash')!=__import__('batch_task_builder').task_hash(task): fail(p+'.task_ref','Runtime Regression Task Hash mismatch')
        result_path=(base/entry.get('results_ref','')).resolve()
        try: result_path.relative_to(base)
        except ValueError: fail(p+'.results_ref','must stay within current Run')
        results=json.loads(result_path.read_text(encoding='utf-8'))
        expected_ids=set(task.get('case_order',[]))
        if not expected_ids or expected_ids!=set(ref.get('case_ids',[])): fail(p+'.case_ids','must exactly match the Cases executed by this Runtime Regression task')
        for result in results:
            cid=result.get('case_id')
            if cid not in plan_cases or plan_cases[cid].get('batch_id')!=bid: fail(p+'.results','Case must belong to this planned Batch')
            runtime._validate_result_version(task,result)
            merged[cid]=result
        initial_task=json.loads((base/state['task_ref']).read_text(encoding='utf-8'))
        initial_results=json.loads((base/state['worker_results_ref']).read_text(encoding='utf-8'))
        final_mod._validate_runtime_receipts(base,bid,state,initial_task,initial_results,worker,reviewer,runtime)
        worker_session=entry['worker_dispatch_receipt']['agent_session_id']; reviewer_session=entry['reviewer_dispatch_receipt']['agent_session_id']
        if worker_session in sessions or reviewer_session in sessions: fail(p+'.sessions','Regression Worker/Reviewer sessions must be unique across all Runtime Regression batches')
        sessions.update({worker_session,reviewer_session})
        reviewer_task_path=(base/entry.get('reviewer_task_ref','')).resolve()
        try: reviewer_task_path.relative_to(base)
        except ValueError: fail(p+'.reviewer_task_ref','must stay within current Run')
        if not reviewer_task_path.is_file(): fail(p+'.reviewer_task_ref','frozen Runtime Reviewer Task is required')
        reviewer_task=json.loads(reviewer_task_path.read_text(encoding='utf-8'))
        for result in results: runtime.validate_result_from_snapshot(base,reviewer_task,plan_cases[result['case_id']],result)
        proof.append({'batch_id':bid,'task_ref':task_ref,'results_ref':entry['results_ref'],'worker_session_id':worker_session,'reviewer_session_id':reviewer_session})
    if order_keys!=sorted(order_keys): fail('runtime_evidence','Runtime task references must preserve confirmed Batch order and per-Batch execution history order')
    required_refs=set()
    for bid in batch_order:
        state_path=base/'internal/execution/runtime-state'/f'{bid}-state.json'
        if not state_path.is_file(): continue
        state=json.loads(state_path.read_text(encoding='utf-8'))
        for entry in state.get('retest_history',[]):
            if entry.get('mode')=='product_regression' and entry.get('regression_id')==regression.get('regression_id'):
                required_refs.add(str((base/entry['task_ref']).resolve().relative_to(base)).replace('\\','/'))
    if seen_task_refs!=required_refs: fail('runtime_evidence','all and only real Runtime Worker/Reviewer attempts for this Regression must be bound')
    expected=set(regression.get('original_case_ids',[]))|set(regression.get('impact_case_ids',[]))
    if set(merged)!=expected: fail('runtime_evidence','final Runtime Worker Case scope must exactly equal original FAIL + impact scope')
    declared={r.get('case_id'):r for r in regression.get('results',[]) if isinstance(r,dict)}
    if set(declared)!=set(merged) or any(declared[cid]!=merged[cid] for cid in merged):
        fail('results','Regression input results must exactly equal results emitted by the Runtime Worker Tasks')
    regression['runtime_proof']=proof
    return merged

def validate_reg(v,baseline_plan,evidence_root=None):
    for k in [
        'regression_id','bug_ref','original_case_ids','impact_case_ids','cases','status',
        'target_environment','deployment_version','deployment_event_ref',
        'deployment_event_sha256','impact_analysis'
    ]:
        if k not in v: fail(k,'required')
    if not v['original_case_ids']: fail('original_case_ids','non-empty required')
    cases=v['cases']
    if not isinstance(cases,list) or not cases: fail('cases','regression task cases required')
    ids=[c.get('case_id') for c in cases]
    if any(not x for x in ids) or len(ids)!=len(set(ids)): fail('cases','unique case_ids required')
    required_ids=set(v['original_case_ids'])|set(v.get('impact_case_ids',[]))
    if set(ids)!=required_ids: fail('cases',f'must equal original + impact scope; missing={sorted(required_ids-set(ids))}, extra={sorted(set(ids)-required_ids)}')
    baseline=_baseline_case_map(baseline_plan)
    unknown=required_ids-set(baseline)
    if unknown: fail('cases',f'regression scope must come from confirmed execution plan: {sorted(unknown)}')
    target_env = v.get('target_environment')
    if not isinstance(target_env,str) or not target_env.strip():
        fail('target_environment','non-empty target_environment required')
    planned_env = baseline_plan.get('target_environment')
    if planned_env and isinstance(planned_env, dict):
        expected_env_id = planned_env.get('env_id')
        if target_env != expected_env_id:
            fail('target_environment', f'regression target_environment {target_env} does not match planned env {expected_env_id}')
    dep_version = v.get('deployment_version')
    if not isinstance(dep_version, str) or not dep_version.strip():
        fail('deployment_version', 'non-empty deployment_version required')
    dep_event = v.get('deployment_event_ref')
    if not isinstance(dep_event,str) or not dep_event.strip():
        fail('deployment_event_ref', 'non-empty deployment_event_ref required')
    dep_sha=v.get('deployment_event_sha256')
    if not isinstance(dep_sha,str) or len(dep_sha)!=64:
        fail('deployment_event_sha256','64-character SHA-256 required')
    impact = v.get('impact_analysis')
    if not isinstance(impact, dict):
        fail('impact_analysis', 'impact_analysis must be an object')
    required_impact={'old_pass_retest_needed','affected_pass_cases','data_recheck_needed','rationale'}
    if set(impact)!=required_impact:
        fail('impact_analysis',f'exact fields required: {sorted(required_impact)}')
    if not isinstance(impact['old_pass_retest_needed'], bool):
        fail('impact_analysis.old_pass_retest_needed', 'boolean required')
    affected=impact['affected_pass_cases']
    if not isinstance(affected,list) or any(not isinstance(cid,str) or not cid for cid in affected) or len(affected)!=len(set(affected)):
        fail('impact_analysis.affected_pass_cases', 'unique list of Case IDs required')
    scope_batches={baseline[cid].get('batch_id') for cid in required_ids}
    projected_affected={cid for cid in affected if cid in baseline and baseline[cid].get('batch_id') in scope_batches}
    if projected_affected!=set(v.get('impact_case_ids',[])):
        fail('impact_analysis.affected_pass_cases','impact_case_ids must equal deployment impact projected onto the Regression Batches')
    if not set(affected)<=set(baseline):
        fail('impact_analysis.affected_pass_cases','affected Cases must belong to the confirmed plan')
    if impact['old_pass_retest_needed'] != bool(affected):
        fail('impact_analysis.old_pass_retest_needed','must be true exactly when affected_pass_cases is non-empty')
    if not isinstance(impact['data_recheck_needed'],bool):
        fail('impact_analysis.data_recheck_needed','boolean required')
    if not isinstance(impact['rationale'],str) or not impact['rationale'].strip():
        fail('impact_analysis.rationale','non-empty rationale required')
    if not evidence_root:
        fail('deployment_event_ref','Run directory required to verify deployment event')
    base=Path(evidence_root).resolve(); event_path=(base/dep_event).resolve()
    if not _inside(event_path,base/'internal/execution/deployments'):
        fail('deployment_event_ref','must stay under internal/execution/deployments')
    if not event_path.is_file():
        fail('deployment_event_ref','deployment event file is missing')
    if _sha256(event_path)!=dep_sha:
        fail('deployment_event_sha256','does not match deployment event file')
    try: event=json.loads(event_path.read_text(encoding='utf-8'))
    except Exception as exc: fail('deployment_event_ref',f'invalid JSON: {exc}')
    if event.get('target_env')!=target_env:
        fail('deployment_event_ref','event target_env does not match Regression')
    if event.get('deployment_version')!=dep_version:
        fail('deployment_event_ref','event deployment_version does not match Regression')
    if event.get('impact_decision')!=impact:
        fail('deployment_event_ref','event impact_decision does not match Regression')

    # Regression is not allowed to redefine the original Case or primary execution method.
    for c in cases:
        cid=c['case_id']; base=baseline[cid]
        if 'primary_execution' in c and c.get('primary_execution')!=base.get('primary_execution'):
            fail(f'cases[{cid}].primary_execution',f'must preserve original Planning method {base.get("primary_execution")}')
        for field in ['steps','expected_results','target_action']:
            if field in c and c.get(field)!=base.get(field): fail(f'cases[{cid}].{field}','Regression cannot change the confirmed/planned Case')
    if v['status']=='completed':
        results=v.get('results')
        if not isinstance(results,list) or not results: fail('results','completed regression requires real results')
        rids=[r.get('case_id') for r in results]
        if len(rids)!=len(set(rids)) or set(rids)!=required_ids: fail('results','must match regression scope exactly')
        ctl=_load_execution_control(); result_by={r['case_id']:r for r in results}
        for cid in required_ids: ctl.validate(baseline[cid],result_by[cid],evidence_root=evidence_root)
        if not evidence_root: fail('runtime_evidence','Run directory required to verify real Worker/Reviewer receipts')
        _validate_regression_runtime(v,baseline_plan,evidence_root)
        failed_scope=sorted(cid for cid in required_ids if result_by[cid].get('status')!='PASS'); passed=not failed_scope
    else:
        failed_scope=[]; passed=False
    return {'ok':True,'regression_id':v['regression_id'],'regression_passed':passed,'failed_scope_case_ids':failed_scope}

CASE_LEDGER_REL='internal/execution/results/case-results-ledger.json'
def _load_ledger(run_dir):
    path=Path(run_dir)/CASE_LEDGER_REL
    if not path.exists(): fail('case_result_ledger',f'missing {CASE_LEDGER_REL}')
    return path,json.loads(path.read_text(encoding='utf-8'))
def _write_ledger(path,ledger):
    tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); tmp.replace(path)

def apply_defect_to_ledger(run_dir,v):
    out=validate(v); bug=out.get('bug_ref')
    sub=v.get('submission',{})
    if sub.get('status')=='failed' or not bug or not str(bug).strip():
        fail('submission.status',f'cannot apply defect {v.get("defect_id")} to ledger when submission status is failed or bug_ref is empty')
    path,ledger=_load_ledger(run_dir); rows=ledger.setdefault('cases',{})
    _,plan=_load_confirmed_plan(run_dir); planned=_baseline_case_map(plan)
    plan_batches={b.get('id'):b for b in plan.get('batches',[]) if isinstance(b,dict)}
    source_plan_batch=plan_batches.get(v['source_batch'])
    if not source_plan_batch: fail('source_batch','must exist in the confirmed Execution Plan')
    for cid in v['source_cases']:
        if cid not in planned or planned[cid].get('batch_id')!=v['source_batch']:
            fail(f'execution_plan.cases[{cid}].batch_id','source Case must belong to source_batch in the confirmed Execution Plan')
    source_kind = v.get('source_kind', 'runtime_case_fail')
    if source_kind not in {'runtime_case_fail', 'data_readiness'}:
        fail('source_kind', 'must be runtime_case_fail or data_readiness')

    roots=[]
    if source_kind == 'runtime_case_fail':
        runtime_path=Path(run_dir)/'internal/execution/runtime-state'/f'{v["source_batch"]}-state.json'
        if not runtime_path.is_file(): fail('source_batch.runtime_state','completed Runtime state is required to submit a formal Bug')
        runtime_state=json.loads(runtime_path.read_text(encoding='utf-8'))
        result_ref=runtime_state.get('final_results_ref') or runtime_state.get('worker_results_ref')
        if runtime_state.get('status')!='completed' or not result_ref: fail('source_batch.runtime_state','completed Worker/Reviewer Runtime evidence is required')
        runtime_root=Path(__file__).resolve().parents[2]/'test-execution-runtime/scripts'
        import sys
        if str(runtime_root) not in sys.path: sys.path.insert(0,str(runtime_root))
        runtime_mod=_load(runtime_root/'runtime_orchestrator.py','defect_runtime_receipt_validation')
        worker_mod=_load(runtime_root/'worker_review.py','defect_worker_receipt_validation')
        reviewer_mod=_load(runtime_root/'reviewer_contract.py','defect_reviewer_receipt_validation')
        final_mod=_load(Path(__file__).resolve().parents[2]/'test-result-review/scripts/final_review.py','defect_final_receipt_validation')
        run_sessions=set()
        runtime_cache={v['source_batch']:_load_reviewed_runtime_batch(Path(run_dir).resolve(),v['source_batch'],source_plan_batch,planned,final_mod,worker_mod,reviewer_mod,runtime_mod,run_sessions)}
        runtime_state,runtime_by,_=runtime_cache[v['source_batch']]
        for cid in v['source_cases']:
            if cid not in rows: fail(f'case_result_ledger.{cid}','defect source case is not initialized in ledger')
            item=rows[cid]
            if item.get('reviewer_confirmed') is not True or (item.get('final_result') or item.get('status'))!='FAIL':
                fail(f'case_result_ledger.{cid}','formal defect source must be a reviewer-confirmed FAIL')
            if item.get('batch_id')!=v['source_batch']: fail(f'case_result_ledger.{cid}.batch_id','does not match defect source_batch')
            if not isinstance(item.get('runtime_result'),dict) or item['runtime_result'].get('status')!='FAIL': fail(f'case_result_ledger.{cid}.runtime_result','real initial FAIL runtime result required')
            if runtime_by.get(cid)!=item['runtime_result']: fail(f'case_result_ledger.{cid}.runtime_result','must exactly match the latest canonical frozen Runtime result accepted by the independent Reviewer')
            roots.append((Path(run_dir)/'evidence'/v['source_batch']/cid).resolve())
    else:
        # data_readiness source_kind: cases are unexecuted / BLOCKED by data readiness failure
        runtime_cache = {}
        if 'data_readiness_review' in v: fail('data_readiness_review','inline self-reported review is forbidden')
        data_review=validate_data_readiness_review(run_dir,v.get('data_readiness_review_ref'),v['source_batch'],v['source_cases'])

        for cid in v['source_cases']:
            if cid not in rows: fail(f'case_result_ledger.{cid}','defect source case is not initialized in ledger')
            item=rows[cid]
            item_status = item.get('final_result') or item.get('status')
            if item_status not in {'BLOCKED', 'PENDING', 'NOT_EXECUTED'}:
                fail(f'case_result_ledger.{cid}', 'data_readiness bug source case must be BLOCKED or unexecuted, not fake FAIL')
            item['source_kind'] = 'data_readiness'
            item['status'] = 'BLOCKED'
            item['final_result'] = 'BLOCKED'
            item['reviewer_confirmed'] = True
            item['data_readiness_review'] = data_review
            item['data_readiness_review_ref'] = v['data_readiness_review_ref']
            item['deployment_version'] = json.loads((Path(run_dir)/'internal/state/run-status.json').read_text(encoding='utf-8')).get('current_deployment_version') or plan['target_environment']['initial_deployment_version']
            item['blocked_reason'] = data_review.get('blocked_reason') or v['payload'].get('title')
            roots.append((Path(run_dir)/'evidence'/v['source_batch']).resolve())

    for cid in v.get('blocked_case_ids',[]):
        item=rows.get(cid)
        if not item or item.get('reviewer_confirmed') is not True or (item.get('final_result') or item.get('status'))!='BLOCKED':
            fail(f'blocked_case_ids[{cid}]','must be a real Reviewer-confirmed BLOCKED Case in the ledger')
        runtime=item.get('runtime_result')
        if not isinstance(runtime,dict) or runtime.get('status')!='BLOCKED' or runtime.get('blocked_reason_type')!='upstream_case':
            fail(f'blocked_case_ids[{cid}]','must preserve Runtime BLOCKED(upstream_case) evidence')
        planned_case=planned.get(cid)
        blocked_batch=planned_case.get('batch_id') if planned_case else None
        if (not blocked_batch or item.get('batch_id')!=blocked_batch or
                not plan_batches.get(blocked_batch) or cid not in plan_batches[blocked_batch].get('case_ids',[])):
            fail(f'blocked_case_ids[{cid}].batch_id','ledger Case Batch must match the confirmed Execution Plan')
        if blocked_batch not in runtime_cache:
            runtime_cache[blocked_batch]=_load_reviewed_runtime_batch(Path(run_dir).resolve(),blocked_batch,plan_batches[blocked_batch],planned,final_mod,worker_mod,reviewer_mod,runtime_mod,run_sessions)
        blocked_state,blocked_results,blocked_task=runtime_cache[blocked_batch]
        canonical_runtime=blocked_results.get(cid)
        if canonical_runtime!=runtime: fail(f'blocked_case_ids[{cid}].runtime_result','must exactly match the latest canonical frozen Runtime result accepted by the independent Reviewer')
        dependencies=set(planned.get(cid,{}).get('dependencies',[]) or [])
        if not dependencies.intersection(v['source_cases']):
            fail(f'blocked_case_ids[{cid}]','must depend directly on one of the Bug source Cases before it can be queued for resume')
        dependency_context=blocked_task.get('dependency_context',{})
        for dep in dependencies:
            dep_case=planned.get(dep); dep_row=rows.get(dep); dep_context=dependency_context.get(dep) if isinstance(dependency_context,dict) else None
            if not dep_case or not dep_row or dep_row.get('reviewer_confirmed') is not True:
                fail(f'blocked_case_ids[{cid}].dependency_context.{dep}','must bind a confirmed planned dependency to its reviewed ledger result')
            dep_batch=dep_case.get('batch_id'); dep_batch_plan=plan_batches.get(dep_batch)
            if not dep_batch_plan: fail(f'blocked_case_ids[{cid}].dependency_context.{dep}.batch_id','dependency Batch must exist in confirmed plan')
            if dep_batch==blocked_batch:
                # Same-Batch dependencies are resolved from the ordered local
                # Runtime results and are intentionally omitted from the
                # cross-Batch dependency_context snapshot.
                dep_result=blocked_results.get(dep)
                dep_final=dep_row.get('final_result') or dep_row.get('status')
                dep_runtime=dep_row.get('runtime_result')
                if (dep_row.get('batch_id')!=dep_batch or not isinstance(dep_runtime,dict) or dep_runtime!=dep_result or
                        dep_final not in {'FAIL','BLOCKED','PASS','PASS_AFTER_FIX'} or
                        (dep_result or {}).get('status')!=dep_runtime.get('status')):
                    fail(f'blocked_case_ids[{cid}].dependency_context.{dep}','same-Batch dependency must match its canonical reviewed Runtime/Ledger result')
                continue
            if not isinstance(dep_context,dict):
                fail(f'blocked_case_ids[{cid}].dependency_context.{dep}','cross-Batch dependency requires its frozen Runtime context')
            if dep_batch not in runtime_cache:
                runtime_cache[dep_batch]=_load_reviewed_runtime_batch(Path(run_dir).resolve(),dep_batch,dep_batch_plan,planned,final_mod,worker_mod,reviewer_mod,runtime_mod,run_sessions)
            _,dep_results,_=runtime_cache[dep_batch]; dep_result=dep_results.get(dep)
            dep_final=dep_row.get('final_result') or dep_row.get('status')
            if (dep_row.get('batch_id')!=dep_batch or dep_context.get('case_id') not in (None,dep) or dep_context.get('batch_id')!=dep_batch or
                    dep_context.get('status')!=(dep_result or {}).get('status') or
                    dep_context.get('final_result')!=dep_final or dep_row.get('runtime_result')!=dep_result):
                fail(f'blocked_case_ids[{cid}].dependency_context.{dep}','must exactly match the confirmed plan Batch and canonical reviewed Runtime/Ledger dependency result')
    for ref in v['payload'].get('evidence_refs',[]): _run_evidence_file(run_dir,ref,roots,'payload.evidence_refs')
    ts=_now()
    for cid in v['source_cases']:
        rows[cid]['bug_ref']=bug; rows[cid]['defect_id']=v['defect_id']; rows[cid]['updated_at']=ts
    ledger['updated_at']=ts; _write_ledger(path,ledger)
    _dashboard(run_dir,{'type':'bug_submitted','batch_id':v['source_batch'],'bug_ref':bug,'case_ids':v['source_cases'],'blocked_case_ids':v.get('blocked_case_ids',[]),'stage':'defect-handling'})
    return {'ok':True,'defect_id':v['defect_id'],'bug_ref':bug,'updated_case_ids':v['source_cases']}

def apply_regression_to_ledger(run_dir,v):
    _,plan=_load_confirmed_plan(run_dir)
    out=validate_reg(v,baseline_plan=plan,evidence_root=run_dir)
    if out.get('regression_passed') is not True: fail('regression_passed',f'regression task scope not fully passed: {out.get("failed_scope_case_ids",[])}')
    path,ledger=_load_ledger(run_dir); rows=ledger.setdefault('cases',{}); result_by={r['case_id']:r for r in v['results']}; original=set(v['original_case_ids']); impact=set(v.get('impact_case_ids',[])); ts=_now()
    regression_execution={k:v[k] for k in [
        'regression_id','bug_ref','original_case_ids','impact_case_ids','cases','results','runtime_evidence',
        'target_environment','deployment_version','deployment_event_ref','deployment_event_sha256','impact_analysis'
    ]}
    regression_execution['status']='completed'
    # Historical FAIL and Bug link are facts from Runtime/Defect; Regression cannot manufacture them.
    for cid in original:
        if cid not in rows: fail(f'case_result_ledger.{cid}','case is not initialized in ledger')
        item=rows[cid]
        if item.get('reviewer_confirmed') is not True: fail(f'case_result_ledger.{cid}','original failed Case is not reviewer-confirmed')
        preserved_initial_fail=item.get('initial_result')=='FAIL' and isinstance(item.get('runtime_result'),dict) and item['runtime_result'].get('status')=='FAIL'
        preserved_resume_fail=item.get('initial_result')=='BLOCKED' and isinstance(item.get('blocked_runtime_result'),dict) and item['blocked_runtime_result'].get('status')=='BLOCKED' and isinstance(item.get('resume_result'),dict) and item['resume_result'].get('status')=='FAIL' and item.get('runtime_result')==item.get('resume_result')
        if not (preserved_initial_fail or preserved_resume_fail):
            fail(f'case_result_ledger.{cid}.initial_result','Regression requires a real preserved initial or resumed FAIL; it cannot create one')
        if item.get('bug_ref')!=v['bug_ref'] and item.get('existing_bug_ref')!=v['bug_ref']:
            fail(f'case_result_ledger.{cid}.bug_ref','Regression bug_ref must match the Bug already linked to the original FAIL')
        if (item.get('final_result') or item.get('status'))!='FAIL': fail(f'case_result_ledger.{cid}.final_result','original Case must still be FAIL before successful regression')
    for cid in impact:
        if cid not in rows: fail(f'case_result_ledger.{cid}','impact Case must already exist in the global Case ledger')
    source_batches=set();
    for cid in original|impact:
        item=rows[cid]; source_batches.add(item.get('batch_id'))
        hist=item.setdefault('regression_history',[]); hist.append({'regression_id':v['regression_id'],'bug_ref':v['bug_ref'],'result':result_by[cid],'at':ts,'scope':'original' if cid in original else 'impact','target_environment':v['target_environment'],'deployment_version':v['deployment_version'],'deployment_event_ref':v['deployment_event_ref'],'deployment_event_sha256':v['deployment_event_sha256']})
        item['regression_id']=v['regression_id']; item['bug_ref']=v['bug_ref']; item['regression_result']=result_by[cid]; item['reviewer_confirmed']=True; item['updated_at']=ts
        item['regression_execution']=regression_execution
        if cid in original:
            item['status']='PASS_AFTER_FIX'; item['final_result']='PASS_AFTER_FIX'; item['source']='regression_passed'
            dash_status='PASS_AFTER_FIX'
        else:
            # Preserve the original runtime_result/history; only final state changes after impact regression.
            item['status']='PASS'; item['final_result']='PASS'; item['source']='regression_impact_passed'
            dash_status='PASS'
        runtime_mod=_load(Path(__file__).resolve().parents[2]/'test-execution-runtime/scripts/runtime_orchestrator.py','defect_runtime_dashboard_summary')
        _dashboard(run_dir,{'type':'case_finished','batch_id':item.get('batch_id'),'case_id':cid,'status':dash_status,'actual_execution':result_by[cid].get('actual_execution'),'automation_summary':runtime_mod._automation_dashboard_summary(run_dir,result_by[cid]),'stage':'defect-handling'})
    ledger['updated_at']=ts; _write_ledger(path,ledger)
    _dashboard(run_dir,{'type':'regression_finished','bug_ref':v['bug_ref'],'status':'PASS','source_batch_ids':sorted(x for x in source_batches if x),'case_ids':sorted(original|impact),'stage':'defect-handling'})
    return {'ok':True,'regression_id':v['regression_id'],'updated_case_ids':sorted(original|impact)}


def apply_disposition_to_ledger(run_dir, disp):
    for k in ['defect_id', 'bug_ref', 'decision_source', 'disposition', 'operator', 'rationale', 'affected_case_ids']:
        if k not in disp: fail(k, 'required')
    if disp['disposition'] not in {'postponed', 'wontfix'}:
        fail('disposition', 'must be postponed or wontfix')
    path, ledger = _load_ledger(run_dir)
    rows = ledger.setdefault('cases', {})
    for field in ['defect_id','bug_ref','decision_source','operator','rationale']:
        if not isinstance(disp[field],str) or not disp[field].strip(): fail(field,'non-empty string required')
    linked={cid for cid,item in rows.items() if item.get('defect_id')==disp['defect_id'] and (item.get('bug_ref') or item.get('existing_bug_ref'))==disp['bug_ref']}
    affected=disp['affected_case_ids']
    if not isinstance(affected,list) or len(affected)!=len(set(affected)) or not linked or set(affected)!=linked:
        fail('affected_case_ids','must exactly equal Cases linked to this defect_id and bug_ref')
    for cid in affected:
        if (rows[cid].get('final_result') or rows[cid].get('status')) not in {'FAIL','BLOCKED'}:
            fail('affected_case_ids','disposition must preserve FAIL/BLOCKED facts')
    ts = _now()
    for cid in disp['affected_case_ids']:
        if cid not in rows: fail(f'case_result_ledger.{cid}', 'case not found in ledger')
        item = rows[cid]
        # Keep status as is (do not convert to PASS!)
        item['disposition'] = disp['disposition']
        item['disposition_record'] = {
            'defect_id': disp['defect_id'],
            'bug_ref': disp['bug_ref'],
            'decision_source': disp['decision_source'],
            'disposition': disp['disposition'],
            'operator': disp['operator'],
            'rationale': disp['rationale'],
            'timestamp': disp.get('timestamp') or ts,
            'target_version': disp.get('target_version')
        }
        item['updated_at'] = ts
    ledger['updated_at'] = ts
    # Atomically apply to dashboard first; if dashboard fails or rejects, ledger is not modified
    _dashboard(run_dir, {
        'type': 'defect_disposition_applied',
        'defect_id': disp['defect_id'],
        'bug_ref': disp['bug_ref'],
        'decision_source': disp['decision_source'],
        'disposition': disp['disposition'],
        'case_ids': disp['affected_case_ids'],
        'stage': 'defect-handling'
    })
    _write_ledger(path, ledger)
    return {'ok': True, 'defect_id': disp['defect_id'], 'disposition': disp['disposition'], 'affected_case_ids': disp['affected_case_ids']}


if __name__=='__main__':
    a=argparse.ArgumentParser()
    a.add_argument('--input',required=True)
    a.add_argument('--type',choices=['bug','regression','disposition'],default='bug')
    a.add_argument('--apply-run-dir')
    a.add_argument('--execution-plan')
    x=a.parse_args()
    v=json.loads(Path(x.input).read_text(encoding='utf-8'))
    if x.type=='bug': out=apply_defect_to_ledger(x.apply_run_dir,v) if x.apply_run_dir else validate(v)
    elif x.type=='disposition':
        if not x.apply_run_dir: fail('apply_run_dir','--apply-run-dir required for disposition')
        out=apply_disposition_to_ledger(x.apply_run_dir,v)
    else:
        if x.apply_run_dir: out=apply_regression_to_ledger(x.apply_run_dir,v)
        else:
            if not x.execution_plan: fail('execution_plan','standalone regression validation requires --execution-plan')
            out=validate_reg(v,json.loads(Path(x.execution_plan).read_text(encoding='utf-8')),evidence_root=Path(x.execution_plan).resolve().parents[2] if x.execution_plan else None)
    print(json.dumps(out,ensure_ascii=False))
