# Data Builder 方法

## 1. Builder 不是“造一条数据库记录”

Builder 应封装合法业务动作。

例如：

```text
create_project
submit_project
approve_project
```

目标是让数据形成路径与真实业务一致。

## 2. 最小探测

新接口/新页面第一次用于造数：

- 只创建一个样本；
- 读取回来；
- 验证状态/关系；
- 必要时 UI 看一眼。

确认之后再沉淀。

## 3. Builder 失败怎么处理

每次重试必须有新的证据或新的假设。

禁止固定“失败就重试 3 次”。

先判断：

- 参数错；
- 鉴权错；
- 业务前置错；
- 环境错；
- API 不适合；
- 真实产品问题。

## 4. 数据不要污染测试目标

数据准备只能完成前置。

如果 Case 的测试目标就是“提交项目”，数据准备不能提前把项目提交掉。

## 5. 业务对象隔离

默认用 Run/Batch 唯一前缀或可追踪标识，避免历史数据混淆。

但不要为了唯一性改变业务含义。

## 6. Builder 可复用记录

只有脚本化 Builder 才登记执行来源。API 造数固定 TypeScript + Vitest + Node 原生 fetch；UI 造数固定 TypeScript + Playwright Test。Manifest 中至少保存：

```json
{
  "builder_id": "create-project-v1",
  "object_type": "project",
  "business_entry": "api",
  "language": "typescript",
  "runner": "vitest",
  "script_ref": "scripts/data/create-project.test.ts",
  "script_sha256": "<当前文件 SHA-256>",
  "verified": true,
  "verified_environment": "isolated-test",
  "verified_at": "<ISO-8601>",
  "verified_case_id": "TC-001",
  "verified_object_ref": "project-123",
  "read_back_evidence_ref": "evidence/B01/TC-001/data-builder-read-back.json"
}
```

当前对象还要在 Manifest 的 object 项中引用自己的 read-back JSON。该 JSON 必须记录 `batch_id`、`case_id`、`object_ref`、`read_back_verified: true`、`observed_via`，并引用原始响应/页面观察文件及其 SHA-256、正式 runner report 及其 SHA-256。原始观察必须含精确 `object_ref`；report 必须含实际 TypeScript 脚本 Hash 和成功退出码。复用脚本的 Builder 还必须与 `script_ref`/`script_sha256` 一致。Contract 会重新读取原始观察、report 和脚本，校验 Batch/Case/对象关联与全部 Hash；只有自报 `read_back_verified=true` 的 JSON 不构成读回证据。

原始业务读回应记录 `object_type` 与非空 `observed_fields`（来自本次正式 API/UI GET 结果），不能只保存 Builder 自己写入的对象 ID。若 Manifest 标注 `state_applicable: true`，Contract 会将原始读回中的 `observed_fields.state`（或 `status`）与 `target_state` 比较；不一致时 Batch 不得 Ready。
