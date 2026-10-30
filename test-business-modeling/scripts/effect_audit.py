#!/usr/bin/env python3
"""Read-only, generic cross-artifact effect/scope audit; never claims semantic correctness.

usage: python scripts/effect_audit.py --model MODEL.json --ledger evidence/effect-ledger.json [--active-csv ...] [--strict]
"""
from __future__ import annotations
import argparse, csv, json, re, sys
from pathlib import Path

SCOPES = {'active', 'excluded', 'superseded', 'unresolved', 'dependency'}

def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def audit(model, ledger, active_rows=None, strict=False):
    errors, flags, info = [], [], []
    def err(k, s): errors.append({'code': k, 'detail': s})
    def flag(k, s): flags.append({'code': k, 'detail': s})
    def filled(v): return isinstance(v, str) and bool(v.strip())
    all_refs = set()
    for name, id_key in [('modules','module_id'),('capabilities','capability_id'),('business_objects','object_id'),('state_machines','state_machine_id'),('relationships','relationship_id'),('events','event_id'),('rules','rule_id'),('invariants','invariant_id'),('cross_module_flows','flow_id')]:
        for item in model.get(name, []):
            if isinstance(item, dict) and filled(item.get(id_key)): all_refs.add(item[id_key])
    unknown_refs = {i.get('unknown_id') for i in model.get('unknowns',[]) if isinstance(i,dict)}
    cs = ledger.get('clauses', [])
    if not cs: err('NO_CLAUSES', '没有独立业务承诺/范围判定清单；不能以原始条款编号总数代替有效子句')
    cids = set(); active=[]; retired=[]; unresolved=[]
    for i,c in enumerate(cs):
        p=f'clauses[{i}]'; cid=c.get('id')
        if not filled(cid) or cid in cids:err('CLAUSE_ID',p+' 编号缺失或重复')
        cids.add(cid)
        if not (filled(c.get('source')) and filled(c.get('source_location')) and filled(c.get('atomic_claim'))): err('SOURCE_EVIDENCE',p+' 缺原始证据定位或独立业务子句')
        s=c.get('scope')
        if s not in SCOPES:err('SCOPE',p+' 范围效力不合法');continue
        if s=='active':
            active.append(c)
            if not filled(c.get('current_expected')):err('NO_ACTIVE_EXPECTATION',p+' 有效条款没有当前正确结果')
            refs=c.get('model_refs',[])
            if not refs and not c.get('unknown_refs'): err('MISSING_COVERAGE',p+' 有效要求既没有业务机制去向也没有未决去向')
            for ref in refs:
                if ref not in all_refs:err('BAD_TARGET',p+' 指向不存在的模型机制 '+str(ref))
        elif s in ('excluded','superseded'):
            retired.append(c)
            if c.get('model_refs'):err('RETIRED_ACTIVE_REF',p+' 已排除/被替代要求仍指向当前有效机制')
            if filled(c.get('current_expected')):err('RETIRED_ACTIVE_OUTCOME',p+' 已排除/被替代要求仍写当前正确结果')
            if not (filled(c.get('authority')) and filled(c.get('authority_location'))):err('NO_DECISION_EVIDENCE',p+' 缺取消/替代的有效裁定来源')
        elif s=='unresolved':
            unresolved.append(c)
            if filled(c.get('current_expected')):err('UNRESOLVED_AS_CERTAIN',p+' 未定业务规则却被写为确定结果')
            if not c.get('unknown_refs'):err('NO_UNKNOWN_LINK',p+' 未定规则没有疑问去向')
        elif s=='dependency' and not (c.get('model_refs') or c.get('unknown_refs')):
            flag('DEPENDENCY_UNFOLLOWED',p+' 外部依赖没有消费位置或限制')
        for ref in c.get('unknown_refs', []):
            if ref not in unknown_refs:err('BAD_UNKNOWN',p+' 不存在的待确认编号 '+str(ref))
    paths = ledger.get('critical_paths',[])
    if not paths:flag('NO_PATHS','没有逐步业务链路的成功/失败/交叉变化跟踪')
    for j,p in enumerate(paths):
        loc=f'critical_paths[{j}]'
        if not filled(p.get('task')):err('PATH_TASK',loc+' 没有实际用户任务')
        steps=p.get('steps',[])
        if not steps:err('PATH_EMPTY',loc+' 只有流程名称，未逐步推演')
        for i,step in enumerate(steps):
            sp=f'{loc}.steps[{i}]'
            if step.get('event_ref') not in all_refs:err('PATH_EVENT',sp+' 未定位实际业务事件')
            if not filled(step.get('when')):err('PATH_WHEN',sp+' 缺条件/状态')
            if not (filled(step.get('then')) or step.get('unknown_refs')):err('PATH_THEN',sp+' 缺条件导致的结果或待确认')
            if not filled(step.get('must_hold')):flag('PATH_HOLD',sp+' 没有说明影响或应保持的事实')
        if p.get('high_risk'):
            if not p.get('interruptions'):err('NO_INTERRUPTION',loc+' 高风险长链未推演失败/停止/恢复的最终结果')
            if not p.get('interleavings'):flag('NO_INTERLEAVING',loc+' 高风险长链没有并发/上游变化推演或不适用依据')
        if not (filled(p.get('terminal_outcome')) or p.get('unknown_refs')):err('NO_TERMINAL',loc+' 无最终业务结果或未决项')
        for cid in p.get('clause_refs',[]):
            if cid not in cids:err('PATH_CLAUSE',loc+' 引用不存在条款 '+str(cid))
    discriminators=ledger.get('discriminators',[])
    for j,d in enumerate(discriminators):
        loc=f'discriminators[{j}]'
        if not d.get('clause_refs'):err('DISCRIMINATOR_UNGROUNDED',loc+' 没有原始证据/待确认锚点')
        for cid in d.get('clause_refs',[]):
            if cid not in cids:err('DISCRIMINATOR_CLAUSE',loc+' 错误来源子句 '+str(cid))
        if d.get('confidence')=='confirmed':
            if not (filled(d.get('outcome_a')) and filled(d.get('outcome_b'))) or d.get('outcome_a').strip()==d.get('outcome_b').strip():err('NON_DISCRIMINATIVE',loc+' 两种不同条件没有可区分业务结果')
            if not filled(d.get('oracle')):err('NO_PROOF',loc+' 没有可区分表面成功与真实业务成功的依据')
        elif d.get('confidence')=='needs_decision':
            if not d.get('unknown_refs'):err('UNSOURCED_EXAMPLE',loc+' 不能证明的业务正反例未标记待确认')
        else:err('DISCRIMINATOR_CONFIDENCE',loc+' 例子的确定性必须明确')
    # Universal, project-configured regression markers; only inspect *current* claims, never original quote.
    markers=ledger.get('retired_markers',[])
    if retired and not markers and not filled(ledger.get('no_markers_reason')):
        flag('RETIRED_SCAN_NOT_CONFIGURED','存在正式排除/替代的子句，但没有安排旧行为反扫或说明为什么没有可用标记')
    if any(p.get('high_risk') for p in paths) and not discriminators and not filled(ledger.get('no_discriminator_reason')):
        flag('NO_HIGH_RISK_CHALLENGE','已有高风险业务链，但未提供正反业务结果挑战或合理不适用理由')
    positive=[]
    for c in active:positive.append(('有效规则 '+str(c.get('id')), c.get('current_expected','')))
    for p in paths:
        positive.append(('当前链路 '+str(p.get('id')),p.get('terminal_outcome','')))
        for st in p.get('steps',[]): positive.append(('当前步骤 '+str(p.get('id')),st.get('then','')))
        for st in p.get('interruptions',[]):
            if isinstance(st,dict):positive.append(('中断结果 '+str(p.get('id')),st.get('then','')))
    for d in discriminators:
        if d.get('confidence')=='confirmed':positive.extend([('已确认反例 '+str(d.get('id')),d.get('outcome_a','')),('已确认反例 '+str(d.get('id')),d.get('outcome_b',''))])
    if active_rows:
        for j,r in enumerate(active_rows):
            st=str(r.get('coverage_status','')+' '+r.get('scope','')).lower()
            if ('排除' in st or '不属于本期' in st) and not ('本期按有效范围保留' in st or '部分' in st): continue
            for col in ['mechanism_behavior','current_expected','effective_behavior','当前行为','当前业务结果']:
                if r.get(col):positive.append((f'有效来源表第{j+2}行 {r.get("requirement",r.get("id",""))}',r[col]))
    accepted={x.get('key'):x for x in ledger.get('reviewed_flags',[]) if isinstance(x,dict)}
    for m in markers:
        ident=m.get('id'); needle=m.get('text','')
        if not filled(ident) or not filled(needle):err('RETIRE_MARKER','排除标记缺编号/匹配文本');continue
        for origin,value in positive:
            if needle not in str(value):continue
            key=f'{ident}@{origin}'
            if key in accepted and filled(accepted[key].get('evidence')):info.append({'accepted':key,'rationale':accepted[key]['evidence']});continue
            flag('RETIRED_BEHAVIOR_CANDIDATE',key+': 当前业务预期出现了已排除行为标记 '+needle+'；可能是否定表述，必须逐条核查，不可静默通过')
    decisions={}
    for c in cs:
        key=c.get('decision_key')
        if not key:continue
        decision=decisions.setdefault(key,{'active':[],'unresolved':[]})
        if c.get('scope')=='active': decision['active'].append(c.get('id'))
        elif c.get('scope')=='unresolved': decision['unresolved'].append(c.get('id'))
    for k,v in decisions.items():
        if v['active'] and v['unresolved']:flag('CERTAINTY_CONFLICT',str(k)+' 同一业务决策同时被写成确定和待确定，请查证是否为不同子条件')
    # machine flags cannot judge true semantic correctness, even if report ok
    return {'ok':not errors and (not strict or not flags),'errors':errors,'flags':flags,'reviewed_flags':info,'stats':{'clauses':len(cs),'active':len(active),'retired':len(retired),'unresolved':len(unresolved),'critical_paths':len(paths),'discriminators':len(discriminators)}}

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--model',required=True)
    a.add_argument('--ledger',required=True)
    a.add_argument('--active-csv',help='含当前有效机制字段的来源追踪 CSV（可选；若有必须检查）')
    a.add_argument('--strict',action='store_true',help='存在待人工核实疑点即阻断')
    a.add_argument('--out')
    args=a.parse_args()
    rows=None
    if args.active_csv:
        with open(args.active_csv,encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    ret=audit(load_json(args.model),load_json(args.ledger),rows,args.strict)
    content=json.dumps(ret,ensure_ascii=False,indent=2)
    if args.out:Path(args.out).write_text(content+'\n',encoding='utf-8')
    print(content)
    return 0 if ret['ok'] else 1

if __name__=='__main__':sys.exit(main())
