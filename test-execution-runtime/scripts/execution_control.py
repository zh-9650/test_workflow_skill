import argparse, json
from pathlib import Path

FINAL={'PASS','FAIL','BLOCKED','NEEDS_REVIEW'}
TECH={'script_error','locator_error','data_error','environment_error','account_permission_error','case_design_issue'}
BLOCK_TYPES={'product_bug','environment','external_resource','upstream_case','manual_pending','data_unavailable','account_permission'}
REVIEW_TYPES={'case_design_issue','business_rule_uncertain','evidence_insufficient','planning_conflict'}

def fail(path,msg): raise AssertionError(f'{path}: {msg}')

def _main(plan): return plan.get('primary_execution')
def _actual(res): return res.get('actual_execution')

def _check_evidence(refs,path,evidence_base):
    if not isinstance(refs,list) or any(not isinstance(ref,str) or not ref.strip() for ref in refs): fail(path,'must be a non-empty list of paths')
    if evidence_base is None: return
    base=Path(evidence_base).resolve()
    for i,ref in enumerate(refs):
        p=(base/ref).resolve() if not Path(ref).is_absolute() else Path(ref).resolve()
        try: p.relative_to(base)
        except ValueError: fail(f'{path}[{i}]','evidence must stay inside the Run directory')
        if not p.is_file(): fail(f'{path}[{i}]',f'evidence file does not exist: {p}')

def validate(plan_case,result,evidence_base=None):
    cid=plan_case.get('case_id')
    if result.get('case_id')!=cid: fail('case_id',f'mismatch, expected {cid}')
    if _actual(result)!=_main(plan_case): fail(f'{cid}.actual_execution',f'planned {_main(plan_case)}, actual {_actual(result)}')
    expected=plan_case.get('expected_results',[]); rows=result.get('expected_results',[])
    if not expected: fail(f'{cid}.expected_results','plan has none')
    if len(expected)!=len(rows): fail(f'{cid}.expected_results','mapping incomplete')
    exp_by={e.get('id'):e for e in expected}; row_by={e.get('id'):e for e in rows}
    if None in exp_by or set(exp_by)!=set(row_by): fail(f'{cid}.expected_results','IDs mismatch')
    status=result.get('status')
    if status not in FINAL: fail(f'{cid}.status',f'invalid {status}')
    for eid,r in row_by.items():
        p=f'{cid}.expected_results[{eid}]'
        if r.get('actual') in (None,''): fail(p+'.actual','required')
        if r.get('result') not in {'pass','fail','blocked','needs_review'}: fail(p+'.result','invalid')
        plan_e=exp_by[eid]
        refs=r.get('evidence_refs',r.get('evidence',[]))
        if not refs and not plan_e.get('evidence_not_required'):
            fail(p+'.evidence_refs','required unless plan explicitly exempts evidence')
        if refs: _check_evidence(refs,p+'.evidence_refs',evidence_base)
        if plan_e.get('evidence_not_required') and not plan_e.get('evidence_not_required_reason'):
            fail(f'{cid}.expected_results[{eid}].evidence_not_required_reason','required for evidence exemption')
    if status=='PASS':
        bad=[eid for eid,r in row_by.items() if r.get('result')!='pass']
        if bad: fail(f'{cid}.status',f'PASS but expected results not pass: {bad}')
    elif status=='FAIL':
        if result.get('reason_type')!='product_issue': fail(f'{cid}.reason_type','FAIL requires product_issue; technical/data/design errors are not product FAIL')
        if result.get('expected') in (None,'') or result.get('actual') in (None,''): fail(f'{cid}.FAIL','expected and actual required')
        if not result.get('evidence_refs'): fail(f'{cid}.evidence_refs','FAIL requires evidence')
        if result.get('reproduced') is not True:
            if result.get('reproduction_applicable') is not False or not result.get('reproduction_reason'):
                fail(f'{cid}.reproduced','must be true or explicitly not applicable with reason')
        if not any(r.get('result')=='fail' for r in rows): fail(f'{cid}.expected_results','FAIL requires at least one failed expected')
    elif status=='BLOCKED':
        if any(r.get('result')!='blocked' for r in rows): fail(f'{cid}.expected_results','BLOCKED requires every expected result to be blocked')
        if result.get('blocked_reason_type') not in BLOCK_TYPES: fail(f'{cid}.blocked_reason_type',f'must be one of {sorted(BLOCK_TYPES)}')
        if not result.get('blocked_reason'): fail(f'{cid}.blocked_reason','required')
        if result.get('affected_by') in (None,''): fail(f'{cid}.affected_by','required')
    elif status=='NEEDS_REVIEW':
        if not any(r.get('result')=='needs_review' for r in rows): fail(f'{cid}.expected_results','NEEDS_REVIEW requires a needs_review expected result')
        if result.get('review_reason_type') not in REVIEW_TYPES: fail(f'{cid}.review_reason_type',f'must be one of {sorted(REVIEW_TYPES)}')
        if not result.get('review_reason'): fail(f'{cid}.review_reason','required')
        if not result.get('required_action'): fail(f'{cid}.required_action','required')
    ep=plan_case.get('evidence_plan',{})
    rec=ep.get('recording')
    if isinstance(rec,dict) and rec.get('required') is True and not result.get('recording_ref',result.get('video_ref')):
        fail(f'{cid}.recording_ref','planned recording missing')
    recording=result.get('recording_ref',result.get('video_ref'))
    if recording and evidence_base is not None: _check_evidence([recording],f'{cid}.recording_ref',evidence_base)
    return {'ok':True,'case_id':cid,'status':status}

if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--plan-case',required=True); a.add_argument('--result',required=True); x=a.parse_args()
    print(json.dumps(validate(json.loads(Path(x.plan_case).read_text(encoding='utf-8')),json.loads(Path(x.result).read_text(encoding='utf-8'))),ensure_ascii=False))
