#!/usr/bin/env python3
"""Project the legacy case-template/instance representation into standalone TEST CASES.

The unit delivered to a tester is ONE complete case per independently judgeable
scenario, not a template or an instance to be manually joined.  No product
business expectations are invented here: expectations are sourced only from
existing assertions and the case_quality_design oracle/data contracts.
"""
import argparse
import json
import re
from pathlib import Path

PLACEHOLDER = ('准备相关数据', '准备合法数据', '准备测试数据', '执行相关操作', '结果正确',
               '符合预期', '正常显示', '操作成功', '按实际情况', '查看相关日志', '自行准备',
               '待补充', 'TODO', 'TBD', '检查正常')
READY = 'design_ready'

class DeliveryError(ValueError):
    pass

def require(v, path):
    if not isinstance(v,str) or not v.strip():
        raise DeliveryError(f'{path}: 必须写清具体内容')
    if any(p.casefold() == v.strip().casefold() for p in PLACEHOLDER):
        raise DeliveryError(f'{path}: 空泛占位不能当独立用例')
    return v.strip()

def items(v,path,mandatory=True):
    if not isinstance(v,list) or (mandatory and not v):
        raise DeliveryError(f'{path}: 需要非空列表')
    return v

def words(v,path):
    if isinstance(v,str):return [require(v,path)]
    return [require(x,f'{path}[{i}]') for i,x in enumerate(items(v,path))]

def unique_by(lst,key,path):
    out={}
    for i,x in enumerate(items(lst,path)):
        if not isinstance(x,dict):raise DeliveryError(f'{path}[{i}]: 对象缺失')
        k=require(x.get(key),f'{path}[{i}].{key}')
        if k in out:raise DeliveryError(f'{path}: 重复 {key}={k}')
        out[k]=x
    return out

def render_data(v):
    if not isinstance(v,dict):raise DeliveryError('execution_instances.test_data: 对象缺失')
    if not v:raise DeliveryError('execution_instances.test_data: 不能空')
    return [f'{k}={json.dumps(x,ensure_ascii=False)}' for k,x in v.items()]

def make_cases(source,*, candidate=False):
    tpls=unique_by(source.get('case_templates'), 'case_id','case_templates')
    executions=unique_by(source.get('execution_instances'),'instance_id','execution_instances')
    q=source.get('case_quality_design') or {}
    rd=unique_by(q.get('instance_readiness'), 'instance_id','case_quality_design.instance_readiness')
    if set(executions)!=set(rd):
        raise DeliveryError(f'instance_readiness 与执行场景不一致，缺少={sorted(set(executions)-set(rd))} 多余={sorted(set(rd)-set(executions))}')
    mapping=q.get('branch_instances',[])
    branch_ids={iid:[] for iid in executions}
    for row in mapping:
        for iid in row.get('instance_ids',[]):
            if iid in branch_ids and row.get('status')=='covered':branch_ids[iid].append(row['branch_id'])
    out=[];used_ids=set()
    for iid,inst in executions.items():
        cid=require(inst.get('case_id'),f'instance[{iid}].case_id')
        if cid not in tpls:raise DeliveryError(f'instance[{iid}]: 用例骨架不存在')
        tpl=tpls[cid];qrow=rd[iid]
        case_id=iid[2:] if iid.startswith('I-') else iid
        if case_id in used_ids:raise DeliveryError(f'用例ID重复: {case_id}')
        used_ids.add(case_id)
        status=qrow.get('design_status')
        if status!=READY and not candidate:
            raise DeliveryError(f'{iid}: {status} 尚不可正式交付；允许候选但不可标记设计就绪')
        preconditions=words(tpl.get('preconditions'),f'{iid}.preconditions') if tpl.get('preconditions_applicable') else ['本场景无需额外前置条件（用例中数据准备仍须完成）']
        dc=qrow.get('data_contract')
        if not isinstance(dc,dict):raise DeliveryError(f'{iid}.data_contract 缺失')
        data={k:words(dc.get(k),f'{iid}.data_contract.{k}') for k in ('actors','objects','initial_facts','decisive_values')}
        for k in ('setup_approach','readiness_check','isolation_cleanup'):
            data[k]=require(dc.get(k),f'{iid}.data_contract.{k}')
        variant=require(inst.get('variation'),f'{iid}.variation')
        values=render_data(inst.get('test_data'))
        # A final test case must be preparable from its own prerequisites, never
        # depend on a different test having executed/PASSed before it.
        if 'created_by_case_id' in (inst.get('test_data') or {}):
            raise DeliveryError(f'{iid}: 依赖其它测试用例造数；改成当前用例内独立准备并核验')
        if any(re.search(r'(另一条|前一条|其他|another|previous|prior).*?(用例|case|test).*?(通过|pass|执行|run)', x, flags=re.I) for x in preconditions if not ('不依赖' in x or '不得依赖' in x)):
            raise DeliveryError(f'{iid}: 前置条件依赖其他用例的执行结果，不是独立用例')
        aids=items(inst.get('expected_assertion_ids'),f'{iid}.expected_assertion_ids')
        if len(aids)!=len(set(aids)):raise DeliveryError(f'{iid}: 重复断言引用')
        ass=unique_by(tpl.get('assertions'),'assertion_id',f'{cid}.assertions')
        if not set(aids)<=set(ass):raise DeliveryError(f'{iid}: 无效断言引用')
        ora=unique_by(qrow.get('oracle_contracts'),'assertion_id',f'{iid}.oracle_contracts')
        if not set(aids)<=set(ora):raise DeliveryError(f'{iid}: 某个断言没有判定依据')
        steps=items(tpl.get('steps'),f'{cid}.steps')
        step_ids=[require(s.get('step_id'),f'{cid}.steps[].step_id') for s in steps]
        if len(step_ids)!=len(set(step_ids)):raise DeliveryError(f'{cid}.steps: 重复标识')
        assertions=[];obs_by_step={s:[] for s in step_ids};final=[]
        for aid in aids:
            a=ass[aid];o=ora[aid]
            if o.get('oracle_type')=='pending_oracle' and not candidate:
                raise DeliveryError(f'{iid}/{aid}: 判定标准缺失，不能正式交付')
            for k in ('basis','observed_fact','decision_rule','evidence_collection'):
                require(o.get(k),f'{iid}.oracle[{aid}].{k}')
            expected=require(a.get('expected'),f'{iid}.assertion[{aid}].expected')
            assertion={'id':aid,'checkpoint':a.get('checkpoint'),'expected':expected,'oracle_type':o.get('oracle_type'),
                       'basis':o['basis'],'observed_fact':o['observed_fact'],'decision_rule':o['decision_rule'],
                       'evidence_collection':o['evidence_collection'],'tp_ids':a.get('test_point_ids',[])}
            if a.get('checkpoint') in ('step','intermediate'):
                sid=a.get('step_id')
                if sid not in obs_by_step:raise DeliveryError(f'{iid}/{aid}: 步骤标识不存在')
                obs_by_step[sid].append(assertion)
            elif a.get('checkpoint')=='final':final.append(assertion)
            else:raise DeliveryError(f'{iid}/{aid}: 无效检查点')
            assertions.append(assertion)
        rendered_steps=[]
        for si,s in enumerate(steps):
            sid=s['step_id'];action=require(s.get('action'),f'{iid}.steps[{sid}].action')
            check=obs_by_step[sid][:]
            # For a one-step case, the final business assertion is also the
            # observable result of that step. It is NOT an additional fake step.
            if len(steps)==1:check+=final
            rendered_steps.append({'id':sid,'action':action,'checks':check})
        if len(steps)>1 and not any(obs_by_step.values()):
            raise DeliveryError(f'{iid}: 多步骤全是动作而没有中间检查点，请给关键步骤增加有来源的预期')
        if not any(st['checks'] for st in rendered_steps):raise DeliveryError(f'{iid}: 缺少逐步可观察预期')
        tp_ids=inst.get('test_point_ids') or tpl.get('test_point_ids') or []
        if not tp_ids:raise DeliveryError(f'{iid}: 缺少来源 TP')
        out.append({'case_id':case_id,
           'title':require(tpl.get('title'),f'{iid}.title')+'｜'+variant,
           'priority':tpl.get('priority'),'case_type':tpl.get('case_type'),
           'tp_ids':tp_ids,'branch_ids':sorted(set(branch_ids[iid])),
           'preconditions':preconditions,'data':data,'data_values':values,'steps':rendered_steps,
           'final_assertions':final,'assertions':assertions,
           'cleanup':data['isolation_cleanup'],'design_status':status,
           'dependency':qrow.get('dependency','')})
    return out

def plain(v):return str(v).replace('|','\\|').replace('\n','；').replace('\r','')
def multi(xs):return '<br>'.join(plain(x) for x in xs)
def prep_lines(c):
    d=c['data'];return ['主体/权限：'+ '；'.join(d['actors']), '业务对象：'+ '；'.join(d['objects']),
        '初始状态：'+ '；'.join(d['initial_facts']), '决定性条件：'+ '；'.join(d['decisive_values']),
        '本例取值：'+ '；'.join(c['data_values']), '准备途径：'+d['setup_approach'],
        '就绪核验：'+d['readiness_check'], '隔离/恢复：'+d['isolation_cleanup']]

def step_lines(c):
    result=[]
    for n,s in enumerate(c['steps'],1):result.append(f'{n}. {s["action"]}')
    if len(c['steps'])>1 and c['final_assertions']:
        result.append(f'{len(c["steps"])+1}. 根据独立证据完成最终核对：'+ '；'.join(a['evidence_collection'] for a in c['final_assertions']))
    return result

def expected_lines(c):
    result=[]
    for n,s in enumerate(c['steps'],1):
        if s['checks']:
            result.append(f'{n}. '+ '；'.join(a['expected']+'【依据：'+a['basis']+'；观察：'+a['observed_fact']+'；判定：'+a['decision_rule']+'】' for a in s['checks']))
        else:result.append(f'{n}. 此步为前置动作；不得在此提前宣称最终成功，后续按断言核实')
    if len(c['steps'])>1 and c['final_assertions']:
        result.append(f'{len(c["steps"])+1}. '+ '；'.join(a['expected']+'【依据：'+a['basis']+'；观察：'+a['observed_fact']+'；判定：'+a['decision_rule']+'】' for a in c['final_assertions']))
    return result

def full_md(cases):
    lines=['# 全量测试用例（独立可读正本）','',
           '> 每行即一条完整可独立执行和判定的测试用例；无需查找或拼接“主项/实例”。数据只写已确认的准备方式与要求，未验证的环境能力不得伪称可用。','',
           '| 用例ID | 用例标题 | 前置条件（含完整数据准备） | 测试步骤 | 预期结果（逐步与最终判定） | 优先级 | 疑问/备注 |',
           '|---|---|---|---|---|---|---|']
    for c in cases:
        pre=multi(c['preconditions']+prep_lines(c))
        remark=f'来源TP：{",".join(c["tp_ids"])}；分支：{",".join(c["branch_ids"])}；设计状态：{c["design_status"]}'
        if c['dependency']:remark+='；执行依赖：'+c['dependency']
        lines.append('| '+' | '.join([plain(c['case_id']),plain(c['title']),pre,multi(step_lines(c)),multi(expected_lines(c)),plain(c['priority']),plain(remark)])+' |')
    lines+=['','## 说明','每条用例的前置数据、准备方式、就绪检查、步骤和断言均已在本行列出。若正式环境缺少可控入口，该用例只能以候选状态交付。','']
    return '\n'.join(lines)

def cards_md(cases):
    lines=['# 完整用例卡片（与全量表格同源生成）','',
           '> 本文件便于逐条审阅；与 full.md 完全来自同一份结构化设计，不是另一套手写用例。','']
    for c in cases:
        lines += [f'## {c["case_id"]}｜{c["title"]}','',
                  f'**优先级：** {c["priority"]}　**来源TP：** {", ".join(c["tp_ids"])}　**业务分支：** {", ".join(c["branch_ids"])}',
                  f'**设计状态：** {c["design_status"]}'+(f'（依赖：{c["dependency"]}）' if c['dependency'] else ''),'',
                  '### 前置条件','']
        lines += ['- '+x for x in c['preconditions']]
        lines += ['','### 数据准备与就绪核验','']
        lines += ['- '+x for x in prep_lines(c)]
        lines+=['','### 执行步骤与预期','', '| 步骤 | 操作 | 本步预期与判定 |','|---|---|---|']
        actions=step_lines(c);expecteds=expected_lines(c)
        for i,(a,e) in enumerate(zip(actions,expecteds),1):lines.append(f'| {i} | {plain(a)} | {plain(e)} |')
        lines+=['','### 恢复与清理','',c['cleanup'],'','---','']
    return '\n'.join(lines)

def smoke_md(cases, ids):
    byid={c['case_id']:c for c in cases}
    if len(ids)!=len(set(ids)) or set(ids)-set(byid):
        raise DeliveryError('smoke IDs 存在重复或不存在于全量用例')
    lines=['# 冒烟测试用例（每条同样独立完整）','',
           '> 这里不是全量用例 ID 引用表。每条冒烟用例重复带有自己的数据前置、步骤、预期和来源，可独立执行。','',
           '| 用例ID | 测试步骤（含前置数据准备） | 预期结果 | 提取来源 |','|---|---|---|---|']
    for id in ids:
        c=byid[id]
        lines.append('| '+' | '.join([plain(id),multi(['【前置】']+c['preconditions']+prep_lines(c)+['【步骤】']+step_lines(c)),multi(expected_lines(c)),plain(','.join(c['tp_ids'])+' / '+','.join(c['branch_ids']))])+' |')
    lines+=['','## 提测准入说明','冒烟选择应覆盖项目实际存在的关键入口、主链、权限与强阻断；不得机械要求固定比例或编造缺失业务。','']
    return '\n'.join(lines)

def materialize(source,smoke_ids,*,candidate=False):
    cases=make_cases(source,candidate=candidate)
    if not smoke_ids and not candidate:raise DeliveryError('正式交付必须选择至少一条冒烟用例（若项目确实不需要，应人工明确豁免）')
    standalone_json=json.dumps({'schema_version':'1.2.0', 'source_case_design_version':source.get('case_design_version'), 'cases':cases},ensure_ascii=False,indent=2)+'\n'
    return cases,full_md(cases),cards_md(cases),smoke_md(cases,smoke_ids),standalone_json

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True);p.add_argument('--full',required=True);p.add_argument('--cards',required=True)
    p.add_argument('--smoke',required=True);p.add_argument('--smoke-ids',required=True,help='JSON array of standalone case IDs')
    p.add_argument('--standalone-json',required=True,help='交付下游完整独立用例的机器正本')
    p.add_argument('--candidate',action='store_true');p.add_argument('--verify',action='store_true',help='check exact bytes; do not write')
    a=p.parse_args();source=json.loads(Path(a.input).read_text(encoding='utf-8'))
    ids=json.loads(Path(a.smoke_ids).read_text(encoding='utf-8'))
    if not isinstance(ids,list):raise SystemExit('smoke IDs must be JSON list')
    cases,full,cards,smoke,standalone_json=materialize(source,ids,candidate=a.candidate)
    for path,data in ((a.full,full),(a.cards,cards),(a.smoke,smoke),(a.standalone_json,standalone_json)):
        dest=Path(path)
        if a.verify:
            if not dest.exists() or dest.read_text(encoding='utf-8')!=data:
                raise SystemExit(f'REJECT: 文档与完整用例设计不同步 {path}')
        else:
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(data,encoding='utf-8')
    print(json.dumps({'ok':True,'case_count':len(cases),'smoke_count':len(ids),'verified':a.verify},ensure_ascii=False))

if __name__=='__main__':main()
