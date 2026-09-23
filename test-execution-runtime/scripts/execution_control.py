import argparse, json, runpy
from pathlib import Path

EXECUTION_SCHEMA_VERSION = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / 'clarify-before-testing/scripts/workflow_versions.py')
)['EXECUTION_SCHEMA_VERSION']

FINAL={'PASS','FAIL','BLOCKED','NEEDS_REVIEW'}
BLOCK_TYPES={'product_bug','environment','external_resource','upstream_case','manual_pending','data_unavailable','account_permission'}
REVIEW_TYPES={'case_design_issue','business_rule_uncertain','evidence_insufficient','planning_conflict'}


def fail(path,msg): raise AssertionError(f'{path}: {msg}')
def _main(plan): return plan.get('primary_execution')
def _actual(res): return res.get('actual_execution')


def _resolve_root(evidence_root):
    if evidence_root is None: fail('evidence_root','current Run directory is required for evidence validation')
    return Path(evidence_root).resolve()


def _allowed_case_root(plan_case,evidence_root):
    run=_resolve_root(evidence_root); bid=plan_case.get('batch_id'); cid=plan_case.get('case_id')
    if not bid or not cid: fail('plan_case','batch_id and case_id required for evidence ownership validation')
    return (run/'evidence'/str(bid)/str(cid)).resolve()


def _allowed_batch_root(plan_case,evidence_root):
    run=_resolve_root(evidence_root); bid=plan_case.get('batch_id')
    if not bid: fail('plan_case.batch_id','required for batch evidence ownership validation')
    return (run/'evidence'/str(bid)).resolve()


def _evidence_path(ref,evidence_root):
    if isinstance(ref,dict): ref=ref.get('path') or ref.get('ref')
    if not isinstance(ref,str) or not ref.strip(): fail('evidence_ref','non-empty file path required')
    run=_resolve_root(evidence_root); p=Path(ref)
    p=(p if p.is_absolute() else run/p).resolve()
    return p


def _inside(path,root):
    try: path.relative_to(root); return True
    except ValueError: return False


def _require_evidence(refs,path,evidence_root,allowed_root):
    if not isinstance(refs,list) or not refs: fail(path,'non-empty evidence list required')
    for ref in refs:
        p=_evidence_path(ref,evidence_root)
        if not _inside(p,allowed_root): fail(path,f'evidence must belong to current Run/Batch/Case: {p}')
        if not p.exists() or not p.is_file(): fail(path,f'evidence file does not exist: {p}')


def _require_single_evidence(ref,path,evidence_root,allowed_root):
    p=_evidence_path(ref,evidence_root)
    if not _inside(p,allowed_root): fail(path,f'evidence must belong to current Run/Batch/Case: {p}')
    if not p.exists() or not p.is_file(): fail(path,f'evidence file does not exist: {p}')


def validate(plan_case,result,evidence_root=None):
    cid=plan_case.get('case_id'); status=result.get('status')
    schema_version=result.get('schema_version')
    if type(schema_version) is not int or schema_version != EXECUTION_SCHEMA_VERSION:
        fail(f'{cid}.schema_version',f'must be integer {EXECUTION_SCHEMA_VERSION}')
    if result.get('case_id')!=cid: fail('case_id',f'mismatch, expected {cid}')
    if status not in FINAL: fail(f'{cid}.status',f'invalid {status}')
    actual_execution=_actual(result); planned_execution=_main(plan_case)
    not_executed=(status=='BLOCKED' and result.get('target_action_executed') is False and actual_execution in (None,'NOT_EXECUTED'))
    if not not_executed and actual_execution!=planned_execution:
        fail(f'{cid}.actual_execution',f'planned {planned_execution}, actual {actual_execution}')

    case_evidence_root=_allowed_case_root(plan_case,evidence_root)
    expected=plan_case.get('expected_results',[]); rows=result.get('expected_results',[])
    if not expected: fail(f'{cid}.expected_results','plan has none')
    if len(expected)!=len(rows): fail(f'{cid}.expected_results','mapping incomplete')
    exp_by={e.get('id'):e for e in expected}; row_by={e.get('id'):e for e in rows}
    if None in exp_by or len(exp_by)!=len(expected) or None in row_by or len(row_by)!=len(rows) or set(exp_by)!=set(row_by): fail(f'{cid}.expected_results','IDs missing/duplicate/mismatch')
    for eid,r in row_by.items():
        p=f'{cid}.expected_results[{eid}]'
        if r.get('actual') in (None,''): fail(p+'.actual','required')
        if r.get('result') not in {'pass','fail','blocked','needs_review'}: fail(p+'.result','invalid')
        refs=r.get('evidence_refs',r.get('evidence',[]))
        if not refs: fail(p+'.evidence_refs','every Expected requires current-run evidence')
        _require_evidence(refs,p+'.evidence_refs',evidence_root,case_evidence_root)

    if status=='PASS':
        bad=[eid for eid,r in row_by.items() if r.get('result')!='pass']
        if bad: fail(f'{cid}.status',f'PASS but expected results not pass: {bad}')
    elif status=='FAIL':
        if result.get('reason_type')!='product_issue': fail(f'{cid}.reason_type','FAIL requires product_issue; technical/data/design errors are not product FAIL')
        if result.get('expected') in (None,'') or result.get('actual') in (None,''): fail(f'{cid}.FAIL','expected and actual required')
        _require_evidence(result.get('evidence_refs',[]),f'{cid}.evidence_refs',evidence_root,case_evidence_root)
        if result.get('reproduced') is not True:
            if result.get('reproduction_applicable') is not False or not result.get('reproduction_reason'): fail(f'{cid}.reproduced','must be true or explicitly not applicable with reason')
        if not any(r.get('result')=='fail' for r in rows): fail(f'{cid}.expected_results','FAIL requires at least one failed expected')
    elif status=='BLOCKED':
        if result.get('blocked_reason_type') not in BLOCK_TYPES: fail(f'{cid}.blocked_reason_type',f'must be one of {sorted(BLOCK_TYPES)}')
        if not result.get('blocked_reason'): fail(f'{cid}.blocked_reason','required')
        if result.get('affected_by') in (None,''): fail(f'{cid}.affected_by','required')
        if all(r.get('result')=='pass' for r in rows): fail(f'{cid}.expected_results','BLOCKED cannot have every Expected marked pass')
        if not any(r.get('result')=='blocked' for r in rows): fail(f'{cid}.expected_results','BLOCKED requires at least one blocked Expected')
    elif status=='NEEDS_REVIEW':
        if result.get('review_reason_type') not in REVIEW_TYPES: fail(f'{cid}.review_reason_type',f'must be one of {sorted(REVIEW_TYPES)}')
        if not result.get('review_reason'): fail(f'{cid}.review_reason','required')
        if not result.get('required_action'): fail(f'{cid}.required_action','required')
        if not any(r.get('result')=='needs_review' for r in rows): fail(f'{cid}.expected_results','NEEDS_REVIEW requires at least one Expected needing review')

    ep=plan_case.get('evidence_plan',{}); rec=ep.get('recording')
    if isinstance(rec,dict) and rec.get('required') is True:
        rr=result.get('recording_ref',result.get('video_ref'))
        if not rr: fail(f'{cid}.recording_ref','planned recording missing')
        allowed=_allowed_batch_root(plan_case,evidence_root) if rec.get('scope')=='batch' else case_evidence_root
        _require_single_evidence(rr,f'{cid}.recording_ref',evidence_root,allowed)
    for ref in result.get('file_evidence_refs',[]) or []:
        _require_single_evidence(ref,f'{cid}.file_evidence_refs',evidence_root,case_evidence_root)
    return {'ok':True,'case_id':cid,'status':status}


if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--plan-case',required=True); a.add_argument('--result',required=True); a.add_argument('--evidence-root',required=True); x=a.parse_args()
    print(json.dumps(validate(json.loads(Path(x.plan_case).read_text(encoding='utf-8')),json.loads(Path(x.result).read_text(encoding='utf-8')),x.evidence_root),ensure_ascii=False))
