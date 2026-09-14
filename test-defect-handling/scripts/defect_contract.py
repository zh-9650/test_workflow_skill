import argparse, json, importlib.util
from pathlib import Path

def fail(path,msg): raise AssertionError(f'{path}: {msg}')

def _load_execution_control():
    p=Path(__file__).resolve().parents[2]/'test-execution-runtime/scripts/execution_control.py'
    spec=importlib.util.spec_from_file_location('shared_execution_control',p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

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
    else:
        if sub.get('status')!='not_submitted_existing': fail('submission.status','existing bug must use not_submitted_existing')
        if sub.get('bug_ref')!=dc.get('existing_bug_ref'): fail('submission.bug_ref','must equal existing_bug_ref')
    return {'ok':True,'defect_id':v['defect_id'],'bug_ref':dc.get('existing_bug_ref') or sub.get('bug_ref')}

def validate_reg(v,evidence_base=None):
    for k in ['regression_id','bug_ref','original_case_ids','impact_case_ids','worker_is_new','preserve_primary_execution','baseline_cases','cases','status']:
        if k not in v: fail(k,'required')
    if not v['original_case_ids']: fail('original_case_ids','non-empty required')
    if v['worker_is_new'] is not True: fail('worker_is_new','must be true')
    if v['preserve_primary_execution'] is not True: fail('preserve_primary_execution','must be true')
    cases=v['cases']
    if not isinstance(cases,list) or not cases: fail('cases','real regression plan cases required')
    baseline=v['baseline_cases']
    if not isinstance(baseline,list) or not baseline: fail('baseline_cases','original planning cases are required')
    baseline_by={c.get('case_id'):c for c in baseline}
    ids=[c.get('case_id') for c in cases]
    if len(ids)!=len(set(ids)): fail('cases','duplicate plan case ids')
    case_by={c['case_id']:c for c in cases}
    required_ids=set(v['original_case_ids']) | set(v.get('impact_case_ids',[]))
    missing=required_ids-set(case_by)
    if missing: fail('cases',f'missing original/impact cases {sorted(missing)}')
    missing_baseline=required_ids-set(baseline_by)
    if missing_baseline: fail('baseline_cases',f'missing original/impact baseline cases {sorted(missing_baseline)}')
    for cid in required_ids:
        old=baseline_by[cid]; new=case_by[cid]
        if old.get('primary_execution')!=new.get('primary_execution'): fail(f'cases[{cid}].primary_execution','must match the original planning case')
        old_ids=[e.get('id') for e in old.get('expected_results',[])]
        new_ids=[e.get('id') for e in new.get('expected_results',[])]
        if old_ids!=new_ids: fail(f'cases[{cid}].expected_results','Expected mapping must match the original planning case')
        old_expected={e.get('id'):e.get('expected') for e in old.get('expected_results',[])}
        new_expected={e.get('id'):e.get('expected') for e in new.get('expected_results',[])}
        if old_expected!=new_expected: fail(f'cases[{cid}].expected_results','Expected text must match the original planning case')
    if v['status']=='completed':
        results=v.get('results')
        if not isinstance(results,list) or not results: fail('results','completed regression requires real results')
        rids=[r.get('case_id') for r in results]
        if len(rids)!=len(set(rids)): fail('results','duplicate regression result case_id')
        if set(rids)!=set(case_by): fail('results',f'must match regression cases exactly; missing={sorted(set(case_by)-set(rids))}, extra={sorted(set(rids)-set(case_by))}')
        ctl=_load_execution_control(); result_by={r['case_id']:r for r in results}
        for cid,pc in case_by.items(): ctl.validate(pc,result_by[cid],evidence_base)
        failed_scope=sorted(cid for cid in required_ids if result_by[cid].get('status')!='PASS')
        passed=not failed_scope
    else:
        failed_scope=[]; passed=False
    return {'ok':True,'regression_id':v['regression_id'],'regression_passed':passed,'failed_scope_case_ids':failed_scope}

CASE_LEDGER_REL='internal/execution/results/case-results-ledger.json'

def apply_regression_to_ledger(run_dir,v):
    out=validate_reg(v,Path(run_dir))
    if out.get('regression_passed') is not True:
        fail('regression_passed',f'original/impact scope not fully passed: {out.get("failed_scope_case_ids",[])}')
    path=Path(run_dir)/CASE_LEDGER_REL
    if not path.exists(): fail('case_result_ledger',f'missing {CASE_LEDGER_REL}')
    ledger=json.loads(path.read_text(encoding='utf-8')); rows=ledger.setdefault('cases',{})
    result_by={r['case_id']:r for r in v['results']}
    original=set(v['original_case_ids']); impact=set(v.get('impact_case_ids',[]))
    from datetime import datetime, timezone
    ts=datetime.now(timezone.utc).isoformat()
    for cid in original|impact:
        if cid not in rows: fail(f'case_result_ledger.{cid}','case is not initialized in ledger')
        rows[cid].update({
            'status':'PASS_AFTER_FIX' if cid in original else 'PASS',
            'final_result':'PASS_AFTER_FIX' if cid in original else 'PASS',
            'reviewer_confirmed':True,
            'source':'regression_passed',
            'regression_id':v['regression_id'],
            'bug_ref':v['bug_ref'],
            'regression_result':result_by[cid],
            'updated_at':ts,
        })
    ledger['updated_at']=ts
    tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); tmp.replace(path)
    return {'ok':True,'regression_id':v['regression_id'],'updated_case_ids':sorted(original|impact)}

if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--input',required=True); a.add_argument('--type',choices=['bug','regression'],default='bug'); a.add_argument('--apply-run-dir'); x=a.parse_args()
    v=json.loads(Path(x.input).read_text(encoding='utf-8'))
    if x.type=='bug': out=validate(v)
    elif x.apply_run_dir: out=apply_regression_to_ledger(x.apply_run_dir,v)
    else: out=validate_reg(v)
    print(json.dumps(out,ensure_ascii=False))
