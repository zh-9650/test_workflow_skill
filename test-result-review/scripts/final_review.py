import argparse, importlib.util, json, hashlib
from pathlib import Path

FINAL={'PASS','FAIL','BLOCKED','PASS_AFTER_FIX'}
CONCLUSIONS={'ready','ready_with_risk','not_recommended','incomplete'}
WORKER_CHECKS=['all_cases_checked','all_expected_checked','execution_method_checked','evidence_binding_checked','failure_classification_checked','file_cleanup_checked']
REVIEWER_CHECKS=['completeness_checked','method_consistency_checked','judgement_checked','evidence_checked','abnormal_classification_checked']

def fail(path,msg): raise AssertionError(f'{path}: {msg}')
def _sha256(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _load(path,name):
    spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def _resolve(run_dir,ref,default):
    p=Path(ref or default); return p if p.is_absolute() else Path(run_dir)/p

def _validate_review_checks(batch):
    bid=batch.get('batch_id'); w=batch.get('worker_self_review',{}); r=batch.get('reviewer',{})
    if w.get('status')!='passed': fail(f'batch_results[{bid}].worker_self_review','must pass')
    for k in WORKER_CHECKS:
        if w.get('checks',{}).get(k) is not True: fail(f'batch_results[{bid}].worker_self_review.checks.{k}','must be true')
    if r.get('status')!='passed': fail(f'batch_results[{bid}].reviewer','must pass')
    for k in REVIEWER_CHECKS:
        if r.get('checks',{}).get(k) is not True: fail(f'batch_results[{bid}].reviewer.checks.{k}','must be true')

def _run_json(run,ref,path):
    p=Path(ref); p=(p if p.is_absolute() else run/p).resolve()
    try: p.relative_to(run.resolve())
    except ValueError: fail(path,'reference escapes the current Run')
    if not p.is_file(): fail(path,f'missing file {p}')
    try: return p,json.loads(p.read_text(encoding='utf-8'))
    except (OSError,ValueError) as e: fail(path,f'invalid JSON artifact: {e}')

def _validate_dispatch_receipt(run,receipt,role,task,result_status,path):
    if not isinstance(receipt,dict): fail(path,'completed host dispatch receipt is required')
    if receipt.get('agent_role')!=role: fail(path+'.agent_role',f'must be {role}')
    if receipt.get('receipt_status')!='completed': fail(path+'.receipt_status','must be completed')
    if receipt.get('task_id')!=task.get('task_id') or receipt.get('task_hash')!=task.get('task_hash'):
        fail(path,'must bind to the exact frozen dispatched Task')
    if not isinstance(receipt.get('agent_session_id'),str) or not receipt['agent_session_id'].strip():
        fail(path+'.agent_session_id','actual host Agent session identity required')
    if receipt.get('dispatch_source') not in {'codex_subagent_tool','claude_task_tool'}:
        fail(path+'.dispatch_source','supported host Agent dispatch source required')
    if not receipt.get('host_dispatch_ref'): fail(path+'.host_dispatch_ref','host dispatch reference required')
    if not receipt.get('started_at') or not receipt.get('finished_at'): fail(path,'started_at and finished_at are required')
    try:
        started=__import__('datetime').datetime.fromisoformat(receipt['started_at'].replace('Z','+00:00'))
        finished=__import__('datetime').datetime.fromisoformat(receipt['finished_at'].replace('Z','+00:00'))
    except (TypeError,ValueError): fail(path,'valid dispatch timestamps required')
    if finished<started: fail(path,'finished_at precedes started_at')
    if receipt.get('result_status')!=result_status: fail(path+'.result_status','must match the completed formal result')
    outputs=receipt.get('outputs')
    if not isinstance(outputs,dict) or not outputs: fail(path+'.outputs','completed receipt must bind output files and hashes')
    for ref,digest in outputs.items():
        target,_=_run_json(run,ref,path+'.outputs')
        if not isinstance(digest,str) or _sha256(target)!=digest: fail(path+'.outputs','output file hash mismatch')
    return receipt['agent_session_id']

def _result_status_summary(results):
    cases={r['case_id']:r['status'] for r in results}
    statuses=set(cases.values())
    if statuses=={'PASS'}: overall='PASS'
    elif 'FAIL' in statuses: overall='FAIL'
    elif 'NEEDS_REVIEW' in statuses: overall='NEEDS_REVIEW'
    elif 'BLOCKED' in statuses: overall='BLOCKED'
    elif len(statuses)==1: overall=next(iter(statuses))
    else: overall='MIXED'
    return {'overall':overall,'cases':cases}

def _validate_reviewer_output(run,receipt,reviewer_task,review,reviewer_session,path):
    outputs=receipt.get('outputs',{}) if isinstance(receipt,dict) else {}
    if not isinstance(outputs,dict) or len(outputs)!=1:
        fail(path+'.outputs','Reviewer receipt must bind exactly one immutable result file')
    matched=False
    for ref in outputs:
        _,payload=_run_json(run,ref,path+'.outputs')
        if payload!=review:
            fail(path+'.outputs','receipt-bound Reviewer result differs from the result accepted by Runtime state')
        if payload.get('reviewer_task_id')!=reviewer_task.get('task_id'):
            fail(path+'.outputs','Reviewer result must bind the frozen Reviewer Task')
        if payload.get('agent_session_id')!=reviewer_session:
            fail(path+'.outputs','Reviewer result must identify the dispatched Reviewer session')
        matched=True
    if not matched: fail(path+'.outputs','Reviewer result file is required')

def _validate_runtime_receipts(run,bid,state,task,results,worker_mod,reviewer_mod,runtime_mod,run_sessions=None):
    if run_sessions is None: run_sessions=set()
    dashboard_path=run/'dashboard/dashboard-data.json'
    if not dashboard_path.is_file(): fail('dashboard','dashboard-data.json is required to validate Batch/Retest receipts')
    dashboard=json.loads(dashboard_path.read_text(encoding='utf-8'))
    dash_batch_rows={row.get('id'):row for row in dashboard.get('batches',[]) if row.get('id')}
    results_ref=state.get('worker_results_ref'); self_ref=state.get('worker_self_review_ref')
    worker_task_path,worker_task=_run_json(run,state.get('task_ref',''),f'batch[{bid}].task_ref')
    if worker_task!=task: fail(f'batch[{bid}].task_ref','loaded Worker Task differs from the validated Task')
    if not results_ref or not self_ref: fail(f'batch[{bid}]','Worker results and self-review references are required')
    result_path,_=_run_json(run,results_ref,f'batch[{bid}].worker_results_ref')
    self_path,self_review=_run_json(run,self_ref,f'batch[{bid}].worker_self_review_ref')
    worker_receipt=state.get('worker_dispatch_receipt') or {}
    worker_session=_validate_dispatch_receipt(run,worker_receipt,'execution_worker',task,_result_status_summary(results),f'batch[{bid}].worker_dispatch_receipt')
    if worker_session in run_sessions:
        fail(f'batch[{bid}].worker_dispatch_receipt.agent_session_id','host Agent session must be unique across the entire Run')
    if worker_receipt.get('outputs',{}).get(str(results_ref))!=_sha256(result_path):
        fail(f'batch[{bid}].worker_dispatch_receipt.outputs','must include the actual Worker results file hash')
    if worker_receipt.get('outputs',{}).get(str(self_ref))!=_sha256(self_path):
        fail(f'batch[{bid}].worker_dispatch_receipt.outputs','must include the actual Worker self-review file hash')
    worker_mod.validate(self_review,task['case_order'],results,task_id=task['task_id'],task_hash=task['task_hash'],worker_session_id=worker_session,results_sha256=_sha256(result_path))
    reviewer_task_path,reviewer_task=_run_json(run,state.get('reviewer_task_ref',''),f'batch[{bid}].reviewer_task_ref')
    if reviewer_task_path is None: fail(f'batch[{bid}].reviewer_task_ref','required')
    runtime_mod._validate_reviewer_task_hash(reviewer_task)
    if reviewer_task.get('results_sha256')!=_sha256(result_path) or reviewer_task.get('worker_self_review_sha256')!=_sha256(self_path):
        fail(f'batch[{bid}].reviewer_task','Worker results/self-review hashes differ from frozen Reviewer input')
    runtime_mod._validate_frozen_artifacts(run,reviewer_task,task,results)
    reviewer=state.get('reviewer') or {}
    review_history=state.get('review_history',[])
    initial_review=next((item.get('review') for item in review_history if item.get('type')=='initial_or_batch_review'),reviewer)
    if review_history:
        last_local_review=next((item.get('review') for item in reversed(review_history) if item.get('type')=='local_retest_review'),None)
        expected_final_review=(runtime_mod._compose_reviewer_review(initial_review,last_local_review,task['case_order'])
                               if last_local_review else initial_review)
        if reviewer!=expected_final_review:
            fail(f'batch[{bid}].reviewer','final aggregate Reviewer state must reconcile to initial and latest local Retest reviews')
    reviewer_receipt=state.get('reviewer_dispatch_receipt') or {}
    reviewer_session=_validate_dispatch_receipt(run,reviewer_receipt,'result_reviewer',reviewer_task,reviewer.get('status'),f'batch[{bid}].reviewer_dispatch_receipt')
    if worker_session==reviewer_session: fail(f'batch[{bid}].agent_sessions','Worker and Reviewer must be different host sessions')
    if reviewer_session in run_sessions:
        fail(f'batch[{bid}].reviewer_dispatch_receipt.agent_session_id','host Agent session must be unique across the entire Run')
    run_sessions.update({worker_session,reviewer_session})
    recovery_history=reviewer_task.get('worker_recovery_history',[])
    if worker_receipt.get('recovery_sequence') and not recovery_history:
        fail(f'batch[{bid}].worker_recovery_history','replacement Worker receipt requires its complete frozen recovery history')
    recovery_sessions={worker_session,reviewer_session}
    for recovery_index,recovery in enumerate(recovery_history):
        recovery_prefix=f'batch[{bid}].worker_recovery_history[{recovery_index}]'
        previous_session=(recovery.get('previous_worker_receipt') or {}).get('agent_session_id')
        replacement_session=(recovery.get('replacement_worker_receipt') or {}).get('agent_session_id')
        if not previous_session or previous_session in recovery_sessions or previous_session in run_sessions:
            fail(recovery_prefix+'.previous_worker_receipt','interrupted Worker session must be recorded once and remain distinct')
        if recovery_index==len(recovery_history)-1:
            if replacement_session!=worker_session:
                fail(recovery_prefix+'.replacement_worker_receipt','latest replacement must be the Worker that produced this Batch')
        elif not replacement_session or replacement_session in recovery_sessions or replacement_session in run_sessions:
            fail(recovery_prefix+'.replacement_worker_receipt','intermediate replacement session must be recorded once and remain distinct')
        recovery_sessions.add(previous_session)
        run_sessions.add(previous_session)
        if recovery_index<len(recovery_history)-1:
            recovery_sessions.add(replacement_session)
            run_sessions.add(replacement_session)
    _validate_reviewer_output(run,reviewer_receipt,reviewer_task,initial_review,reviewer_session,f'batch[{bid}].reviewer_dispatch_receipt')
    reviewer_mod.validate(initial_review,task['case_order'],results,reviewer_task=reviewer_task,worker_session_id=worker_session,reviewer_session_id=reviewer_session,results_sha256=reviewer_task.get('results_sha256'))

    history=state.get('retest_history',[]); retest_tasks=state.get('retest_tasks',[])
    if state.get('active_retest') is not None: fail(f'batch[{bid}].active_retest','pending Retest/Regression work prevents Final Review')
    if len(history)!=len(retest_tasks): fail(f'batch[{bid}].retest_history','every generated Retest Task must have a completed Worker/Reviewer history')
    seen_tasks=set()
    all_sessions={worker_session,reviewer_session}
    for index,entry in enumerate(history):
        prefix=f'batch[{bid}].retest_history[{index}]'
        task_path,rtask=_run_json(run,entry.get('task_ref',''),prefix+'.task_ref')
        task_ref=str(task_path.relative_to(run.resolve())).replace('\\','/')
        if task_ref not in {str(x).replace('\\','/') for x in retest_tasks}: fail(prefix+'.task_ref','must match a generated Retest Task')
        if task_ref in seen_tasks: fail(prefix+'.task_ref','duplicate Retest history entry')
        seen_tasks.add(task_ref)
        _,rresults=_run_json(run,entry.get('results_ref',''),prefix+'.results_ref')
        _,rself=_run_json(run,entry.get('self_review_ref',''),prefix+'.self_review_ref')
        _,rtask_review=_run_json(run,entry.get('reviewer_task_ref',''),prefix+'.reviewer_task_ref')
        runtime_mod._validate_reviewer_task_hash(rtask_review)
        rworker=entry.get('worker_dispatch_receipt') or {}; rreviewer=entry.get('reviewer_dispatch_receipt') or {}; rreview=entry.get('review') or {}
        rresults_path,_=_run_json(run,entry.get('results_ref',''),prefix+'.results_ref')
        rself_path,_=_run_json(run,entry.get('self_review_ref',''),prefix+'.self_review_ref')
        rworker_session=_validate_dispatch_receipt(run,rworker,'execution_worker',rtask,_result_status_summary(rresults),prefix+'.worker_dispatch_receipt')
        if rworker.get('outputs',{}).get(str(entry.get('results_ref')))!=_sha256(rresults_path): fail(prefix+'.worker_dispatch_receipt.outputs','must bind the Retest results hash')
        if rworker.get('outputs',{}).get(str(entry.get('self_review_ref')))!=_sha256(rself_path): fail(prefix+'.worker_dispatch_receipt.outputs','must bind the Retest self-review hash')
        if rtask_review.get('results_sha256')!=_sha256(rresults_path) or rtask_review.get('worker_self_review_sha256')!=_sha256(rself_path): fail(prefix+'.reviewer_task','Retest hashes differ from frozen Reviewer input')
        runtime_mod._validate_frozen_artifacts(run,rtask_review,rtask,rresults)
        recovery_history=rtask_review.get('worker_recovery_history',[])
        for recovery_index,recovery in enumerate(recovery_history):
            recovery_prefix=f'{prefix}.worker_recovery_history[{recovery_index}]'
            previous_session=(recovery.get('previous_worker_receipt') or {}).get('agent_session_id')
            replacement_session=(recovery.get('replacement_worker_receipt') or {}).get('agent_session_id')
            if not previous_session or previous_session in all_sessions or previous_session in run_sessions:
                fail(recovery_prefix+'.previous_worker_receipt','interrupted Worker session must be recorded once and remain distinct')
            if recovery_index==len(recovery_history)-1:
                if replacement_session!=rworker_session:
                    fail(recovery_prefix+'.replacement_worker_receipt','latest replacement must be the Worker that produced this Retest')
            elif not replacement_session or replacement_session in all_sessions or replacement_session in run_sessions:
                fail(recovery_prefix+'.replacement_worker_receipt','intermediate replacement session must be recorded once and remain distinct')
            all_sessions.add(previous_session)
            run_sessions.add(previous_session)
            if recovery_index<len(recovery_history)-1:
                all_sessions.add(replacement_session); run_sessions.add(replacement_session)
        rreviewer_session=_validate_dispatch_receipt(run,rreviewer,'result_reviewer',rtask_review,rreview.get('status'),prefix+'.reviewer_dispatch_receipt')
        if (rworker_session==rreviewer_session or rworker_session in all_sessions or rreviewer_session in all_sessions
            or rworker_session in run_sessions or rreviewer_session in run_sessions):
            fail(prefix+'.agent_sessions','each Retest Worker and Reviewer must use distinct new sessions')
        all_sessions.update({rworker_session,rreviewer_session})
        run_sessions.update({rworker_session,rreviewer_session})
        worker_mod.validate(rself,rtask['case_order'],rresults,task_id=rtask['task_id'],task_hash=rtask['task_hash'],worker_session_id=rworker_session,results_sha256=_sha256(rresults_path))
        _validate_reviewer_output(run,rreviewer,rtask_review,rreview,rreviewer_session,prefix+'.reviewer_dispatch_receipt')
        reviewer_mod.validate(rreview,rtask['case_order'],rresults,reviewer_task=rtask_review,worker_session_id=rworker_session,reviewer_session_id=rreviewer_session,results_sha256=rtask_review.get('results_sha256'))
    if seen_tasks!={str(x).replace('\\','/') for x in retest_tasks}:
        fail(f'batch[{bid}].retest_history','does not account for every generated Retest Task')
    if history:
        latest=history[-1]; latest_row=dash_batch_rows[bid]
        if latest_row.get('last_retest_worker_session_id')!=(latest.get('worker_dispatch_receipt') or {}).get('agent_session_id'):
            fail(f'dashboard.batches[{bid}].last_retest_worker_session_id','must match the latest Runtime Retest Worker receipt')
        if latest_row.get('last_retest_reviewer_session_id')!=(latest.get('reviewer_dispatch_receipt') or {}).get('agent_session_id'):
            fail(f'dashboard.batches[{bid}].last_retest_reviewer_session_id','must match the latest Runtime Retest Reviewer receipt')
        if latest_row.get('last_retest_worker_receipt_status')!='completed' or latest_row.get('last_retest_reviewer_receipt_status')!='completed':
            fail(f'dashboard.batches[{bid}].last_retest_receipt_status','latest Retest Worker and Reviewer receipts must be completed')

def _validate_case_result_snapshot(run,plan_case,result,runtime_states,runtime_mod):
    bid=plan_case.get('batch_id'); state=runtime_states.get(bid,{})
    candidates=[]
    if state.get('task_ref') and state.get('reviewer_task_ref'):
        task_path=(run/state['task_ref']).resolve()
        task=json.loads(task_path.read_text(encoding='utf-8'))
        if task.get('task_id')==result.get('task_id'):
            candidates.append(state['reviewer_task_ref'])
    for entry in state.get('retest_history',[]):
        task_path=(run/entry.get('task_ref','')).resolve()
        results_path=(run/entry.get('results_ref','')).resolve()
        if not task_path.is_file() or not results_path.is_file(): continue
        task=json.loads(task_path.read_text(encoding='utf-8'))
        results=json.loads(results_path.read_text(encoding='utf-8'))
        if task.get('task_id')==result.get('task_id') and any(row==result for row in results):
            candidates.append(entry.get('reviewer_task_ref'))
    if len(candidates)!=1 or not candidates[0]:
        fail(f'{result.get("case_id")}.runtime_snapshot','result must map to exactly one completed Worker/Reviewer artifact snapshot')
    reviewer_path=(run/candidates[0]).resolve()
    try: reviewer_path.relative_to(run.resolve())
    except ValueError: fail(f'{result.get("case_id")}.runtime_snapshot','Reviewer Task must stay within the current Run')
    if not reviewer_path.is_file(): fail(f'{result.get("case_id")}.runtime_snapshot','Reviewer Task snapshot is missing')
    reviewer_task=json.loads(reviewer_path.read_text(encoding='utf-8'))
    runtime_mod.validate_result_from_snapshot(run,reviewer_task,plan_case,result)

def _validate_ledger_regression(item,cid,regression_result,plan,run,defect_mod):
    regression=item.get('regression_execution')
    if not isinstance(regression,dict) or regression.get('status')!='completed':
        fail(f'{cid}.regression_execution','completed Runtime Worker/Reviewer Regression evidence required')
    if regression.get('regression_id')!=item.get('regression_id') or regression.get('bug_ref')!=item.get('bug_ref'):
        fail(f'{cid}.regression_execution','Regression and Bug identity must match the Case ledger')
    checked=defect_mod.validate_reg(regression,baseline_plan=plan,evidence_root=run)
    if checked.get('regression_passed') is not True:
        fail(f'{cid}.regression_execution','Runtime Regression scope is not fully PASS')
    by_case={r.get('case_id'):r for r in regression.get('results',[]) if isinstance(r,dict)}
    if by_case.get(cid)!=regression_result:
        fail(f'{cid}.regression_result','must equal the result bound to this Case in the verified Runtime Regression')

def derive_assessment(rows,plan_by):
    unresolved=[r for r in rows if r['status']=='FAIL']; blocked=[r for r in rows if r['status']=='BLOCKED']
    core=[r for r in rows if plan_by[r['case_id']].get('core_flow') or plan_by[r['case_id']].get('core_flow_id')]
    core_ok=all(r['status'] in {'PASS','PASS_AFTER_FIX'} for r in core) if core else True
    critical=[r for r in unresolved if r.get('severity') in {'critical','blocker','major'}]
    if critical or not core_ok: conclusion='not_recommended'
    elif blocked or unresolved: conclusion='ready_with_risk'
    else: conclusion='ready'
    return {'coverage_complete':True,'core_flow_passed':core_ok,'unresolved_critical_defects':len(critical),'blocked_scope':[r['case_id'] for r in blocked],'regression_complete':True,'conclusion':conclusion}

def validate(v,run_dir=None):
    if run_dir is None: run_dir=v.get('run_dir')
    if not run_dir: fail('run_dir','required so Final Review can reopen real Planning/Runtime/Evidence files')
    run=Path(run_dir)
    plan_path=_resolve(run,v.get('execution_plan_ref'),'internal/execution/execution-plan.json')
    ledger_path=_resolve(run,v.get('case_result_ledger_ref'),'internal/execution/results/case-results-ledger.json')
    if not plan_path.exists(): fail('execution_plan_ref',f'missing {plan_path}')
    if not ledger_path.exists(): fail('case_result_ledger_ref',f'missing {ledger_path}')
    plan=json.loads(plan_path.read_text(encoding='utf-8')); ledger=json.loads(ledger_path.read_text(encoding='utf-8'))
    state_path=run/'internal/state/run-status.json'
    if not state_path.exists(): fail('run_status','run-status.json missing')
    run_state=json.loads(state_path.read_text(encoding='utf-8'))
    if run_state.get('pending_resume_batches'):
        fail('run_status.pending_resume_batches','Cases unblocked by regression still require data recheck, execution and Reviewer closure')
    if run_state.get('pending_resume'):
        fail('run_status.pending_resume','a regression-unblocked Batch resume is still active')
    stale_blocked_items=[x for x in run_state.get('blocked_items',[]) if x.get('case_id') in ledger.get('cases',{}) and (ledger['cases'][x['case_id']].get('final_result') or ledger['cases'][x['case_id']].get('status'))!='BLOCKED']
    if stale_blocked_items: fail('run_status.blocked_items','resolved Cases must be removed from the active blocked queue before Final Review')
    plan_binding=run_state.get('confirmation_bindings',{}).get('execution-plan')
    if not plan_binding: fail('execution_plan_ref','execution plan is not confirmed/bound')
    if Path(plan_binding.get('contract_path','')).resolve()!=plan_path.resolve() or _sha256(plan_path)!=plan_binding.get('contract_sha256'):
        fail('execution_plan_ref','confirmed execution plan changed after confirmation')
    case_binding=run_state.get('confirmation_bindings',{}).get('test-cases')
    if not case_binding: fail('confirmed_cases','confirmed test-case binding missing')
    if run_state.get('confirmations',{}).get('test_cases_confirmed') is not True or run_state.get('confirmations',{}).get('test_cases_self_review_passed') is not True:
        fail('confirmed_cases','Router must show current test-case self-review and user-confirmation flags')
    case_artifact=run_state.get('artifacts',{}).get('test-cases')
    if not case_artifact: fail('confirmed_cases','registered test-case artifact record missing')
    for field,path_field,hash_field in (('path','path','sha256'),('contract_path','contract_path','contract_sha256'),('review_path','review_path','review_sha256')):
        bound=Path(case_binding.get(field,'')); registered=Path(case_artifact.get(path_field,''))
        if not bound.is_file() or not registered.is_file() or bound.resolve()!=registered.resolve():
            fail('confirmed_cases',f'Router test-case {field} path is missing or does not match registration')
        if _sha256(bound)!=case_binding.get(hash_field) or _sha256(registered)!=case_artifact.get(hash_field):
            fail('confirmed_cases',f'Router test-case {field} hash is stale or does not match registration')
    confirmed_cases_path=Path(case_binding.get('contract_path',''))
    if not confirmed_cases_path.exists() or _sha256(confirmed_cases_path)!=case_binding.get('contract_sha256'):
        fail('confirmed_cases','confirmed test cases changed or disappeared')
    confirmed_design=json.loads(confirmed_cases_path.read_text(encoding='utf-8'))
    confirmed_inputs={}
    for kind in ('business-understanding','test-points'):
        binding=run_state.get('confirmation_bindings',{}).get(kind)
        if not binding: fail('confirmed_cases',f'{kind} confirmation binding missing')
        source=Path(binding.get('contract_path',''))
        if not source.exists() or _sha256(source)!=binding.get('contract_sha256'):
            fail('confirmed_cases',f'{kind} contract changed or disappeared')
        confirmed_inputs[kind]=json.loads(source.read_text(encoding='utf-8'))
    repo_root=Path(__file__).resolve().parents[2]
    case_mod=_load(repo_root/'test-case-design/scripts/case_contract.py','final_confirmed_case_contract')
    case_mod.validate(confirmed_design,confirmed_inputs['test-points'],confirmed_inputs['business-understanding'],require_confirmed=True)
    confirmed_cases={'cases':case_mod.project_execution_cases(confirmed_design)}
    planning_mod=_load(Path(__file__).resolve().parents[2]/'test-execution-planning/scripts/execution_plan.py','final_execution_plan_contract')
    planning_mod.validate(plan,require_confirmed=False,confirmed_cases=confirmed_cases,confirmed_cases_sha256=case_binding['contract_sha256'])
    plan_by={c['case_id']:c for c in plan.get('cases',[])}; plan_ids=set(plan_by)
    formal=set(v.get('formal_case_ids',[])); planned=set(v.get('planned_case_ids',[])); rows=v.get('results',[]); rid={r.get('case_id') for r in rows}
    if not formal or not planned or not rows: fail('run','formal_case_ids/planned_case_ids/results required')
    if len(rows)!=len(rid): fail('results','duplicate final result case_id')
    if formal!=planned or formal!=rid or formal!=plan_ids: fail('case_sets','formal/planned/result must exactly equal the real execution plan case set')
    ledger_rows=ledger.get('cases',{})
    if set(ledger_rows)!=plan_ids: fail('case_result_ledger','ledger case set must exactly equal the plan')

    runtime_root=Path(__file__).resolve().parents[2]/'test-execution-runtime/scripts'
    import sys
    if str(runtime_root) not in sys.path: sys.path.insert(0,str(runtime_root))
    execution=_load(runtime_root/'execution_control.py','final_execution_control')
    reviewer_mod=_load(runtime_root/'reviewer_contract.py','final_reviewer_contract')
    worker_mod=_load(runtime_root/'worker_review.py','final_worker_review')
    runtime_mod=_load(runtime_root/'runtime_orchestrator.py','final_runtime_orchestrator')
    defect_mod=_load(Path(__file__).resolve().parents[2]/'test-defect-handling/scripts/defect_contract.py','final_defect_regression_contract')

    # Reopen actual batch state files rather than trusting only final-summary flags.
    planned_batches={b['id']:b for b in plan.get('batches',[])}
    supplied_batches={b.get('batch_id'):b for b in v.get('batch_results',[])}
    if set(supplied_batches)!=set(planned_batches): fail('batch_results','every planned batch requires one final batch result')
    runtime_states={}; run_sessions=set()
    for bid,batch in planned_batches.items():
        state_path=run/f'internal/execution/runtime-state/{bid}-state.json'
        if not state_path.exists(): fail(f'batch_results[{bid}]',f'missing runtime state {state_path}')
        state=json.loads(state_path.read_text(encoding='utf-8'))
        runtime_states[bid]=state
        if state.get('status')!='completed': fail(f'batch_results[{bid}].status','runtime batch state is not completed')
        task_path=run/state.get('task_ref','')
        results_path=run/state.get('worker_results_ref','')
        if not task_path.exists() or not results_path.exists(): fail(f'batch_results[{bid}]','task/results file missing')
        task=json.loads(task_path.read_text(encoding='utf-8')); detailed=json.loads(results_path.read_text(encoding='utf-8'))
        _validate_runtime_receipts(run,bid,state,task,detailed,worker_mod,reviewer_mod,runtime_mod,run_sessions)
        _validate_review_checks(supplied_batches[bid])

    summary_by={r['case_id']:r for r in rows}
    for cid,pc in plan_by.items():
        summary=summary_by[cid]; status=summary.get('status')
        if status not in FINAL: fail(f'{cid}.status','non-final status remains')
        item=ledger_rows[cid]
        if item.get('reviewer_confirmed') is not True: fail(f'{cid}.ledger','final ledger result must be reviewer-confirmed')
        ledger_status=item.get('final_result') or item.get('status')
        if ledger_status!=status: fail(f'{cid}.status',f'final summary {status} != reviewer-confirmed ledger {ledger_status}')
        if status=='PASS_AFTER_FIX':
            original=item.get('runtime_result')
            regression=item.get('regression_result')
            initial_failed=(item.get('initial_result')=='FAIL' and isinstance(original,dict) and original.get('status')=='FAIL')
            resumed_failed=(item.get('initial_result')=='BLOCKED' and isinstance(item.get('blocked_runtime_result'),dict) and item['blocked_runtime_result'].get('status')=='BLOCKED' and isinstance(item.get('resume_result'),dict) and item['resume_result'].get('status')=='FAIL' and item.get('runtime_result')==item.get('resume_result'))
            if not (initial_failed or resumed_failed): fail(f'{cid}.initial_result','PASS_AFTER_FIX requires a preserved initial or resumed FAIL and its original BLOCKED history when applicable')
            if not item.get('bug_ref'): fail(f'{cid}.bug_ref','PASS_AFTER_FIX requires bug_ref in ledger')
            if not isinstance(original,dict) or original.get('status')!='FAIL': fail(f'{cid}.runtime_result','initial FAIL runtime result required')
            _validate_case_result_snapshot(run,pc,original,runtime_states,runtime_mod)
            if not isinstance(regression,dict) or regression.get('status')!='PASS': fail(f'{cid}.regression_result','real PASS regression result required')
            _validate_case_result_snapshot(run,pc,regression,runtime_states,runtime_mod)
            _validate_ledger_regression(item,cid,regression,plan,run,defect_mod)
        elif item.get('source')=='regression_impact_passed':
            regression=item.get('regression_result')
            if not isinstance(regression,dict) or regression.get('status')!='PASS': fail(f'{cid}.regression_result','impact regression requires a real PASS result')
            _validate_case_result_snapshot(run,pc,regression,runtime_states,runtime_mod)
            _validate_ledger_regression(item,cid,regression,plan,run,defect_mod)
        elif item.get('source')=='unblocked_cases_reviewer_passed':
            blocked=item.get('blocked_runtime_result'); resumed=item.get('resume_result')
            if item.get('initial_result')!='BLOCKED' or not isinstance(blocked,dict) or blocked.get('status')!='BLOCKED':
                fail(f'{cid}.blocked_runtime_result','the original Reviewer-confirmed BLOCKED result must be preserved')
            if not isinstance(resumed,dict) or resumed.get('status')!='PASS' or item.get('runtime_result')!=resumed:
                fail(f'{cid}.resume_result','final PASS must equal the new Reviewer-confirmed resume execution')
            if resumed.get('task_id')!=item.get('resume_task_id') or resumed.get('task_hash')!=item.get('resume_task_hash'):
                fail(f'{cid}.resume_result','must bind the frozen resume Runtime Task recorded in the ledger')
            _validate_case_result_snapshot(run,pc,blocked,runtime_states,runtime_mod); _validate_case_result_snapshot(run,pc,resumed,runtime_states,runtime_mod)
            bid=pc.get('batch_id'); state=runtime_states.get(bid,{})
            matches=[]
            for entry in state.get('retest_history',[]):
                if entry.get('mode')!='resume_after_regression': continue
                _,results=_run_json(run,entry.get('results_ref',''),f'{cid}.resume.results_ref')
                if any(r.get('case_id')==cid and r==resumed for r in results): matches.append(entry)
            if len(matches)!=1: fail(f'{cid}.resume_history','must match exactly one real resumed Worker/Reviewer result chain')
        else:
            runtime=item.get('runtime_result')
            if not isinstance(runtime,dict): fail(f'{cid}.runtime_result','full runtime result required in case ledger')
            _validate_case_result_snapshot(run,pc,runtime,runtime_states,runtime_mod)
        if status=='FAIL' and not (item.get('bug_ref') or item.get('existing_bug_ref') or summary.get('bug_ref') or summary.get('existing_bug_ref') or summary.get('no_bug_reason')): fail(f'{cid}.FAIL','bug closure required')
        if status=='BLOCKED' and not (summary.get('blocked_reason') or item.get('runtime_result',{}).get('blocked_reason')): fail(f'{cid}.blocked_reason','required')

    dashboard_path=run/'dashboard/dashboard-data.json'
    if not dashboard_path.is_file(): fail('dashboard','dashboard-data.json is required for Final Review reconciliation')
    dashboard=json.loads(dashboard_path.read_text(encoding='utf-8'))
    dash_batch_rows={b.get('id'):b for b in dashboard.get('batches',[])}
    dash_batches={bid:row.get('status') for bid,row in dash_batch_rows.items()}
    state_batches=run_state.get('batch_status',{})
    for bid in planned_batches:
        if dash_batches.get(bid)!='completed': fail(f'dashboard.batches[{bid}]','must be completed before Final Review')
        if state_batches.get(bid)!='completed': fail(f'run_status.batch_status[{bid}]','must be completed and consistent with Dashboard before Final Review')
        state=json.loads((run/'internal/execution/runtime-state'/f'{bid}-state.json').read_text(encoding='utf-8'))
        worker_rows=json.loads((run/(state.get('final_results_ref') or state['worker_results_ref'])).read_text(encoding='utf-8'))
        if dash_batch_rows[bid].get('worker_session_id')!=(state.get('worker_dispatch_receipt') or {}).get('agent_session_id'):
            fail(f'dashboard.batches[{bid}].worker_session_id','must match the actual Worker receipt')
        if dash_batch_rows[bid].get('reviewer_session_id')!=(state.get('reviewer_dispatch_receipt') or {}).get('agent_session_id'):
            fail(f'dashboard.batches[{bid}].reviewer_session_id','must match the actual Reviewer receipt')
        if dash_batch_rows[bid].get('worker_receipt_status')!='completed' or dash_batch_rows[bid].get('reviewer_receipt_status')!='completed':
            fail(f'dashboard.batches[{bid}].receipt_status','Worker and Reviewer receipts must both be completed')
        expected_worker_status=_result_status_summary(json.loads((run/state['worker_results_ref']).read_text(encoding='utf-8')))
        if dash_batch_rows[bid].get('worker_result_status')!=expected_worker_status:
            fail(f'dashboard.batches[{bid}].worker_result_status','must match the Worker formal result summary')
        if dash_batch_rows[bid].get('reviewer_result_status')!=(state.get('reviewer') or {}).get('status'):
            fail(f'dashboard.batches[{bid}].reviewer_result_status','must match the accepted Reviewer result')
    pending_regressions=[d.get('id') for d in dashboard.get('defects',[]) if d.get('status') in {'pending_regression','regression_running'}]
    if pending_regressions: fail('dashboard.defects','pending Regression prevents Final Review: '+', '.join(str(x) for x in pending_regressions))
    dashboard_cases={c.get('id'):c for c in dashboard.get('cases',[])}
    if set(dashboard_cases)!=plan_ids: fail('dashboard.cases','Dashboard Case set must exactly match confirmed Planning')
    for cid,pc in plan_by.items():
        row=dashboard_cases[cid]; ledger_status=ledger_rows[cid].get('final_result') or ledger_rows[cid].get('status')
        if row.get('status')!=ledger_status: fail(f'dashboard.cases[{cid}].status','must match the reviewer-confirmed Case ledger')
        automation=pc.get('automation') or {}
        if automation.get('required') is True:
            if row.get('planned_execution')!=pc.get('primary_execution') or row.get('runner')!=automation.get('runner'):
                fail(f'dashboard.cases[{cid}].runner','must match the confirmed API/UI execution stack')
            use_regression=(ledger_status=='PASS_AFTER_FIX' or ledger_rows[cid].get('source')=='regression_impact_passed')
            result=ledger_rows[cid].get('regression_result') if use_regression else ledger_rows[cid].get('runtime_result')
            run_info=(result or {}).get('automation_run') or {}
            if row.get('script_ref')!=run_info.get('script_ref') or row.get('script_sha256')!=run_info.get('script_sha256'):
                fail(f'dashboard.cases[{cid}].script','must match the final executed script and hash')
            if row.get('script_status')!='verified': fail(f'dashboard.cases[{cid}].script_status','final script must be verified against its recorded hash')
            if row.get('official_run_status')!='completed' or row.get('official_run_exit_code')!=run_info.get('official_run',{}).get('exit_code'):
                fail(f'dashboard.cases[{cid}].official_run_status','must match the completed official runner report, including its exit code')
            if row.get('evidence_status')!='present' or not row.get('evidence_count'): fail(f'dashboard.cases[{cid}].evidence_status','planned Case Evidence must be recorded')
        if pc.get('evidence_plan',{}).get('recording') is True:
            recording=row.get('recording_status')
            if recording!='completed': fail(f'dashboard.cases[{cid}].recording_status','planned Case recording must be completed')
    assessment=derive_assessment(rows,plan_by)
    if assessment['conclusion'] not in CONCLUSIONS: fail('final_assessment.conclusion','invalid')
    v['final_assessment']=assessment
    return {'ok':True,'cases':len(rows),'final_assessment':assessment}

if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--input',required=True); a.add_argument('--run-dir',required=True); x=a.parse_args()
    print(json.dumps(validate(json.loads(Path(x.input).read_text(encoding='utf-8')),x.run_dir),ensure_ascii=False))
