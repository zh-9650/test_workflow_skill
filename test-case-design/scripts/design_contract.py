import argparse, json, re
from pathlib import Path
METHODS={'等价类','边界值','判定表','因果图','状态迁移','场景法','组合测试','错误推测'}
VAGUE_PATTERNS=[r'结果正确',r'正常展示',r'正常返回',r'符合预期',r'符合规则',r'按实际实现',r'按最终口径',r'无异常',r'功能正常',r'操作成功']

def fail(path,msg): raise AssertionError(f'{path}: {msg}')

def _validate_technique(p):
    methods=p.get('methods',[]); analysis=p.get('technique_analysis',{})
    for m in methods:
        a=analysis.get(m)
        if not isinstance(a,dict): fail(f'{p["id"]}.technique_analysis.{m}','derivation structure required')
        if m=='边界值':
            if not a.get('source_rule') or not isinstance(a.get('derived_values'),list) or len(a['derived_values'])<3: fail(f'{p["id"]}.边界值','source_rule + derived_values required')
        elif m=='判定表':
            if not a.get('conditions') or not a.get('actions') or not a.get('rules'): fail(f'{p["id"]}.判定表','conditions/actions/rules required')
        elif m=='状态迁移':
            if not a.get('states') or not a.get('transitions') or 'invalid_transitions' not in a: fail(f'{p["id"]}.状态迁移','states/transitions/invalid_transitions required')
        elif m=='场景法':
            if not a.get('main_flow') or 'alternative_flows' not in a or 'failure_flows' not in a: fail(f'{p["id"]}.场景法','main/alternative/failure flows required')
        elif m=='等价类':
            if not a.get('valid_classes') or not a.get('invalid_classes'): fail(f'{p["id"]}.等价类','valid_classes/invalid_classes required')
        elif m=='因果图':
            if not a.get('causes') or not a.get('effects'): fail(f'{p["id"]}.因果图','causes/effects required')
        elif m=='组合测试':
            if not a.get('parameters') or not a.get('generated_combinations'): fail(f'{p["id"]}.组合测试','parameters/generated_combinations required')
        elif m=='错误推测':
            if not a.get('failure_mechanisms'): fail(f'{p["id"]}.错误推测','failure_mechanisms required')

def _is_vague(text):
    return any(re.search(pattern,text) for pattern in VAGUE_PATTERNS)

def _validate_point(p,i):
    if not isinstance(p,dict): fail(f'test_points[{i}]','must be an object')
    for k in ['id','test_point','methods','technique_analysis']:
        if k not in p: fail(f'test_points[{i}].{k}','required')
    if not isinstance(p['test_point'],str) or not p['test_point'].strip(): fail(f'test_points[{i}].test_point','non-empty required')
    methods=p.get('methods')
    if not isinstance(methods,list) or not methods: fail(f'{p["id"]}.methods','at least one method required')
    if not set(methods)<=METHODS: fail(f'{p["id"]}.methods','unsupported method')
    _validate_technique(p)

def _review_status(v,key='self_review'):
    value=v.get(key,v.get('self_review',{}))
    if isinstance(value,dict): return value.get('status')
    return None

def validate(v):
    mode=v.get('mode','full')
    if mode not in {'test-points','test-cases','full'}: fail('mode','test-points|test-cases|full required')
    pts=v.get('test_points',[]); cases=v.get('cases',[])
    if not isinstance(pts,list) or not pts: fail('test_points','required and non-empty')
    pids={p.get('id') for p in pts}
    if None in pids or len(pids)!=len(pts): fail('test_points.id','missing or duplicate')
    for i,p in enumerate(pts): _validate_point(p,i)
    if mode=='test-points':
        if v.get('business_understanding_confirmed') is not True and v.get('business_confirmation_status')!='confirmed': fail('business_understanding_confirmed','business understanding must be confirmed')
        if _review_status(v,'test_points_self_review')!='passed' and _review_status(v)!='passed': fail('test_points_self_review.status','must be passed')
        if cases: fail('cases','must be empty in test-points mode')
        return {'ok':True,'mode':mode,'test_points':len(pts),'cases':0,'coverage':None}
    if not isinstance(cases,list) or not cases: fail('cases','required and non-empty')
    if v.get('test_points_confirmed') is not True: fail('test_points_confirmed','must be true')
    if mode=='full' and v.get('test_cases_confirmed') is not True: fail('test_cases_confirmed','must be true')
    covered=set()
    for c in cases:
        cid=c.get('case_id') or '<unknown>'
        tpids=c.get('test_point_ids',[])
        if not tpids:
            if not (c.get('added_after_point_review') is True and c.get('reason')): fail(f'{cid}.test_point_ids','must reference test point or record approved post-review addition')
            backfill=c.get('backfilled_test_point_id')
            if not backfill or backfill not in pids: fail(f'{cid}.backfilled_test_point_id','post-review case must be backfilled into a real test point')
            tpids=[backfill]
        unknown=set(tpids)-pids
        if unknown: fail(f'{cid}.test_point_ids',f'unknown test points {sorted(unknown)}')
        covered.update(tpids)
        steps=c.get('steps')
        if not isinstance(steps,list) or not steps: fail(f'{cid}.steps','non-empty required')
        exp=c.get('expected_results')
        if not isinstance(exp,list) or not exp: fail(f'{cid}.expected_results','at least one required')
        for i,e in enumerate(exp):
            text=e if isinstance(e,str) else e.get('expected','')
            if not text.strip(): fail(f'{cid}.expected_results[{i}]','expected text required')
            if _is_vague(text.strip()): fail(f'{cid}.expected_results[{i}]',f'vague expected forbidden: {text}')
        if c.get('preconditions_applicable') is False:
            if c.get('preconditions') not in (None,[],{}): fail(f'{cid}.preconditions','must be empty when not applicable')
        elif not c.get('preconditions'): fail(f'{cid}.preconditions','required unless preconditions_applicable=false')
        if c.get('test_data_applicable') is False:
            if c.get('test_data') not in (None,[],{}): fail(f'{cid}.test_data','must be empty when not applicable')
        elif not c.get('test_data'): fail(f'{cid}.test_data','required unless test_data_applicable=false')
        if c.get('business_chain') is True or c.get('case_type') in {'business_chain','long_flow'}:
            assertions=c.get('intermediate_assertions')
            if not isinstance(assertions,list) or not assertions: fail(f'{cid}.intermediate_assertions','required for a business chain case')
            for j,a in enumerate(assertions):
                if not isinstance(a,dict) or not a.get('step') or not a.get('expected'): fail(f'{cid}.intermediate_assertions[{j}]','step and expected required')
    missing=sorted(pids-covered)
    if missing: fail('coverage',f'uncovered test points: {missing}')
    if v.get('self_review',{}).get('status')!='passed': fail('self_review.status','must be passed')
    return {'ok':True,'test_points':len(pts),'cases':len(cases),'coverage':f'{len(pids)}/{len(pids)}'}

if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--input',required=True); x=a.parse_args(); print(json.dumps(validate(json.loads(Path(x.input).read_text(encoding='utf-8'))),ensure_ascii=False))
