import argparse, json
from pathlib import Path

MAIN = {'UI','API','人工'}
AUX = {'UI','API','数据库只读','Network','日志','文件','其他系统'}

def fail(path, msg):
    raise AssertionError(f'{path}: {msg}')

def _recording_required(ep):
    rec = ep.get('recording')
    return isinstance(rec, dict) and rec.get('required') is True

def validate(plan):
    cases = plan.get('cases')
    batches = plan.get('batches')
    if not isinstance(cases, list) or not cases: fail('cases','required and non-empty')
    if not isinstance(batches, list) or not batches: fail('batches','required and non-empty')
    sr = plan.get('self_review', {})
    if sr.get('status') != 'passed': fail('self_review.status','must be passed')
    if plan.get('user_confirmation',{}).get('status') != 'confirmed': fail('user_confirmation.status','execution plan must be confirmed')

    batch_ids=[]; batch_by_id={}; case_membership={}
    for i,b in enumerate(batches):
        p=f'batches[{i}]'; bid=b.get('id')
        if not bid: fail(p+'.id','required')
        if bid in batch_by_id: fail(p+'.id',f'duplicate {bid}')
        batch_ids.append(bid); batch_by_id[bid]=b
        if not isinstance(b.get('parallel_safe'),bool): fail(p+'.parallel_safe','boolean required')
        if not isinstance(b.get('case_ids'),list) or not b['case_ids']: fail(p+'.case_ids','non-empty list required')
        if len(set(b['case_ids'])) != len(b['case_ids']): fail(p+'.case_ids','duplicate case id in batch')
        for cid in b['case_ids']: case_membership.setdefault(cid,[]).append(bid)
    batch_order={bid:i for i,bid in enumerate(batch_ids)}

    case_by_id={}
    for i,c in enumerate(cases):
        p=f'cases[{i}]'; cid=c.get('case_id')
        if not cid: fail(p+'.case_id','required')
        if cid in case_by_id: fail(p+'.case_id',f'duplicate {cid}')
        case_by_id[cid]=c
        bid=c.get('batch_id')
        if bid not in batch_by_id: fail(f'{cid}.batch_id',f'unknown batch {bid}')
        if case_membership.get(cid) != [bid]: fail(f'{cid}.batch_id',f'must appear exactly once in {bid}.case_ids; actual={case_membership.get(cid)}')
        main=c.get('primary_execution')
        if main not in MAIN: fail(f'{cid}.primary_execution',f'invalid {main}')
        if c.get('ui_required') is True and main!='UI': fail(f'{cid}.primary_execution','UI-required case cannot use API/manual')
        if not set(c.get('supporting_observations',c.get('aux_validation',[]))) <= AUX: fail(f'{cid}.supporting_observations','contains unsupported value')
        ep=c.get('evidence_plan')
        if not isinstance(ep,dict) or not ep: fail(f'{cid}.evidence_plan','must be explicit, not empty shell')
        for k in ['screenshots','api','network','files']:
            if k not in ep or not isinstance(ep[k],list): fail(f'{cid}.evidence_plan.{k}','list required')
        if 'recording' not in ep: fail(f'{cid}.evidence_plan.recording','required')
        rec=ep['recording']
        if rec is not False and not isinstance(rec,dict): fail(f'{cid}.evidence_plan.recording','must be false or object')
        if isinstance(rec,dict) and rec.get('required') is True and rec.get('scope') not in {'batch','case'}:
            fail(f'{cid}.evidence_plan.recording.scope','batch|case required when recording is required')
        waiver=ep.get('waiver_reason')
        if main=='UI' and not ep['screenshots'] and not _recording_required(ep) and not waiver:
            fail(f'{cid}.evidence_plan','UI case requires screenshot/recording or waiver_reason')
        if main=='API' and not ep['api'] and not waiver:
            fail(f'{cid}.evidence_plan.api','API case requires request/response evidence or waiver_reason')
        if c.get('downloads_file') is True and not ep['files']:
            fail(f'{cid}.evidence_plan.files','download case requires files evidence')

    # batch references must be real cases and ownership must agree in both directions
    for bid,b in batch_by_id.items():
        for cid in b['case_ids']:
            if cid not in case_by_id: fail(f'{bid}.case_ids',f'contains unknown case {cid}')
            if case_by_id[cid].get('batch_id') != bid: fail(f'{bid}.case_ids',f'{cid}.batch_id disagrees')
    for cid in case_by_id:
        if cid not in case_membership: fail(f'{cid}.batch_id','case is not assigned to any batch')
        if len(case_membership[cid]) != 1: fail(f'{cid}.batch_id',f'case appears in multiple batches {case_membership[cid]}')

    # dependencies: exist, not self, acyclic, and batch order cannot violate dependency
    graph={cid:[] for cid in case_by_id}
    for cid,c in case_by_id.items():
        deps=c.get('dependencies',c.get('depends_on',[])) or []
        if not isinstance(deps,list): fail(f'{cid}.dependencies','list required')
        for d in deps:
            if d not in case_by_id: fail(f'{cid}.dependencies',f'unknown case {d}')
            if d==cid: fail(f'{cid}.dependencies','self dependency forbidden')
            graph[cid].append(d)
            if batch_order[case_by_id[d]['batch_id']] > batch_order[c['batch_id']]:
                fail(f'{cid}.dependencies',f'dependency {d} is scheduled in a later batch')
    color={cid:0 for cid in graph}
    def dfs(n,stack):
        color[n]=1
        for d in graph[n]:
            if color[d]==1: fail(f'{n}.dependencies',f'cycle detected: {" -> ".join(stack+[n,d])}')
            if color[d]==0: dfs(d,stack+[n])
        color[n]=2
    for cid in graph:
        if color[cid]==0: dfs(cid,[])
    return {'ok':True,'cases':len(case_by_id),'batches':len(batch_by_id)}

if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--input',required=True); x=a.parse_args()
    print(json.dumps(validate(json.loads(Path(x.input).read_text(encoding='utf-8'))),ensure_ascii=False))
