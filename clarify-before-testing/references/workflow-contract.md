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
  产出 business understanding + business-model.json
  → self-review passed
  → user confirmed

case-design / test-point-design
  产出 test-points.md + test-points.json
  → self-review passed
  → user confirmed

case-design / test-case-design
  产出 test-cases.md + test-cases.json
  → self-review passed
  → user confirmed

execution-planning
```

`case-design` 保留为内部 Stage，避免后续执行流程接口变化；测试点和测试用例由两个独立 Skill 完成。

不允许绕过任何一个人工确认。

## 3. 前半程版本依赖

依赖链：

```text
business_model_version
        ↓
test_point_version
        ↓
case_design_version
```

同时绑定真实文件 SHA-256。

规则：

- Business Model 改变：Test Point、Test Case、Execution Plan 确认失效；
- Test Point 改变：Test Case、Execution Plan 确认失效；
- Test Case 改变：Execution Plan 确认失效；
- 不允许只修改版本号继续；
- Contract 必须重新校验上游当前已确认文件。

## 4. 后半程批次流转与顺序

```text
execution-planning
→ self-review
→ user confirm
+ 循环执行各 Batch：
   data-readiness
   → current Batch data ready
   → execution-runtime
   → Reviewer
   → [存在未处理 FAIL] → defect-handling
   → [回归解锁 BLOCKED Case] → data-readiness → execution-runtime
   → [存在后续待执行批次] → data-readiness
+ 全部批次与缺陷闭环：
 → result-review
 → validated final review
 → closed
```

## 5. 异常返回上游

真实设计/执行异常可以打回：

- Business Model 问题 → `business-modeling`
- Test Point / Case 设计问题 → `case-design`
- 执行方案问题 → `execution-planning`
- 当前批次数据异常 → `data-readiness`

纠正性回退必须记录 `return_reason`。

正常 Batch 轮转不算异常回退。

## 6. 产物与确认绑定

产物自审完成后登记：

```text
正式产物 path + sha256
内部 Contract input path + sha256
Contract validation result
```

用户确认时重新检查。

文件改变后旧确认失效。

## 7. Final Review

`result-review → closed` 必须绑定真实 Final Review 产物并通过最终 Contract。

禁止手工把 `final_review_status` 改成 passed 绕过复核。

## 8. 状态更新时机

只在关键事件更新：

- Stage 变化；
- 正式产物登记/确认；
- Batch 开始/结束；
- Case 开始/结束/阻塞；
- Reviewer 结果；
- Bug 提交；
- 回归完成；
- 用户暂停。

不要对每次点击、请求或截图更新全局状态。

Stage 只能由 Router transition 更新。
