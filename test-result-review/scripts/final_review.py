import argparse, json, importlib.util
from pathlib import Path

FINAL={'PASS','FAIL','BLOCKED','PASS_AFTER_FIX'}
CONCLUSIONS={'ready','ready_with_risk','not_recommended','incomplete'}
WORKER_CHECKS=['all_cases_checked','all_expected_checked','execution_method_checked','evidence_binding_checked','failure_classification_checked','file_cleanup_checked']
REVIEWER_CHECKS=['completeness_checked','method_consistency_checked','judgement_checked','evidence_checked','abnormal_classification_checked']

def fail(path,msg): raise AssertionError(f'{path}: {msg}')

def _load_execution_control():
    p=Path(__file__).resolve().parents[2]/'test-execution-runtime/scripts/execution_control.py'
    spec=importlib.util.spec_from_file_location('final_review_execution_control',p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def _load_regression_contract():
    p=Path(__file__).resolve().parents[2]/'test-defect-handling/scripts/defect_contract.py'
    spec=importlib.util.spec_from_file_location('final_review_regression_contract',p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def derive_assessment(v):
    rows=v['results']
    # FAIL is always unresolved. A process-only `fixed=true` flag must never hide it.
    unresolved=[r for r in rows if r['status']=='FAIL']
    blocked=[r for r in rows if r['status']=='BLOCKED']
    core=[r for r in rows if r.get('core_flow')]
    core_ok=all(r['status'] in {'PASS','PASS_AFTER_FIX'} for r in core)
    coverage_complete=set(v['formal_case_ids'])==set(v['planned_case_ids'])=={r['case_id'] for r in rows}
    regression_complete=all(r['status']!='PASS_AFTER_FIX' or any(x.get('result')=='PASS' for x in r.get('regressions',[])) for r in rows)
    critical=[r for r in unresolved if r.get('severity') in {'critical','blocker','major'}]
    if not coverage_complete: conclusion='incomplete'
    elif critical or not core_ok: conclusion='not_recommended'
    elif blocked or unresolved: conclusion='ready_with_risk'
    else: conclusion='ready'
    return {'coverage_complete':coverage_complete,'core_flow_passed':core_ok,'unresolved_critical_defects':len(critical),'blocked_scope':[r['case_id'] for r in blocked],'regression_complete':regression_complete,'conclusion':conclusion}

def _validate_review_checks(batch):
    bid=batch.get('batch_id'); w=batch.get('worker_self_review',{}); r=batch.get('reviewer',{})
    if w.get('status')!='passed': fail(f'batch_results[{bid}].worker_self_review','must pass')
    for k in WORKER_CHECKS:
        if w.get('checks',{}).get(k) is not True: fail(f'batch_results[{bid}].worker_self_review.checks.{k}','must be true')
    if r.get('status')!='passed': fail(f'batch_results[{bid}].reviewer','must pass')
    for k in REVIEWER_CHECKS:
        if r.get('checks',{}).get(k) is not True: fail(f'batch_results[{bid}].reviewer.checks.{k}','must be true')

def validate(v,evidence_base=None):
    formal=set(v.get('formal_case_ids',[])); planned=set(v.get('planned_case_ids',[])); rows=v.get('results',[]); rid={r.get('case_id') for r in rows}
    if not formal or not planned or not rows: fail('run','formal_case_ids/planned_case_ids/results required')
    if len(rows)!=len(rid): fail('results','duplicate final result case_id')
    if formal!=planned or formal!=rid: fail('case_sets',f'formal/planned/result differ: {formal}^{planned}^{rid}')
    planned_batches=set(v.get('planned_batch_ids',[])); actual_batch_rows=v.get('batch_results',[]); actual_batches={b.get('batch_id') for b in actual_batch_rows}
    if not planned_batches: fail('planned_batch_ids','at least one planned Batch is required')
    if planned_batches!=actual_batches: fail('batch_results','every planned batch requires a final batch result')
    planned_cases=v.get('planned_cases',[])
    if not isinstance(planned_cases,list) or not planned_cases: fail('planned_cases','the final review must include the confirmed Execution Plan cases')
    plan_by={c.get('case_id'):c for c in planned_cases}
    if set(plan_by)!=planned: fail('planned_cases','must match planned_case_ids exactly')
    ctl=_load_execution_control(); reg=_load_regression_contract()
    for b in v.get('batch_results',[]):
        if b.get('status')!='completed': fail(f'batch_results[{b.get("batch_id")}].status','must be completed')
        _validate_review_checks(b)
        planned_batch_case_ids={cid for cid,c in plan_by.items() if c.get('batch_id')==b.get('batch_id')}
        if not isinstance(b.get('case_ids'),list) or set(b['case_ids']) != planned_batch_case_ids: fail(f'batch_results[{b.get("batch_id")}].case_ids','must match the confirmed plan exactly')
    for r in rows:
        cid=r['case_id']; status=r.get('status')
        if status not in FINAL: fail(f'{cid}.status','non-final status remains')
        pc=plan_by[cid]
        if r.get('planned_primary_execution',pc.get('primary_execution'))!=r.get('actual_execution'): fail(f'{cid}.actual_execution','planned vs actual execution mismatch')
        # Evidence obligations belong to the confirmed plan, never to the result row.
        # A worker cannot weaken them by writing a second `planned_evidence` object.
        ep=pc.get('evidence_plan',{}); rec=ep.get('recording')
        if isinstance(rec,dict) and rec.get('required') is True and not r.get('recording_ref'): fail(f'{cid}.recording_ref','planned recording missing')
        if ep.get('files') and not r.get('file_evidence_refs'): fail(f'{cid}.file_evidence_refs','planned file evidence missing')
        if status!='PASS_AFTER_FIX': ctl.validate(pc,r,evidence_base)
        if status=='FAIL':
            if not (r.get('bug_ref') or r.get('existing_bug_ref') or r.get('no_bug_reason')): fail(f'{cid}.FAIL','bug closure required')
        if status=='BLOCKED' and not r.get('blocked_reason'): fail(f'{cid}.blocked_reason','required')
        if status=='PASS_AFTER_FIX':
            if r.get('initial_result')!='FAIL': fail(f'{cid}.initial_result','PASS_AFTER_FIX requires initial FAIL')
            if not r.get('bug_ref'): fail(f'{cid}.bug_ref','PASS_AFTER_FIX requires bug_ref')
            regs=r.get('regressions')
            if not isinstance(regs,list) or not regs: fail(f'{cid}.regressions','PASS_AFTER_FIX requires regression history')
            if not any(x.get('result')=='PASS' and x.get('regression_id') and x.get('worker_id') and x.get('executed_at') for x in regs): fail(f'{cid}.regressions','requires real PASS regression record')
            regression=r.get('regression')
            if not isinstance(regression,dict): fail(f'{cid}.regression','full validated regression record required')
            reg_out=reg.validate_reg(regression,evidence_base)
            if reg_out.get('regression_passed') is not True: fail(f'{cid}.regression','original and impact scope must pass')
    assessment=derive_assessment(v)
    if assessment['conclusion'] not in CONCLUSIONS: fail('final_assessment.conclusion','invalid')
    v['final_assessment']=assessment
    return {'ok':True,'cases':len(rows),'final_assessment':assessment}

if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--input',required=True); a.add_argument('--evidence-base'); a.add_argument('--output'); x=a.parse_args()
    input_path=Path(x.input).resolve()
    out=validate(json.loads(input_path.read_text(encoding='utf-8')),x.evidence_base)
    out['validator']='test-result-review/scripts/final_review.py'; out['validated_at']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
    out['validated_input'] = str(input_path)
    import hashlib
    out['validated_input_sha256'] = hashlib.sha256(input_path.read_bytes()).hexdigest()
    if x.output: Path(x.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(out,ensure_ascii=False))
