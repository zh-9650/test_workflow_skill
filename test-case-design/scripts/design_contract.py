import argparse, json
from pathlib import Path

METHODS={'等价类','边界值','判定表','因果图','状态迁移','场景法','组合测试','错误推测'}
VAGUE_EXACT={'结果正确','正常展示','页面正常展示','正常返回','返回正常','符合预期','符合规则','按实际实现','按最终口径','无异常','操作成功即可继续','展示正常','页面展示正常','功能正常','运行正常','显示正常'}
VAGUE_PHRASES={'没有问题','没问题','无问题','没有任何问题','无任何问题','没有异常','没有任何异常','无任何异常','均正常','都正常','一切正常','无报错','没有报错'}
VAGUE_STEP={'进行相关操作','执行相关操作','输入合法数据','输入正常数据','按要求操作','进行操作','继续操作'}
POINT_CHECKS={'coverage_checked','method_derivation_checked','state_flow_checked','linkage_checked','long_flow_checked','dedup_checked'}
CASE_CHECKS={'point_coverage_checked','executability_checked','expected_results_checked','intermediate_assertions_checked','dedup_checked','readability_checked'}


def fail(path,msg): raise AssertionError(f'{path}: {msg}')
def text(v): return isinstance(v,str) and bool(v.strip())
def _canon(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))

def _is_vague_expected(v):
    if not text(v): return True
    s=''.join(v.strip().split()).rstrip('。.!！')
    if s in VAGUE_EXACT: return True
    has_vague_term = any(p in s for p in VAGUE_PHRASES) or (('没有' in s or '无' in s) and ('问题' in s or '异常' in s or '报错' in s))
    if has_vague_term:
        has_concrete = any(c in s for c in ['"', '“', '”', "'", '‘', '’', ':', '：', '=', '0','1','2','3','4','5','6','7','8','9'])
        if not has_concrete: return True
    return False

def _is_vague_step(v):
    if not text(v): return True
    s=''.join(v.strip().split()).rstrip('。.!！')
    return s in VAGUE_STEP


def _validate_technique(p):
    methods=p.get('methods',[]); analysis=p.get('technique_analysis',{})
    if not methods: fail(f'{p.get("id","<unknown>")}.methods','at least one applicable method required')
    if not set(methods)<=METHODS: fail(f'{p["id"]}.methods','unsupported method')
    for m in methods:
        a=analysis.get(m)
        if not isinstance(a,dict): fail(f'{p["id"]}.technique_analysis.{m}','real derivation structure required')
        if m=='边界值' and (not a.get('source_rule') or not isinstance(a.get('derived_values'),list) or len(a['derived_values'])<3): fail(f'{p["id"]}.边界值','source_rule + derived_values required')
        if m=='判定表' and (not a.get('conditions') or not a.get('actions') or not a.get('rules')): fail(f'{p["id"]}.判定表','conditions/actions/rules required')
        if m=='状态迁移' and (not a.get('states') or not a.get('transitions') or 'invalid_transitions' not in a): fail(f'{p["id"]}.状态迁移','states/transitions/invalid_transitions required')
        if m=='场景法' and (not a.get('main_flow') or 'alternative_flows' not in a or 'failure_flows' not in a): fail(f'{p["id"]}.场景法','main/alternative/failure flows required')
        if m=='等价类' and (not a.get('valid_classes') or not a.get('invalid_classes')): fail(f'{p["id"]}.等价类','valid_classes/invalid_classes required')
        if m=='因果图' and (not a.get('causes') or not a.get('effects')): fail(f'{p["id"]}.因果图','causes/effects required')
        if m=='组合测试' and (not a.get('parameters') or not a.get('generated_combinations')): fail(f'{p["id"]}.组合测试','parameters/generated_combinations required')
        if m=='错误推测' and not a.get('failure_mechanisms'): fail(f'{p["id"]}.错误推测','failure_mechanisms required')


def _review(review,checks,path):
    if not isinstance(review,dict) or review.get('status')!='passed': fail(path+'.status','must be passed')
    got=review.get('checks',{})
    for k in checks:
        if got.get(k) is not True: fail(f'{path}.checks.{k}','must be true')


def validate_points(v, require_confirmed=True):
    pts=v.get('test_points',[])
    if not isinstance(pts,list) or not pts: fail('test_points','non-empty required')
    ids=[]
    for i,p in enumerate(pts):
        path=f'test_points[{i}]'; pid=p.get('id')
        if not text(pid): fail(path+'.id','required')
        if not text(p.get('title',p.get('test_point',''))): fail(path+'.title','human-readable test point required')
        if not text(p.get('module','')): fail(path+'.module','business module required')
        _validate_technique(p); ids.append(pid)
    if len(ids)!=len(set(ids)): fail('test_points.id','duplicate')
    _review(v.get('test_points_self_review',v.get('self_review')),POINT_CHECKS,'test_points_self_review')
    if require_confirmed and v.get('test_points_user_confirmation',{}).get('status')!='confirmed': fail('test_points_user_confirmation.status','must be confirmed before Case generation')
    return {'ok':True,'test_points':len(pts)}


def validate_cases(v, require_confirmed=True, confirmed_points=None):
    validate_points(v, require_confirmed=False)
    if confirmed_points is not None:
        validate_points(confirmed_points, require_confirmed=False)
        if _canon(v.get('test_points',[])) != _canon(confirmed_points.get('test_points',[])):
            fail('test_points','Case generation must use the exact currently confirmed test-point set; return to test-point stage for any additions/changes')
    if confirmed_points is None and require_confirmed and v.get('test_points_confirmed') is not True: fail('test_points_confirmed','must be true when no Router confirmation binding is supplied')
    pts=v['test_points']; cases=v.get('cases',[])
    if not isinstance(cases,list) or not cases: fail('cases','non-empty required')
    pids={p['id'] for p in pts}; covered=set(); cids=[]
    for idx,c in enumerate(cases):
        path=f'cases[{idx}]'; cid=c.get('case_id')
        if not text(cid): fail(path+'.case_id','required')
        if cid in cids: fail(path+'.case_id',f'duplicate {cid}')
        cids.append(cid)
        if not text(c.get('title',c.get('name',''))): fail(f'{cid}.title','human-readable case title required')
        tpids=c.get('test_point_ids',[])
        if not isinstance(tpids,list) or not tpids: fail(f'{cid}.test_point_ids','must reference one or more already confirmed test points')
        unknown=set(tpids)-pids
        if unknown: fail(f'{cid}.test_point_ids',f'unknown/unconfirmed test points {sorted(unknown)}')
        covered.update(tpids)
        if not text(c.get('target_action','')): fail(f'{cid}.target_action','explicit tested business action required')
        steps=c.get('steps')
        if not isinstance(steps,list) or not steps: fail(f'{cid}.steps','non-empty required')
        for j,step in enumerate(steps):
            sp=f'{cid}.steps[{j}]'
            if not isinstance(step,dict): fail(sp,'step object required')
            action=step.get('action',step.get('operation'))
            if not text(action): fail(sp+'.action','executable action required')
            if _is_vague_step(action): fail(sp+'.action',f'vague/non-executable step forbidden: {action}')
        exp=c.get('expected_results')
        if not isinstance(exp,list) or not exp: fail(f'{cid}.expected_results','non-empty required')
        exp_ids=[]
        for i,e in enumerate(exp):
            ep=f'{cid}.expected_results[{i}]'
            if not isinstance(e,dict): fail(ep,'object with stable id and expected text required')
            eid=e.get('id'); t=e.get('expected','')
            if not text(eid): fail(ep+'.id','stable expected id required')
            if not text(t): fail(ep+'.expected','observable expected text required')
            if _is_vague_expected(t): fail(ep+'.expected',f'vague expected forbidden: {t}')
            exp_ids.append(eid)
        if len(exp_ids)!=len(set(exp_ids)): fail(f'{cid}.expected_results','duplicate expected id')
        if c.get('complex_flow') is True and not c.get('intermediate_assertions'):
            fail(f'{cid}.intermediate_assertions','complex business flow requires intermediate assertions')
        if c.get('preconditions_applicable') is not False and not c.get('preconditions'): fail(f'{cid}.preconditions','required unless explicitly not applicable')
        if c.get('test_data_applicable') is not False and not c.get('test_data'): fail(f'{cid}.test_data','required unless explicitly not applicable')
    missing=sorted(pids-covered)
    if missing: fail('coverage',f'uncovered confirmed test points: {missing}')
    _review(v.get('test_cases_self_review'),CASE_CHECKS,'test_cases_self_review')
    if require_confirmed and v.get('test_cases_user_confirmation',{}).get('status')!='confirmed': fail('test_cases_user_confirmation.status','must be confirmed before execution planning')
    return {'ok':True,'test_points':len(pts),'cases':len(cases),'coverage':f'{len(pids)}/{len(pids)}'}


def validate(v,stage='all',require_confirmed=True,confirmed_points=None):
    if stage=='points': return validate_points(v,require_confirmed)
    if stage=='cases': return validate_cases(v,require_confirmed,confirmed_points=confirmed_points)
    return validate_cases(v,require_confirmed,confirmed_points=confirmed_points)


if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--input',required=True); a.add_argument('--stage',choices=['points','cases','all'],default='all'); a.add_argument('--allow-waiting-confirmation',action='store_true'); a.add_argument('--confirmed-points'); x=a.parse_args()
    cp=json.loads(Path(x.confirmed_points).read_text(encoding='utf-8')) if x.confirmed_points else None
    print(json.dumps(validate(json.loads(Path(x.input).read_text(encoding='utf-8')),x.stage,not x.allow_waiting_confirmation,confirmed_points=cp),ensure_ascii=False))
