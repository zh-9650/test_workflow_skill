import argparse, hashlib, json, runpy
from pathlib import Path

EXECUTION_SCHEMA_VERSION = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / 'clarify-before-testing/scripts/workflow_versions.py')
)['EXECUTION_SCHEMA_VERSION']

MAIN={'UI','API','人工'}
AUX={'UI','API','数据库只读','Network','日志','文件','其他系统'}
IMMUTABLE_CASE_FIELDS=('title','steps','expected_results','target_action','test_point_ids','preconditions','test_data','complex_flow','intermediate_assertions')


def fail(path,msg): raise AssertionError(f'{path}: {msg}')
def sha256(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _canon(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def _recording_required(ep):
    rec=ep.get('recording'); return isinstance(rec,dict) and rec.get('required') is True


def _confirmed_case_map(confirmed_cases):
    cases=confirmed_cases.get('cases',[]) if isinstance(confirmed_cases,dict) else []
    ids=[c.get('case_id') for c in cases]
    if not ids or any(not x for x in ids) or len(ids)!=len(set(ids)): fail('confirmed_cases','confirmed test-case payload must contain unique case_ids')
    return {c['case_id']:c for c in cases}


def _assert_case_source(plan_case,confirmed):
    cid=plan_case['case_id']
    for field in IMMUTABLE_CASE_FIELDS:
        if field in plan_case and _canon(plan_case.get(field)) != _canon(confirmed.get(field)):
            fail(f'{cid}.{field}',f'Planning cannot modify confirmed Case field {field}')
    # These are required in the plan because Runtime task needs them, but must be exact copies.
    for field in ('title','steps','expected_results','target_action','preconditions','test_data'):
        if field not in plan_case: fail(f'{cid}.{field}','must carry the exact confirmed Case value into Runtime planning')
        if _canon(plan_case[field]) != _canon(confirmed.get(field)):
            fail(f'{cid}.{field}','must exactly equal the confirmed Case')


def validate(plan,require_confirmed=True,confirmed_cases=None,confirmed_cases_sha256=None):
    if type(plan.get('schema_version')) is not int or plan['schema_version'] != EXECUTION_SCHEMA_VERSION:
        fail('schema_version',f'execution plan requires schema_version={EXECUTION_SCHEMA_VERSION}')
    cases=plan.get('cases'); batches=plan.get('batches')
    if not isinstance(cases,list) or not cases: fail('cases','required and non-empty')
    if not isinstance(batches,list) or not batches: fail('batches','required and non-empty')
    if confirmed_cases is None: fail('confirmed_cases','real confirmed test-case payload is required for planning validation')
    confirmed_by=_confirmed_case_map(confirmed_cases); confirmed_ids=list(confirmed_by)
    plan_ids=[c.get('case_id') for c in cases]
    if set(plan_ids)!=set(confirmed_ids) or len(plan_ids)!=len(confirmed_ids):
        fail('case_set',f'planning cases must exactly equal confirmed cases; missing={sorted(set(confirmed_ids)-set(plan_ids))}, extra={sorted(set(plan_ids)-set(confirmed_ids))}')
    declared=plan.get('confirmed_case_ids')
    if not isinstance(declared,list) or set(declared)!=set(confirmed_ids) or len(declared)!=len(confirmed_ids): fail('confirmed_case_ids','must exactly match confirmed test cases')
    if confirmed_cases_sha256 is not None and plan.get('confirmed_cases_sha256')!=confirmed_cases_sha256: fail('confirmed_cases_sha256','must bind to the confirmed test-case contract version')

    sr=plan.get('self_review',{})
    if sr.get('status')!='passed': fail('self_review.status','must be passed')
    for k in ['all_cases_assigned','execution_method_checked','batch_logic_checked','dependency_checked','evidence_checked','data_strategy_checked']:
        if sr.get('checks',{}).get(k) is not True: fail(f'self_review.checks.{k}','must be true')
    if require_confirmed and plan.get('user_confirmation',{}).get('status')!='confirmed': fail('user_confirmation.status','execution plan must be confirmed')

    batch_ids=[]; batch_by_id={}; case_membership={}
    for i,b in enumerate(batches):
        p=f'batches[{i}]'; bid=b.get('id')
        if not bid: fail(p+'.id','required')
        if bid in batch_by_id: fail(p+'.id',f'duplicate {bid}')
        batch_ids.append(bid); batch_by_id[bid]=b
        if not isinstance(b.get('parallel_safe'),bool): fail(p+'.parallel_safe','boolean required')
        if not isinstance(b.get('case_ids'),list) or not b['case_ids']: fail(p+'.case_ids','non-empty list required')
        if len(set(b['case_ids']))!=len(b['case_ids']): fail(p+'.case_ids','duplicate case id in batch')
        for cid in b['case_ids']: case_membership.setdefault(cid,[]).append(bid)
    batch_order={bid:i for i,bid in enumerate(batch_ids)}

    case_by_id={}
    for i,c in enumerate(cases):
        p=f'cases[{i}]'; cid=c.get('case_id')
        if not cid: fail(p+'.case_id','required')
        if cid in case_by_id: fail(p+'.case_id',f'duplicate {cid}')
        case_by_id[cid]=c; _assert_case_source(c,confirmed_by[cid])
        bid=c.get('batch_id')
        if bid not in batch_by_id: fail(f'{cid}.batch_id',f'unknown batch {bid}')
        if case_membership.get(cid)!=[bid]: fail(f'{cid}.batch_id',f'must appear exactly once in {bid}.case_ids; actual={case_membership.get(cid)}')
        main=c.get('primary_execution')
        if main not in MAIN: fail(f'{cid}.primary_execution',f'invalid {main}')
        exp=c['expected_results']; exp_ids=[]
        for j,e in enumerate(exp):
            if not isinstance(e,dict): fail(f'{cid}.expected_results[{j}]','object with stable id and expected text required')
            eid=e.get('id'); expected=e.get('expected')
            if not eid or not isinstance(expected,str) or not expected.strip(): fail(f'{cid}.expected_results[{j}]','id and observable expected text required')
            exp_ids.append(eid)
        if len(exp_ids)!=len(set(exp_ids)): fail(f'{cid}.expected_results','duplicate expected id')
        if c.get('ui_required') is True and main!='UI': fail(f'{cid}.primary_execution','UI-required case cannot use API/manual')
        if not set(c.get('supporting_observations',c.get('aux_validation',[])))<=AUX: fail(f'{cid}.supporting_observations','contains unsupported value')
        ep=c.get('evidence_plan')
        if not isinstance(ep,dict) or not ep: fail(f'{cid}.evidence_plan','must be explicit, not empty shell')
        for k in ['screenshots','api','network','files']:
            if k not in ep or not isinstance(ep[k],list): fail(f'{cid}.evidence_plan.{k}','list required')
        if 'recording' not in ep: fail(f'{cid}.evidence_plan.recording','required')
        rec=ep['recording']
        if rec is not False and not isinstance(rec,dict): fail(f'{cid}.evidence_plan.recording','must be false or object')
        if isinstance(rec,dict) and rec.get('required') is True and rec.get('scope') not in {'batch','case'}: fail(f'{cid}.evidence_plan.recording.scope','batch|case required when recording is required')
        waiver=ep.get('waiver_reason')
        if main=='UI' and not ep['screenshots'] and not _recording_required(ep) and not waiver: fail(f'{cid}.evidence_plan','UI case requires screenshot/recording or waiver_reason')
        if main=='API' and not ep['api'] and not waiver: fail(f'{cid}.evidence_plan.api','API case requires request/response evidence or waiver_reason')
        if c.get('downloads_file') is True and not ep['files']: fail(f'{cid}.evidence_plan.files','download case requires files evidence')

    for bid,b in batch_by_id.items():
        for cid in b['case_ids']:
            if cid not in case_by_id: fail(f'{bid}.case_ids',f'contains unknown case {cid}')
            if case_by_id[cid].get('batch_id')!=bid: fail(f'{bid}.case_ids',f'{cid}.batch_id disagrees')
    for cid in case_by_id:
        if len(case_membership.get(cid,[]))!=1: fail(f'{cid}.batch_id','case must be assigned exactly once')

    graph={cid:[] for cid in case_by_id}
    for cid,c in case_by_id.items():
        deps=c.get('dependencies',c.get('depends_on',[])) or []
        if not isinstance(deps,list): fail(f'{cid}.dependencies','list required')
        for d in deps:
            if d not in case_by_id: fail(f'{cid}.dependencies',f'unknown case {d}')
            if d==cid: fail(f'{cid}.dependencies','self dependency forbidden')
            graph[cid].append(d)
            if batch_order[case_by_id[d]['batch_id']]>batch_order[c['batch_id']]: fail(f'{cid}.dependencies',f'dependency {d} is scheduled in a later batch')
    color={cid:0 for cid in graph}
    def dfs(n,stack):
        color[n]=1
        for d in graph[n]:
            if color[d]==1: fail(f'{n}.dependencies',f'cycle detected: {" -> ".join(stack+[n,d])}')
            if color[d]==0: dfs(d,stack+[n])
        color[n]=2
    for cid in graph:
        if color[cid]==0: dfs(cid,[])
    return {'ok':True,'cases':len(case_by_id),'batches':len(batch_by_id),'confirmed_cases_bound':True}


if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--input',required=True); a.add_argument('--confirmed-cases',required=True); a.add_argument('--allow-waiting-confirmation',action='store_true'); x=a.parse_args()
    cp=Path(x.confirmed_cases); confirmed=json.loads(cp.read_text(encoding='utf-8'))
    print(json.dumps(validate(json.loads(Path(x.input).read_text(encoding='utf-8')),not x.allow_waiting_confirmation,confirmed,sha256(cp)),ensure_ascii=False))
