#!/usr/bin/env python3
"""Read-only review hints for a business-model.json or a ZIP containing it.
These are review signals, NEVER an objective correctness score.
Python 3.9+, standard library only.
"""
import argparse, collections, json, pathlib, zipfile, hashlib, sys

def get_model(path):
    path=pathlib.Path(path)
    if path.suffix.lower()=='.zip':
        with zipfile.ZipFile(path) as z:
            names=[n for n in z.namelist() if n.endswith('/business-model.json') or n=='business-model.json']
            if len(names)!=1: raise ValueError('Expected exactly one final business-model.json, found '+str(names))
            raw=z.read(names[0]); origin=str(path)+'!/'+names[0]
    else: raw=path.read_bytes(); origin=str(path)
    return json.loads(raw),origin,hashlib.sha256(raw).hexdigest()

def issue(kind,sev,where,desc,evidence,action):
    return dict(kind=kind,severity=sev,location=where,observation=desc,evidence=evidence,next_verification=action)

def evaluate(m):
    issues=[]
    sms=m.get('state_machines',[])
    for sm in sms:
        name=sm.get('state_machine_id','unknown')
        states=[s['state_id'] if isinstance(s,dict) else str(s) for s in sm.get('states',[])]
        transitions=sm.get('transitions',[])
        edges=collections.defaultdict(set)
        for t in transitions:
            a=t.get('from');b=t.get('to')
            if a and b:edges[a].add(b)
            if a not in states or b not in states:
                issues.append(issue('invalid_transition','P1',name,'迁移端点在状态列表中不存在',{'transition':t.get('transition_id'),'from':a,'to':b},'回查状态定义和业务来源'))
        # This is a hint only: some states may be intentional entry-points.
        first=sm.get('initial_state') or (states[0] if states else None)
        seen=set();todo=[first] if first else []
        while todo:
            s=todo.pop()
            if s in seen:continue
            seen.add(s);todo.extend(edges.get(s,()))
        unreachable=sorted(set(states)-seen)
        if unreachable:
            issues.append(issue('unreachable_states','REVIEW',name,'从声明/默认初态沿既有迁移不可到达的状态',{'assumed_initial':first,'states':unreachable},'核对是否缺迁移、并行维度或存在多个合法初态；不要自动补造迁移'))
        outgoing={t.get('from') for t in transitions}
        incoming={t.get('to') for t in transitions}
        disconnected=sorted(set(states)-incoming-outgoing)
        if disconnected:
            issues.append(issue('unlinked_states','REVIEW',name,'完全没有迁移边相连的状态',{'states':disconnected},'若状态属于本次真实业务，补足其进入/退出依据；否则说明未适用理由'))
    dims=m.get('requirements_completeness_review',{}).get('dimensions',[])
    reasons=collections.defaultdict(list)
    for d in dims:
        r=' '.join(str(d.get('reason','')).split())
        if r:reasons[r].append(d.get('dimension'))
    for reason,names in reasons.items():
        if len(names)>=4:
            issues.append(issue('reused_review_reason','REVIEW','requirements_completeness_review',f'{len(names)}项不同审查维度共用同一理由',{'dimensions':names,'sample_reason':reason[:180]},'对照每个维度所引用的真实业务事实，检查是否只有模板式自评'))
    proofs=collections.defaultdict(list)
    for e in m.get('events',[]):
        ev=e.get('event_id','unknown')
        p=e.get('proof_boundary',{})
        for statement in p.get('insufficient_evidence',[]):
            txt=' '.join(statement.split())
            if txt:proofs[txt].append(ev)
        for key in ('state','relationship'):
            links=e.get('mechanism_links',{}).get(key,{})
            if links.get('impact')=='not_applicable' and not str(links.get('rationale','')).strip():
                issues.append(issue('unexplained_na','P1',ev,f'{key}声明不适用但无理由',{},'说明不涉及的业务依据；不能用空值表示已检查'))
    for txt,ids in proofs.items():
        if len(ids)>=4:
            issues.append(issue('reused_proof_boundary','REVIEW','events',f'{len(ids)}个业务事件使用相同的“不足证明成功”说明',{'events':ids,'sample':txt[:150]},'选取高风险事件，指出真正会表面成功但业务失败的可判别事实'))
    # IDs exist? (Only checks navigational closure, not semantic correctness).
    evs={e.get('event_id') for e in m.get('events',[])}
    for f in m.get('cross_module_flows',[]):
        missing=[x for x in f.get('steps',[]) if isinstance(x,str) and x.startswith('EV-') and x not in evs]
        if missing:
            issues.append(issue('missing_flow_event','P1',f.get('flow_id'), '业务流程引用了不存在的事件',{'events':missing},'补齐事件或核对流程序列来源'))
    pending={x.get('unknown_id'):x for x in m.get('unknowns',[]) if x.get('status')=='pending'}
    rules=[x for x in m.get('rules',[]) if x.get('source_status') in ('CONFIRMED','DERIVED')]
    # deliberately never auto-resolve semantic contradictions by keyword resemblance
    return dict(summary={
        'events':len(m.get('events',[])),'state_machines':len(sms),'rules':len(rules),
        'pending_unknowns':len(pending),'flags_by_type':dict(collections.Counter(x['kind'] for x in issues)),
        'warning':'提示项不是业务正确性评分；原始需求是否漏读、规则是否冲突，须按来源人工复核。'},
        flags=issues)

def markdown(result):
    s=result['summary'];out=['# 业务理解模型只读审查线索','',f"事件 {s['events']}；状态机 {s['state_machines']}；未决 {s['pending_unknowns']}。",'',
        '**注意：以下是需核验的风险线索，不是已证实缺陷；不能据此宣布业务理解完整。**','']
    for i,x in enumerate(result['flags'],1):
        out.extend([f"## {i}. [{x['severity']}] {x['kind']} — {x['location']}",x['observation'],'',
          f"证据：`{json.dumps(x['evidence'],ensure_ascii=False)}`",'',f"需要查证：{x['next_verification']}",''])
    return '\n'.join(out)

def main():
    a=argparse.ArgumentParser();a.add_argument('model');a.add_argument('--json-out');a.add_argument('--md-out');opts=a.parse_args()
    m,origin,sha=get_model(opts.model);r=evaluate(m);r['input']={'location':origin,'sha256':sha,'schema_version':m.get('schema_version'),'model_version':m.get('model_version')}
    if opts.json_out:pathlib.Path(opts.json_out).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8')
    if opts.md_out:pathlib.Path(opts.md_out).write_text(markdown(r),encoding='utf8')
    print(json.dumps({'input':origin,'sha256':sha,'summary':r['summary']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
