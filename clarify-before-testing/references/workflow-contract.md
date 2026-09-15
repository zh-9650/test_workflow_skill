# Workflow Contract｜测试流程契约

## 1. 目标

状态文件只解决：

- 当前 Run；
- 当前 Stage；
- 当前 Batch / Case；
- 正式产物确认；
- 当前阻塞；
- next_action；
- 最终复核绑定。

不要把整个测试方法塞进状态机。

## 2. 前半程顺序

```text
business-modeling
  产出业务理解
  → self-review passed
  → user confirmed
case-design / test points
  → self-review passed
  → user confirmed
case-design / test cases
  → self-review passed
  → user confirmed
execution-planning
```

不允许绕过任何一个人工确认。

## 3. 后半程批次流转与顺序

```text
execution-planning
→ self-review
→ user confirm
+ 循环执行各 Batch：
   data-readiness (为当前 Batch 准备并验证数据)
   → current Batch data ready (set-batch-data-ready)
   → execution-runtime (执行当前 Batch)
   → Reviewer 审核
   → [存在未处理 FAIL] → defect-handling (提单/关联/修复/回归闭环)
   → [回归解锁 BLOCKED Case] → data-readiness (重新验证该 Batch 数据) → execution-runtime (只恢复被解锁 Case) → Reviewer
   → [存在后续待执行批次] → 正常进入 data-readiness (准备下一 Batch 数据，无需 return_reason)
+ 全部批次与缺陷闭环：
 → result-review
 → validated final review
 → closed
```

## 4. 异常返回上游

只有真实执行/设计异常才能打回上游：

- Case 设计问题 → `case-design`
- 执行方案问题 → `execution-planning`
- 批次执行中数据异常打回重做 → `data-readiness`

必须记录 `return_reason`。

（注：多批次推进中正常进入下一批次的数据准备属于正向批次流转，不属于异常回退，不需要 `return_reason`）。

## 5. 产物与确认绑定

产物自审完成后登记 SHA-256。

用户确认时检查文件摘要未改变。

文件改变以后，旧确认失效；不能只改状态字段继续。

## 6. Final Review

`result-review → closed` 必须绑定真实 Final Review JSON，并重新调用最终复核 Contract。

禁止：

```text
set final_review_status=passed
```

绕过真实复核。

## 7. 状态更新时机

只在关键事件：

- Stage 变化；
- Batch 开始/结束；
- Case 开始/结束/阻塞；
- Reviewer 结果；
- Bug 提交；
- 回归完成；
- 用户暂停。

不要对每次点击、请求或截图更新全局状态。

Stage 只能由 Router transition 更新。Dashboard、Runtime 和 Defect 事件可以更新 Case/Batch/Bug 事实，但不能借事件字段改变 `current_stage`。
