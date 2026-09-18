# Test Point Design Techniques

本 Reference 说明“怎么做”，`SKILL.md` 说明“什么时候做、输出什么”。

测试点设计主轴是业务执行流，不是测试方法清单。

---

## 1. 业务动作节点分析

对每个有独立业务意义的动作建立节点：

```text
source_context
actor
preconditions
inputs
state_before
business_action
outputs
state_changes
data_changes
destinations
downstream_impacts
invariants
```

### Source Context
回答该节点从哪里来：
- 上一步业务节点；
- 某个页面/入口；
- 某个已有对象；
- 某个外部事件。

### Inputs
输入不仅是表单/接口字段，还包括：
- 当前对象状态；
- 当前登录角色；
- 上游数据；
- 关联对象；
- 系统配置；
- 时间；
- 历史操作；
- 外部依赖结果。

### Outputs
输出不仅是 Toast 或 HTTP Response，还包括：
- 页面结果；
- 业务对象字段；
- 新对象；
- 状态；
- 关联关系；
- 待办/消息；
- 文件；
- 权限；
- 索引/检索结果；
- 下游流程入口。

### Invariant
任何写操作必须主动考虑“什么不应该改变”。

例如停用失败时，不只验证提示，还要验证：
- 原状态不变；
- 绑定关系不变；
- 权限没有被部分撤销；
- 下游数据没有部分写入。

---

## 2. 候选场景展开

不是做全量笛卡尔积，而是找“会改变 Expected 的维度”。

推荐维度：
- input_data；
- state；
- actor_permission；
- relation_dependency；
- config；
- time_history；
- execution_external。

每个候选场景记录：

```yaml
scenario_id:
source_refs: []
variation_dimensions: []
expected_status: known | derived | unknown
expected:
expected_source_refs: []
question_id:
```

只有 expected_status=unknown 时才生成设计问题。

---

## 3. 流程级分析

节点级覆盖之外，对每个 flow_path 分析：
- 数据传递；
- 状态传播；
- 分支；
- 中断；
- 恢复；
- 回退；
- 重试；
- 重复；
- 部分成功；
- 重入；
- 分支切换；
- 上游回改；
- 并发；
- 下游失败；
- 外部依赖异常。

跨模块 flow_path 必须明确标记 scope=cross_module。

---

## 4. Coverage Map

Coverage Type 使用 `references/coverage-types.md` 中的机制类型。

状态：

```text
covered
not_applicable
out_of_scope
pending_confirmation
```

覆盖不是追求数量，而是防止已识别业务事实无理由消失。

---

## 5. 测试设计技术：按需使用

设计技术是工具，不是生成主轴。

### 等价类
适用输入类型、格式、枚举、有效/无效类别。
内部记录：valid_classes / invalid_classes。

### 边界值
适用长度、数量、阈值、时间区间。
内部记录：source_rule / derived_values。

### 判定表
适用多个条件共同决定一个动作是否允许或决定不同输出。
内部记录：conditions / actions / rules。

### 因果图
适用复杂条件依赖、互斥、AND/OR 关系。
内部记录：causes / effects / constraints（如适用）。

### 状态迁移
适用生命周期、状态+动作组合。
内部记录：states / transitions / invalid_transitions。

### 场景法
适用多步骤、长链路、跨模块流程。
内部记录：main_flow / alternative_flows / failure_flows / recovery_flows。

### 组合测试
适用多个输入因素且全组合成本过高。
内部记录：parameters / generated_combinations / mandatory_high_risk_combinations。

### 错误推测
适用历史缺陷、技术实现易错点、经验风险。
内部记录：failure_mechanisms。

### 约束
如果声称使用某种技术，就必须存在相应推导；否则不要记录 method。

---

## 6. 去重规则

只有以下条件同时满足才可合并 Test Point：
- 业务前提等价；
- 核心动作等价；
- Expected 机制等价；
- 状态/数据影响等价；
- 下游影响等价。

不能因为文字相似就合并不同状态、不同角色或不同下游影响的测试点。

---

## 7. 测试点与用例的边界

测试点回答“测什么业务机制”。
用例回答“用什么具体数据、怎么操作、怎么判断”。

例如边界 1~50：

测试点：
> 验证名称长度上下边界、边界内值与越界输入处理。

用例数据再展开：
> 0 / 1 / 2 / 49 / 50 / 51。
