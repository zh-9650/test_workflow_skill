VALID={'passed','rework_required','return_upstream'}
RETURN={None,'case_design','execution_planning','data_readiness'}
MANDATORY=['completeness_checked','method_consistency_checked','judgement_checked','evidence_checked','abnormal_classification_checked']


def fail(path,msg): raise AssertionError(f'{path}: {msg}')


def validate(review, planned_case_ids, case_results=None):
    st=review.get('status')
    if st not in VALID: fail('reviewer.status',f'must be one of {sorted(VALID)}')
    if not isinstance(review.get('findings'),list): fail('reviewer.findings','list required')
    checked=review.get('checked_case_ids',[])
    if not isinstance(checked,list) or set(checked)!=set(planned_case_ids) or len(checked)!=len(planned_case_ids):
        fail('reviewer.checked_case_ids','must cover every Case in the reviewer task')
    retest=review.get('retest_case_ids',[])
    if not isinstance(retest,list): fail('reviewer.retest_case_ids','list required')
    if len(retest)!=len(set(retest)): fail('reviewer.retest_case_ids','duplicate case ids are forbidden')
    unknown=set(retest)-set(planned_case_ids)
    if unknown: fail('reviewer.retest_case_ids',f'unknown cases {sorted(unknown)}')
    rs=review.get('return_stage')
    if rs not in RETURN: fail('reviewer.return_stage',f'invalid {rs}')
    checks=review.get('checks')
    if not isinstance(checks,dict): fail('reviewer.checks','object required')
    for k in MANDATORY:
        if k not in checks or not isinstance(checks.get(k),bool): fail(f'reviewer.checks.{k}','boolean check result required')
    result_by={r.get('case_id'):r for r in (case_results or [])}
    needs_review=sorted(cid for cid in planned_case_ids if result_by.get(cid,{}).get('status')=='NEEDS_REVIEW')
    if st=='passed':
        for k in MANDATORY:
            if checks.get(k) is not True: fail(f'reviewer.checks.{k}','must be true when status=passed')
        if retest or rs is not None: fail('reviewer','passed cannot request retest or upstream return')
        if needs_review: fail('reviewer.status',f'cannot pass while NEEDS_REVIEW remains: {needs_review}')
    if st=='rework_required':
        for k in MANDATORY:
            if checks.get(k) is not True: fail(f'reviewer.checks.{k}','must be true when requesting local rework')
        if not retest: fail('reviewer.retest_case_ids','required for rework_required')
        if rs is not None: fail('reviewer.return_stage','must be null for local rework')
    if st=='return_upstream':
        if rs is None: fail('reviewer.return_stage','required for return_upstream')
        if not review.get('findings'): fail('reviewer.findings','return_upstream needs findings')
    return {'ok':True,'status':st}
