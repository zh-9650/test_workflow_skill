from worker_review import validate as validate_worker_review
from reviewer_contract import validate as validate_reviewer

def fail(path,msg): raise AssertionError(f'{path}: {msg}')

def validate(v):
    planned=v.get('case_ids',[]); results=v.get('case_results',[])
    if not planned: fail('case_ids','required')
    validate_worker_review(v.get('worker_self_review',{}),planned,results)
    validate_reviewer(v.get('reviewer',{}),planned)
    st=v.get('status')
    if st=='completed':
        if v['worker_self_review'].get('status')!='passed': fail('status','completed requires worker self review passed')
        if v['reviewer'].get('status')!='passed': fail('status','completed requires reviewer passed')
    elif st not in {'pending','running','self_review','reviewing','needs_rework','blocked','return_upstream'}:
        fail('status',f'invalid {st}')
    return {'ok':True,'status':st}
