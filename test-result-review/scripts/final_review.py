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
    plan_binding=run_state.get('confirmation_bindings',{}).get('execution-plan')
    if not plan_binding: fail('execution_plan_ref','execution plan is not confirmed/bound')
    if Path(plan_binding.get('contract_path','')).resolve()!=plan_path.resolve() or _sha256(plan_path)!=plan_binding.get('contract_sha256'):
        fail('execution_plan_ref','confirmed execution plan changed after confirmation')
    case_binding=run_state.get('confirmation_bindings',{}).get('test-cases')
    if not case_binding: fail('confirmed_cases','confirmed test-case binding missing')
    confirmed_cases_path=Path(case_binding.get('contract_path',''))
    if not confirmed_cases_path.exists() or _sha256(confirmed_cases_path)!=case_binding.get('contract_sha256'):
        fail('confirmed_cases','confirmed test cases changed or disappeared')
    confirmed_cases=json.loads(confirmed_cases_path.read_text(encoding='utf-8'))
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
    execution=_load(runtime_root/'execution_control.py','final_execution_control')
    reviewer_mod=_load(runtime_root/'reviewer_contract.py','final_reviewer_contract')
    worker_mod=_load(runtime_root/'worker_review.py','final_worker_review')

    # Reopen actual batch state files rather than trusting only final-summary flags.
    planned_batches={b['id']:b for b in plan.get('batches',[])}
    supplied_batches={b.get('batch_id'):b for b in v.get('batch_results',[])}
    if set(supplied_batches)!=set(planned_batches): fail('batch_results','every planned batch requires one final batch result')
    for bid,batch in planned_batches.items():
        state_path=run/f'internal/execution/runtime-state/{bid}-state.json'
        if not state_path.exists(): fail(f'batch_results[{bid}]',f'missing runtime state {state_path}')
        state=json.loads(state_path.read_text(encoding='utf-8'))
        if state.get('status')!='completed': fail(f'batch_results[{bid}].status','runtime batch state is not completed')
        task_path=run/state.get('task_ref','')
        results_path=run/state.get('worker_results_ref','')
        if not task_path.exists() or not results_path.exists(): fail(f'batch_results[{bid}]','task/results file missing')
        task=json.loads(task_path.read_text(encoding='utf-8')); detailed=json.loads(results_path.read_text(encoding='utf-8'))
        worker_mod.validate(state.get('worker_self_review') or {},task['case_order'],detailed)
        reviewer_mod.validate(state.get('reviewer') or {},task['case_order'],detailed)
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
            if item.get('initial_result')!='FAIL': fail(f'{cid}.initial_result','PASS_AFTER_FIX requires preserved initial FAIL')
            if not item.get('bug_ref'): fail(f'{cid}.bug_ref','PASS_AFTER_FIX requires bug_ref in ledger')
            if not isinstance(original,dict) or original.get('status')!='FAIL': fail(f'{cid}.runtime_result','initial FAIL runtime result required')
            execution.validate(pc,original,evidence_root=run)
            if not isinstance(regression,dict) or regression.get('status')!='PASS': fail(f'{cid}.regression_result','real PASS regression result required')
            execution.validate(pc,regression,evidence_root=run)
        elif item.get('source')=='regression_impact_passed':
            regression=item.get('regression_result')
            if not isinstance(regression,dict) or regression.get('status')!='PASS': fail(f'{cid}.regression_result','impact regression requires a real PASS result')
            execution.validate(pc,regression,evidence_root=run)
            runtime=item.get('runtime_result')
            if isinstance(runtime,dict): execution.validate(pc,runtime,evidence_root=run)
        else:
            runtime=item.get('runtime_result')
            if not isinstance(runtime,dict): fail(f'{cid}.runtime_result','full runtime result required in case ledger')
            execution.validate(pc,runtime,evidence_root=run)
        if status=='FAIL' and not (item.get('bug_ref') or item.get('existing_bug_ref') or summary.get('bug_ref') or summary.get('existing_bug_ref') or summary.get('no_bug_reason')): fail(f'{cid}.FAIL','bug closure required')
        if status=='BLOCKED' and not (summary.get('blocked_reason') or item.get('runtime_result',{}).get('blocked_reason')): fail(f'{cid}.blocked_reason','required')

    dashboard_path=run/'dashboard/dashboard-data.json'
    if dashboard_path.exists():
        dashboard=json.loads(dashboard_path.read_text(encoding='utf-8'))
        dash_batches={b.get('id'):b.get('status') for b in dashboard.get('batches',[])}
        state_batches=run_state.get('batch_status',{})
        for bid in planned_batches:
            if dash_batches.get(bid)!='completed': fail(f'dashboard.batches[{bid}]','must be completed before Final Review')
            if state_batches.get(bid)!='completed': fail(f'run_status.batch_status[{bid}]','must be completed and consistent with Dashboard before Final Review')
    assessment=derive_assessment(rows,plan_by)
    if assessment['conclusion'] not in CONCLUSIONS: fail('final_assessment.conclusion','invalid')
    v['final_assessment']=assessment
    return {'ok':True,'cases':len(rows),'final_assessment':assessment}

if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--input',required=True); a.add_argument('--run-dir',required=True); x=a.parse_args()
    print(json.dumps(validate(json.loads(Path(x.input).read_text(encoding='utf-8')),x.run_dir),ensure_ascii=False))
