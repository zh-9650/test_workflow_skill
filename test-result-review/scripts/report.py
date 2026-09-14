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
    return f'''# 测试报告\n\n## 1. 测试范围\n{v.get('scope','')}\n\n## 2. 执行概况\n{v.get('execution_summary','')}\n\n## 3. 核心业务流程结果\n{v.get('core_flow_results','')}\n\n## 4. 缺陷情况\n{v.get('defects','')}\n\n## 5. 修复与回归情况\n{v.get('regression','')}\n\n## 6. 未完成/受阻范围\n{v.get('blocked','')}\n\n## 7. 主要质量风险\n{v.get('risks','')}\n\n## 8. 最终测试结论\n{conclusion}\n'''
if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--input',required=True); a.add_argument('--output',required=True); x=a.parse_args(); Path(x.output).write_text(render(json.loads(Path(x.input).read_text(encoding='utf-8'))),encoding='utf-8')
