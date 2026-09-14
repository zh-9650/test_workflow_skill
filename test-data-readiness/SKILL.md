---
name: test-data-readiness
description: 只为即将执行的当前 Batch 准备并验证前置数据；禁止重新规划执行方式、Batch、Case 顺序或证据策略。
---
# Test Data Readiness

## 1. 只处理当前 Batch
读取已确认 Execution Plan，明确本 Batch 是否真的需要业务数据。无需数据时必须 `data_required=false + reason`；需要数据时 `objects` 必须非空。

## 2. 合法业务形成路径
业务对象默认走真实 API 或 UI。脚本只是 implementation，不是业务入口；SQL、数据库直写、内部状态设置禁止用于构造业务事实。

## 3. Object Contract
对象至少声明：

`object_type / object_ref / creation / state_applicable / verified / read_back_verified / relations_verified / access_verified / case_ids / cleanup`

有业务状态时 target/current 都必须非空且一致；无业务状态时显式 `state_applicable=false`。`relations_verified=true` 表示本 Batch 依赖的关联关系已经核对。

## 4. Builder
脚本 Builder 必须记录 builder_id、object_type、business_entry、script_ref、verified、验证环境和时间。只有 verified=true 才允许直接复用；否则先最小试建→read-back→状态核对。

## 5. Readiness 只能由程序计算
禁止在 Manifest 顶层手写 `ready=true`。`scripts/data_manifest.py` 校验通过后写入：

```yaml
readiness:
  ready: true
  checked_at: ...
```

可通过 `--finalize` 把计算后的 readiness 写回 Manifest。Runtime 仍会再次校验 Manifest，不直接信任该字段，因此手工伪造 `readiness.ready=true` 也不能绕过。

## 6. 完成标准
对象存在、状态正确、关联正确、当前账号可访问、read-back 已验证、Case 映射明确且有清理策略后才算 Data Ready。详细方法见 `references/data-builder-method.md`。
