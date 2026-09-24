---
name: test-data-readiness
description: Prepare and verify prerequisite data for the single Batch that is about to execute. 仅在执行方案已确认、Router 指定当前 Batch 后使用。根据计划中的数据需求，用合法业务路径准备本 Batch 数据；API 优先、UI 兜底，不使用 SQL 直接造业务数据；创建后必须 read-back 并验证状态、关系和账号可访问性。不要重新分 Batch、选择 UI/API 或修改 Case。
---

# Test Data Readiness｜当前 Batch 数据准备

职责只有一个：

> **把即将执行的当前 Batch 所需前置数据准备好并验证。**

不负责：

- 决定 UI/API/人工；
- 分 Batch；
- Case 顺序；
- Evidence；
- 重新规划执行；
- 修改 Case/Expected。

---

# 1. 数据三类

## 环境信息

URL、账号、权限、服务可用性。

## 可复用基础资源

可以长期稳定复用：

- 测试账号；
- 角色；
- 租户；
- 部门；
- 基础权限；
- 稳定系统配置。

## 业务测试对象

原则上本 Run/Batch 新建：

- 项目；
- 订单；
- 文档；
- 任务；
- 本次真正验证的业务对象。

避免复用历史脏业务数据。

---

# 2. 先明确目标状态和合法形成路径

例如 Case 需要：

```text
对象：项目
目标状态：已审核
关联：创建人/组织/审核人
合法路径：创建 → 提交 → 审核
```

禁止为了方便调用内部状态接口直接把状态改成“已审核”。

前置数据也必须由合法业务动作形成。

---

# 3. API 优先，但先搞清真实调用

写建数脚本前优先查：

1. 前端真实 API 调用；
2. 当前 API 文档；
3. 后端 Controller / DTO / Validator；
4. 已有脚本；
5. 必要时 UI Network。

确认：

- URL；
- Method；
- Header；
- Body；
- 鉴权；
- 前置；
- 成功返回。

然后再写脚本。

不要一边猜参数一边堆临时脚本。

---

# 4. 第一次只做最小试建

```text
创建 1 条
↓
拿到业务 ID
↓
Read-back
↓
确认状态
↓
确认关系
↓
确认当前账号能访问
↓
必要时 UI 可见性确认
```

成功后再批量复用。

HTTP 200 不代表数据准备完成。

---

# 5. API 不适合时转 UI

API 失败先分类。

### 调用方式错误

400/401/403/404、Header、Content-Type、参数结构。

Agent 自己查资料修。

### 业务理解错误

缺前置状态、缺关联、流程理解错。

重新理解合法形成路径。

### API 本身不适合

- 没有公开适用接口；
- 文件流程强依赖前端；
- 前端必须产生关键数据。

转 UI。

### 环境问题

服务不可达、网关、登录服务异常。

不要无限修脚本。

---

# 6. 不使用 SQL 直接造业务数据

数据库仅允许：

- 只读验证；
- 故障分析。

禁止：

```text
UPDATE status='APPROVED'
INSERT 业务对象
```

作为正常测试数据准备。

---

# 7. Builder

跑通后把可复用动作沉淀：

```text
scripts/data/
```

按业务对象和动作组织：

```text
create_project()
submit_project()
approve_project()
upload_document()
```

不要一条 Case 一个 setup 脚本。

只有经过真实创建 + read-back 验证的 Builder 才允许标记可复用。

登记：

```text
internal/data/data-builders.json
```

---

# 8. Batch 内共享，Batch 间默认隔离

同一连续业务链可以共享同一个对象继续推进。

不同 Batch 的业务对象默认隔离，除非 Planning 明确说明共享原因。

---

# 9. 完成标准

数据准备完成必须满足：

```text
对象存在
+
状态正确（如适用）
+
关联关系正确
+
当前账号可访问
+
Case 与对象映射明确
```

输出：

```text
internal/data/manifests/Bxx-data-manifest.json
```

记录：

- 对象类型；
- ID；
- 目标状态；
- 当前状态；
- 创建方式；
- Batch / Case；
- cleanup 策略；
- read-back 结果。

任何 `creation.implementation=script` 的 Builder 必须使用 TypeScript：API Builder 固定 `runner=vitest`，UI Builder 固定 `runner=playwright-test`。Builder 记录 `language`、`runner`、Run 内 `scripts/data/` 下的 `script_ref`、当前文件 `script_sha256`、验证环境/时间，以及验证样本 `verified_case_id`、`verified_object_ref` 和 `read_back_evidence_ref`。对象记录也必须有自己的 `read_back_evidence_ref`，指向 `evidence/<batch>/<case>/` 下的 JSON；除 `batch_id`、`case_id`、`object_ref` 和 `read_back_verified=true` 外，还要绑定原始响应/页面观察文件、正式 runner report、对应 Hash 和 `observed_via`。Contract 会重开所有文件并校验对象关联、脚本 Hash 与 runner report；只填布尔值不能代替 read-back 证据。

详细方法：

`references/data-builder-method.md`

# 10. Data Manifest 与当前 Batch 强绑定

Data Manifest 不能脱离 Execution Plan 单独宣布 ready。

校验时必须同时读取当前 `internal/execution/execution-plan.json`：

```bash
python test-data-readiness/scripts/data_manifest.py \
  --input <run>/internal/data/manifests/B01-data-manifest.json \
  --plan <run>/internal/execution/execution-plan.json \
  --run-dir <run>
```

独立校验成功还不等于 Runtime 已获准使用。必须由 Router 在 `data-readiness` 阶段把当前文件和当前已确认 Execution Plan 的摘要绑定到 Run：

```bash
python clarify-before-testing/scripts/workflow_state.py set-batch-data-ready \
  --state <run>/internal/state/run-status.json \
  --batch B01 \
  --manifest <run>/internal/data/manifests/B01-data-manifest.json
```

禁止用 `set-flag current_batch_data_ready=true` 或手改 JSON 绕过校验。每个新 Batch、以及回归后准备恢复 BLOCKED Case 的 Batch，都必须重新执行这一步。

必须保证：

- `batch_id` 在计划中真实存在；
- `case_ids` 只能指向当前 Batch；
- 需要准备数据的 Case 都有对象映射；
- Builder 的 `object_type` 与实际创建对象一致；
- API/UI 创建入口与已经验证的 Builder 一致。
- Builder 语言/runner 符合 API/UI 固定技术栈；脚本位于当前 Run、Hash 与文件一致，read-back Evidence 引用真实原始观察与 runner report，并对应 Batch/Case/对象及脚本 Hash。
