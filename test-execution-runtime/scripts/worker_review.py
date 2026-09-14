MANDATORY=['all_cases_checked','all_expected_checked','execution_method_checked','evidence_binding_checked','failure_classification_checked','file_cleanup_checked']

def fail(path,msg): raise AssertionError(f'{path}: {msg}')

def validate(worker_review, planned_case_ids, results):
    if worker_review.get('status') != 'passed': fail('worker_self_review.status','must be passed')
    result_ids=[r.get('case_id') for r in results]
    if len(result_ids)!=len(set(result_ids)): fail('worker_self_review.results','duplicate case_id in results')
    if set(planned_case_ids)!=set(result_ids): fail('worker_self_review','planned/result case set mismatch')
    if set(worker_review.get('checked_case_ids',[])) != set(planned_case_ids):
        fail('worker_self_review.checked_case_ids','must cover every planned case')
    checks=worker_review.get('checks')
    if not isinstance(checks,dict): fail('worker_self_review.checks','object required')
    for k in MANDATORY:
        if checks.get(k) is not True: fail(f'worker_self_review.checks.{k}','must be true when status=passed')
    if not isinstance(worker_review.get('findings'),list): fail('worker_self_review.findings','list required')
    return {'ok':True}
