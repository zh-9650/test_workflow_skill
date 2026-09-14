# 测试设计方法

测试点不是先生成再贴标签。选择方法后必须保留对应推导结构，Contract 会检查“方法确实被使用”。
测试点与测试用例是两个确认阶段：测试点 Contract 使用 `mode=test-points`，测试用例确认后才使用 `mode=test-cases` 或 `mode=full`。测试点必须有可读描述，不能只留下稳定 ID 和方法名。

## 等价类
记录有效类、无效类及其依据，再生成测试点。

## 边界值
记录 source rule（如 min/max）和 derived values，至少覆盖边界、边界内邻值和边界外邻值。

## 判定表
记录 conditions、actions、rules；不能只有 `method=判定表`。

## 因果图
记录 causes、constraints（如适用）、effects，复杂关系可再转判定表。

## 状态迁移
记录 states、合法 transitions、invalid_transitions、失败/恢复路径。

## 场景法 / 业务流程法
记录 main_flow、alternative_flows、failure_flows。长链路必须主动考虑中断、回退、重试、跨模块数据衔接以及多个分支叠加后的异常流。

## 组合测试
记录 parameters 和 generated_combinations，同时保留明确高风险组合，不用 Pairwise 覆盖掉业务强组合。

## 错误推测
记录可复用 failure_mechanisms，不直接照搬旧项目 Bug。

方法推导后再从权限、数据一致性、上下游影响、多入口一致性、并发、幂等、异步、时间、外部依赖等风险视角查漏补缺。
