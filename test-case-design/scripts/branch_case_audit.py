#!/usr/bin/env python3
"""Test-point 1.1 -> independent case instances + assertions evidence cross-check.

This is a closed-world, structural anti-regression gate. It does NOT decide whether
an asserted business rule is true or whether a system actually passed a test.
"""
import argparse
import json
from pathlib import Path

ORACLES = {'exact','rule_or_invariant','reference','metamorphic','statistical_or_rubric','pending_oracle'}
STATUSES = {'design_ready','needs_environment_capability','needs_data_method','needs_oracle','upstream_rule_blocked'}

class AuditError(ValueError):
    pass


def error(where, why):
    raise AuditError(f'{where}: {why}')


def filled(v):
    return isinstance(v, str) and bool(v.strip())


def entries(v, where):
    if not isinstance(v, list): error(where, '必须是列表')
    return v


def keyed(rows, key, where):
    m = {}
    for i, row in enumerate(entries(rows, where)):
        if not isinstance(row, dict) or not filled(row.get(key)):
            error(f'{where}[{i}].{key}', '缺少稳定标识')
        if row[key] in m: error(f'{where}[{i}].{key}', '重复')
        m[row[key]] = row
    return m


def nonempty_refs(v, allowed, where):
    refs = entries(v,where)
    if not refs or len(refs) != len(set(refs)):
        error(where,'需要至少一个互不重复的 ID')
    missing = set(refs)-set(allowed)
    if missing:error(where,f'未知引用: {sorted(missing)}')
    return refs


def audit(cases, points, ledger=None, *, candidate=False, legacy=False):
    if not isinstance(points,dict) or not isinstance(cases,dict):error('input','需要 JSON 对象')
    if cases.get('test_point_version') != points.get('design_version'):
        error('test_point_version','用例与测试点版本不匹配')
    if cases.get('business_model_version') != points.get('business_model_version'):
        error('business_model_version','上游业务模型版本不匹配')
    if ledger is not None and ledger.get('model_version') != points.get('business_model_version'):
        error('effect_ledger.model_version','上游有效需求账本版本不一致')
    design = points.get('branch_design')
    if not isinstance(design,dict):
        if legacy:
            return {'ok':True,'mode':'legacy-only-not-1.1-verified','ready_for_handoff':False,'warning':'旧输入没有 branch_design，不能声称完成测试点 1.1 分支承接'}
        error('points.branch_design','缺少测试点 1.1 的分支设计，禁止作为正式输入')
    if points.get('schema_version') != '1.1':
        error('points.schema_version','正式分支承接要求测试点 1.1；不可只添加空分支字段')

    branches = keyed(design.get('branches',[]),'branch_id','points.branch_design.branches')
    if not branches:error('branch_design.branches','不能为空')
    points_by_id=keyed(points.get('test_points',[]),'tp_id','points.test_points')
    claims={}
    if ledger is not None:
        for x in ledger.get('clauses',[]):
            if not isinstance(x,dict) or not filled(x.get('id')):error('effect_ledger.clauses','子条款缺失 ID')
            claims[x['id']]=x

    dispositions=keyed(design.get('claim_dispositions',[]),'claim_id','points.branch_design.claim_dispositions')
    for bid,branch in branches.items():
        for cid in branch.get('claim_ids',[]):
            disposition=dispositions.get(cid)
            if disposition is None or disposition.get('decision')!='covered':
                error(f'branches[{bid}].claim_ids',f'当前分支引用未覆盖或已取消的承诺: {cid}')
    tpls=keyed(cases.get('case_templates',[]),'case_id','case_templates')
    instances=keyed(cases.get('execution_instances',[]),'instance_id','execution_instances')
    assertion_index={}
    for cid,case in tpls.items():
        assertion_index[cid]=keyed(case.get('assertions',[]),'assertion_id',f'case_templates[{cid}].assertions')
    for iid,inst in instances.items():
        cid=inst.get('case_id')
        if cid not in tpls:error(f'execution_instances[{iid}].case_id','找不到用例模板')
        actual=set(inst.get('expected_assertion_ids',[]))
        if not actual <= set(assertion_index[cid]):error(f'execution_instances[{iid}].expected_assertion_ids','断言不属于用例模板')

    bd=cases.get('case_quality_design')
    if not isinstance(bd,dict):error('case_quality_design','缺少可验证的分支与数据/Oracle 承接')
    if bd.get('schema_version') != '1.0':error('case_quality_design.schema_version','需要 1.0')
    mappings=keyed(bd.get('branch_instances',[]),'branch_id','case_quality_design.branch_instances')
    missing=set(branches)-set(mappings)
    extra=set(mappings)-set(branches)
    if missing or extra:error('branch_instances',f'源分支无去向 {sorted(missing)} / 虚构分支 {sorted(extra)}')
    covered={}
    pending_instances=set()
    blocked=[]
    for bid,branch in branches.items():
        rec=mappings[bid]
        status=rec.get('status')
        if status not in {'covered','pending'}:error(f'branch_instances[{bid}].status','必须 covered 或 pending')
        if not set(branch.get('test_point_ids',[]))<=set(points_by_id):error(f'branch[{bid}].test_point_ids','上游指向未知 TP')
        if claims:
            for claim_id in branch.get('claim_ids',[]):
                if claim_id not in claims:error(f'branch[{bid}].claim_ids',f'未知有效子条款 {claim_id}')
                if claims[claim_id].get('scope') not in {'active','dependency'}:
                    error(f'branch[{bid}].claim_ids',f'非当前有效条款 {claim_id} 进入了执行分支')
        if status=='pending':
            if not candidate:error(f'branch_instances[{bid}]','未决分支不能正式放行')
            if not filled(rec.get('question_id')) or not filled(rec.get('reason')):
                error(f'branch_instances[{bid}]','待确认需要问题编号及具体原因')
            pending_instances.update(rec.get('instance_ids',[]) or [])
            blocked.append(bid);continue
        mapped=nonempty_refs(rec.get('instance_ids'),instances,f'branch_instances[{bid}].instance_ids')
        refs=entries(rec.get('assertion_refs'),f'branch_instances[{bid}].assertion_refs')
        if not refs:error(f'branch_instances[{bid}].assertion_refs','必须绑定实例内实际断言')
        matched=set()
        for i,ref in enumerate(refs):
            if not isinstance(ref,dict):error(f'branch_instances[{bid}].assertion_refs[{i}]','必须是对象')
            iid,aid=ref.get('instance_id'),ref.get('assertion_id')
            if iid not in mapped:error(f'branch_instances[{bid}].assertion_refs[{i}]','实例没有归属此分支')
            inst=instances[iid];assertion=assertion_index[inst['case_id']].get(aid)
            if assertion is None or aid not in inst.get('expected_assertion_ids',[]):
                error(f'branch_instances[{bid}].assertion_refs[{i}]','断言没有被实例实际承接')
            if not set(assertion.get('test_point_ids',[]))&set(branch.get('test_point_ids',[]))&set(inst.get('test_point_ids',[])):
                error(f'branch_instances[{bid}].assertion_refs[{i}]','分支、实例与断言没有共同的测试点')
            matched.add(iid)
        if set(mapped)!=matched:error(f'branch_instances[{bid}]','有实例列入覆盖但没有自己的有效断言')
        for required in ('condition_preserved','result_discriminator'):
            if not filled(rec.get(required)):error(f'branch_instances[{bid}].{required}','须说明条件与结果如何独立辨别')
        covered[bid]=set(mapped)

    # Do not let "required_variations" vanish when TPs were merged.
    vr=entries(bd.get('variation_reviews'), 'case_quality_design.variation_reviews')
    varmap={}
    for i,v in enumerate(vr):
        if not isinstance(v,dict):error(f'variation_reviews[{i}]','须为对象')
        key=(v.get('branch_id'),v.get('variation'))
        if not all(filled(k) for k in key) or key in varmap:error(f'variation_reviews[{i}]','分支/变体标识缺失或重复')
        varmap[key]=v
    for bid,branch in branches.items():
        req=branch.get('case_handoff',{}).get('required_variations',[])
        if req is None:req=[]
        if not isinstance(req,list):error(f'branches[{bid}].required_variations','必须为列表')
        for variation in req:
            key=(bid,variation)
            if key not in varmap:error(f'variation_reviews[{bid}]',f'未承接必须保留的条件变体 {variation}')
            v=varmap[key]
            s=v.get('status')
            if s not in {'covered','pending','not_applicable'}:error(f'variation_reviews[{key}].status','非法')
            if s=='covered':
                if bid not in covered:error(f'variation_reviews[{key}]','源分支未覆盖')
                nonempty_refs(v.get('instance_ids'),covered[bid],f'variation_reviews[{key}].instance_ids')
                if not filled(v.get('distinguishing_data')) or not filled(v.get('expected_difference')):
                    error(f'variation_reviews[{key}]','缺少决定性数据条件或差异期望')
            else:
                if not filled(v.get('reason')):error(f'variation_reviews[{key}]','排除或待定必须说明为什么')
                if s=='pending':
                    if not candidate or not filled(v.get('question_id')):error(f'variation_reviews[{key}]','未决不能正式放行，候选需问题 ID')
                    blocked.append(f'{bid}:{variation}')
                if s=='not_applicable' and not filled(v.get('source_basis')):
                    error(f'variation_reviews[{key}]','不能随意移除上游必选变体，必须有更新来源证据')
    if set(varmap)-{(bid,v) for bid,b in branches.items() for v in (b.get('case_handoff',{}).get('required_variations',[]) or [])}:
        error('variation_reviews','出现不属于上游必选变体的可疑记录')

    # Each instance actually used in branch mapping must have a data+Oracle contract.
    readiness=keyed(bd.get('instance_readiness',[]),'instance_id','case_quality_design.instance_readiness')
    used=set().union(*covered.values()) if covered else set()
    extras=set(readiness)-used-pending_instances if candidate else set(readiness)-used
    if used-set(readiness) or extras:
        error('instance_readiness',f'数据/Oracle 契约缺失 {sorted(used-set(readiness))} / 多余 {sorted(extras)}')
    for iid in used:
        record=readiness[iid]
        status=record.get('design_status')
        if status not in STATUSES:error(f'instance_readiness[{iid}].design_status','未定义状态')
        data=record.get('data_contract')
        if not isinstance(data,dict):error(f'instance_readiness[{iid}].data_contract','须为对象')
        for k in ('actors','objects','initial_facts','decisive_values','setup_approach','readiness_check','isolation_cleanup'):
            if not filled(data.get(k)) and not (isinstance(data.get(k),list) and len(data[k])>0 and all(filled(y) for y in data[k])):
                error(f'instance_readiness[{iid}].data_contract.{k}','缺少可交接的数据要求')
        oracle_rows=keyed(record.get('oracle_contracts',[]),'assertion_id',f'instance_readiness[{iid}].oracle_contracts')
        inst=instances[iid];actual=set(inst.get('expected_assertion_ids',[]))
        if set(oracle_rows)!=actual:error(f'instance_readiness[{iid}].oracle_contracts','必须逐断言说明独立 Oracle，不能用一条 Toast 代替')
        oracle_block=False
        for aid,x in oracle_rows.items():
            ot=x.get('oracle_type')
            if ot not in ORACLES:error(f'oracle_contracts[{iid}/{aid}].oracle_type','非法 Oracle 类型')
            for k in ('basis','observed_fact','decision_rule','evidence_collection'):
                if not filled(x.get(k)):error(f'oracle_contracts[{iid}/{aid}].{k}','缺少判定证据')
            if ot=='statistical_or_rubric':
                if not filled(x.get('evaluation_rubric')) or not filled(x.get('sampling_plan')) or not filled(x.get('acceptance_criterion')):
                    error(f'oracle_contracts[{iid}/{aid}]','AI 概率质量须给评测指标、取样与验收标准')
            if ot=='pending_oracle':oracle_block=True
        if status=='design_ready' and oracle_block:error(f'instance_readiness[{iid}]','未建立 Oracle 却标记设计完成')
        if status!='design_ready':
            if not candidate or not filled(record.get('dependency')):
                error(f'instance_readiness[{iid}]','有未决数据/Oracle/环境依赖，正式不可放行')
            blocked.append(iid)

    # Critical task paths: individual branches do not automatically prove a continuous chain.
    paths={r.get('path_id'):r for r in design.get('path_reviews',[]) if isinstance(r,dict) and r.get('status')=='covered'}
    path_reviews=keyed(bd.get('path_case_reviews',[]),'path_id','case_quality_design.path_case_reviews')
    if set(paths)!=set(path_reviews):
        error('path_case_reviews',f'关键链未审 {sorted(set(paths)-set(path_reviews))} / 虚构链 {sorted(set(path_reviews)-set(paths))}')
    for pid,src in paths.items():
        dst=path_reviews[pid]
        if dst.get('status')=='pending':
            if not candidate or not filled(dst.get('question_id')) or not filled(dst.get('reason')):
                error(f'path_case_reviews[{pid}]','长链未决不能正式放行')
            blocked.append(pid);continue
        if dst.get('status')!='covered':error(f'path_case_reviews[{pid}].status','须覆盖或待确认')
        for k in ('terminal_branch_ids','interruption_branch_ids','interleaving_branch_ids'):
            source=set(src.get(k,[]) or [])
            case=set(dst.get(k,[]) or [])
            if source!=case:error(f'path_case_reviews[{pid}].{k}',f'长链分支遗漏 {sorted(source-case)} / 多余 {sorted(case-source)}')
            if not source<=set(covered):error(f'path_case_reviews[{pid}].{k}','源分支尚无实际实例和断言')
        chains=nonempty_refs(dst.get('chain_instance_ids'),instances,f'path_case_reviews[{pid}].chain_instance_ids')
        for iid in chains:
            if iid not in used:error(f'path_case_reviews[{pid}]','连续链路实例未在分支承接清单中')
        if not filled(dst.get('continuity_oracle')) or not filled(dst.get('intermediate_fact')):
            error(f'path_case_reviews[{pid}]','必须写明中途事实与终态一致性的判断依据')
        # An atom-point assertion only does not prove an end-to-end chain.
        chain_cases=[tpls[instances[i]['case_id']] for i in chains]
        if not any(c.get('case_type') in {'long_flow','cross_module'} for c in chain_cases):
            error(f'path_case_reviews[{pid}]','未提供真正的 long_flow/cross_module 连续执行实例')
        for bid in set().union(*(set(src.get(k,[]) or []) for k in ('terminal_branch_ids','interruption_branch_ids','interleaving_branch_ids'))):
            if not (set(chains) & covered[bid]):
                error(f'path_case_reviews[{pid}]',f'分支 {bid} 只有零散的原子实例，未包含在连续链路执行中')

    # Every executed instance must have an independently grounded branch, not just TP ID.
    orphan=set(instances)-used-(pending_instances if candidate else set())
    if orphan:
        error('branch_instances',f'无来源分支的用例执行实例 {sorted(orphan)}')

    # A/B discriminators require cases that can distinguish the two outcomes.
    ds={r.get('discriminator_id'):r for r in design.get('discriminator_reviews',[])
        if isinstance(r,dict) and r.get('status')=='covered'}
    dr=keyed(bd.get('discriminator_case_reviews',[]),'discriminator_id', 'case_quality_design.discriminator_case_reviews')
    if set(ds)!=set(dr):
        error('discriminator_case_reviews',f'未验收正反辨别对 {sorted(set(ds)-set(dr))} / 多余 {sorted(set(dr)-set(ds))}')
    for did,src in ds.items():
        rec=dr[did];source_branches=set(src.get('branch_ids',[]))
        if set(rec.get('branch_ids',[]))!=source_branches:
            error(f'discriminator_case_reviews[{did}]','必须承接正反两侧源分支')
        if rec.get('status')=='pending':
            if not candidate or not filled(rec.get('question_id')) or not filled(rec.get('reason')):
                error(f'discriminator_case_reviews[{did}]','未决只能留在候选版且写明问题')
            blocked.append(did);continue
        if rec.get('status')!='covered':error(f'discriminator_case_reviews[{did}].status','非法状态')
        if not source_branches<=set(covered):error(f'discriminator_case_reviews[{did}]','某侧没有用例实例')
        instances_by_branch=[covered[bid] for bid in source_branches]
        if len(source_branches)>=2 and len(set().union(*instances_by_branch))<2:
            error(f'discriminator_case_reviews[{did}]','相反条件不能仅由同一单次执行充当正反两侧')
        if not filled(rec.get('expected_difference')) or not filled(rec.get('detection_evidence')):
            error(f'discriminator_case_reviews[{did}]','必须说明如何判别两侧不同的业务结果')

    if blocked and not candidate:error('ready_for_handoff','存在未完成项')
    return {'ok':True,'mode':'test-point-1.1','branches':len(branches),
            'covered_branches':len(covered),'required_variations':len(varmap),
            'covered_paths':len(paths),'discriminators':len(ds),'instances_with_data_oracle':len(used),
            'blocked':sorted(set(blocked)),'ready_for_handoff':not blocked}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True,help='internal/design/test-cases.json')
    p.add_argument('--points',required=True,help='test-points.json for TP Skill 1.1')
    p.add_argument('--ledger',help='business-understanding Skill 3.3 effect-ledger.json (recommended)')
    p.add_argument('--candidate',action='store_true',help='allow explicit blocked scenarios; never promote to ready')
    p.add_argument('--legacy-input',action='store_true',help='for inspection only, do not pretend old TP has branches')
    a=p.parse_args()
    read=lambda x:json.loads(Path(x).read_text(encoding='utf-8'))
    try:
        report=audit(read(a.input),read(a.points),read(a.ledger) if a.ledger else None,candidate=a.candidate,legacy=a.legacy_input)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        if not report['ready_for_handoff'] and not (a.candidate or a.legacy_input):raise SystemExit(1)
    except (AuditError,KeyError,TypeError) as e:
        print(json.dumps({'ok':False,'error':str(e)},ensure_ascii=False,indent=2))
        raise SystemExit(1)

if __name__=='__main__':main()
