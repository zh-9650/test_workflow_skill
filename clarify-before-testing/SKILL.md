---
name: clarify-before-testing
description: 测试流程总路由。负责识别当前 Run/阶段、加载对应 Skill、保存轻量状态和真正需要人工确认的决策；不做业务分析，不依赖 Hook/Lease/Heartbeat。
---
# Clarify Before Testing

## 核心原则
- 当前对话与当前项目资料优先，禁止把其他项目规则带入。
- 资料无法确认的业务规则必须显式列为待确认，不能猜。
- Router 只路由和记状态，不替代业务理解、测试设计、执行规划或执行。
- 不使用 PreToolUse/Stop Hook、Lease、Heartbeat、复杂 Resume Pack 或步骤级 checkpoint。
- 正式产物先由 AI 自审并修订，再进入人工确认。

## 标准阶段
1. `business-modeling`：业务理解。
2. `case-design`：测试点与测试用例设计。
3. `execution-planning`：决定怎么跑。
4. `data-readiness`：准备当前 Batch 数据。
5. `execution-runtime`：按 Batch 正式执行。
6. `defect-handling`：确认缺陷、提单与回归；无缺陷时可跳过。
7. `result-review`：最终对账与测试结论。

## 三个人工确认点
前半程固定存在：
- 等待业务理解确认
- 等待测试点确认
- 等待测试用例确认

后半程固定存在：
- 等待执行方案确认

每个确认点都必须绑定到 Run 内真实文件。生成并自审后，用
`workflow_state.py record-artifact` 登记文件摘要；用户确认后再把该登记标为
`confirmed`。不能只调用 `set-flag` 伪造阶段完成。

关键业务口径仍未确认时，只阻塞受影响范围，不把未知规则伪装成基线。

## 路由规则
- 初次进入：建立 `work/test-runs/RUN-xxx/`，初始化 `internal/state/run-status.json`。
- 已有 Run：从状态文件恢复到 Batch/Case 边界；执行中断从当前 Case 开头重跑。
- 用户修改已确认内容：返回最早受影响阶段，并标记下游产物需重新自审。
- 用户只补充不会改变既有结论的信息：增量更新，不机械推翻整个 Run。
- 每次只加载当前阶段真正需要的 Skill 和资料。

登记的正式产物类型固定为：`business_understanding`、`test_points`、
`test_cases`、`execution_plan`。登记后文件发生变化，下一次转阶段会被拒绝，
并且下游确认自动失效，要求重新自审和确认。

## Run 目录
```text
RUN-xxx/
├─ deliverables/
├─ dashboard/
├─ internal/
│  ├─ business/
│  ├─ design/
│  ├─ execution/
│  ├─ data/
│  ├─ defects/
│  └─ state/run-status.json
├─ scripts/{data,ui,api,temp}/
├─ evidence/
├─ logs/
├─ downloads/
└─ scratch/
```
根目录禁止散落临时 `.py/.js/.json/.txt/.png/.md`。正式给人看的内容进 `deliverables/`；机器追踪内容进 `internal/`。

## 阶段结束
- 更新 `run-status.json` 的 `current_stage/current_batch/current_case/next_action`。
- 只在 Batch/Case/缺陷/人工确认等关键事件更新状态。
- 运行 workspace validator，清理缓存与无价值临时文件。
- 不允许通过删除有效失败测试掩盖问题。

最终复核必须先用 `test-result-review` 生成并校验结果文件，再使用
`record-final-review` 登记该校验结果，最后才允许转入 `closed`。
