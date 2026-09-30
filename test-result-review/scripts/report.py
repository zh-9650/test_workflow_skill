from pathlib import Path
import argparse,json
MAP={
 'ready':'测试完成，可进入下一阶段',
 'ready_with_risk':'测试基本完成，但仍有风险',
 'not_recommended':'不建议进入下一阶段',
 'incomplete':'测试未完成，当前无法形成完整质量结论',
}
def render(v):
    assessment=v.get('final_assessment') or {}
    code=assessment.get('conclusion')
    if code not in MAP: raise AssertionError('final_assessment.conclusion: must be generated before report rendering')
    conclusion=MAP[code]
    versions=v.get('version_reconciliation')
    if not isinstance(versions,dict): raise AssertionError('version_reconciliation: validated reconciliation required')
    def safe(value): return str(value).replace('|','\\|').replace('\n',' ')
    lines=[f"初测版本：{safe(versions['initial_deployment_version'])}；最新目标版本：{safe(versions['latest_target_version'])}"]
    lines.extend(['','| Case | 环境 | 实际验证版本 | 沿用旧版本的依据 |','| --- | --- | --- | --- |'])
    for row in versions['case_versions']:
        lines.append('| '+ ' | '.join(safe(x) for x in (row['case_id'],row['target_environment'],row['verified_version'],'；'.join(row['not_retested_rationale'])))+' |')
    for index,event in enumerate(versions['deployment_events'],1):
        lines.append(f"\n部署轮次 {index}：{safe(event['deployment_version'])}；证据 `{safe(event['evidence_ref'])}`；影响评估：{safe(event['impact_decision']['rationale'])}")
    for row in versions.get('execution_rounds',[]):
        lines.append(f"\n{safe(row['case_id'])} / {safe(row['phase'])}：{safe(row['status'])}，版本 {safe(row['deployment_version'])}，证据 `{safe(row['results_ref'])}`")
    version_text='\n'.join(lines)
    blocked='、'.join(versions['unexecuted_scope']) or '无'
    return f'''# 测试报告\n\n## 1. 测试范围\n{v.get('scope','')}\n\n## 2. 执行概况\n{v.get('execution_summary','')}\n\n## 3. 核心业务流程结果\n{v.get('core_flow_results','')}\n\n## 4. 缺陷情况\n{v.get('defects','')}\n\n## 5. 修复与回归情况\n{version_text}\n{v.get('regression','')}\n\n## 6. 未完成/受阻范围\n未执行完成的 Case：{blocked}\n{v.get('blocked','')}\n\n## 7. 主要质量风险\n{v.get('risks','')}\n\n## 8. 最终测试结论\n{conclusion}\n'''
if __name__=='__main__':
    from final_review import validate
    a=argparse.ArgumentParser(); a.add_argument('--input',required=True); a.add_argument('--output',required=True); a.add_argument('--run-dir',required=True); x=a.parse_args()
    run=Path(x.run_dir).resolve(); output=Path(x.output).resolve()
    if not output.is_relative_to(run/'deliverables'): raise AssertionError('output must stay inside Run deliverables')
    if json.loads((run/'internal/state/run-status.json').read_text(encoding='utf-8')).get('current_stage')=='closed': raise AssertionError('closed Run is immutable')
    data=json.loads(Path(x.input).read_text(encoding='utf-8')); validate(data,run)
    output.parent.mkdir(parents=True,exist_ok=True); output.write_text(render(data),encoding='utf-8')
