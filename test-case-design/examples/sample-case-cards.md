# 完整用例卡片（与全量表格同源生成）

> 本文件便于逐条审阅；与 full.md 完全来自同一份结构化设计，不是另一套手写用例。

## TC-API-CREATE-VALID｜Create valid item｜Single isolated synthetic request; first invocation follows formal script execution.

**优先级：** P1　**来源TP：** TP-CREATE-VALID　**业务分支：** BR-SYN-1
**设计状态：** design_ready

### 前置条件

- Use isolated synthetic local HTTP fixture; no external services.

### 数据准备与就绪核验

- 主体/权限：授权合成测试账户
- 业务对象：业务实体 1
- 初始状态：测试账户拥有 1 权限
- 决定性条件：实体标识 1
- 本例取值：fixture="local-memory-catalog"；shared_item_id="item-phase5-b01"；name="Phase5 Item"
- 准备途径：通过独立合成夹具创建业务实体
- 就绪核验：调用读回接口核对实体1状态
- 隔离/恢复：每个实例使用不同标识，执行后隔离清理

### 执行步骤与预期

| 步骤 | 操作 | 本步预期与判定 |
|---|---|---|
| 1 | 1. POST /api/items with id=item-phase5-b01 and name=Phase5 Item | 1. 201 response contains id=item-phase5-b01 and name=Phase5 Item【依据：合成静态产品约束（演示，不构成真实业务依据）；观察：接口返回业务实体 1 及 id；判定：根据唯一标识与取值规则验收 1】 |

### 恢复与清理

每个实例使用不同标识，执行后隔离清理

---

## TC-API-READ-ISOLATED｜Read isolated control item｜Single isolated synthetic request; first invocation follows formal script execution.

**优先级：** P1　**来源TP：** TP-READ-ISOLATED　**业务分支：** BR-SYN-2
**设计状态：** design_ready

### 前置条件

- Use isolated synthetic local HTTP fixture; no external services.

### 数据准备与就绪核验

- 主体/权限：授权合成测试账户
- 业务对象：业务实体 2
- 初始状态：测试账户拥有 2 权限
- 决定性条件：实体标识 2
- 本例取值：fixture="local-memory-catalog"；preseeded_control_id="control-001"
- 准备途径：通过独立合成夹具创建业务实体
- 就绪核验：调用读回接口核对实体2状态
- 隔离/恢复：每个实例使用不同标识，执行后隔离清理

### 执行步骤与预期

| 步骤 | 操作 | 本步预期与判定 |
|---|---|---|
| 1 | 1. GET /api/items/control-001 (read pre-seeded fixture control; no write) | 1. 200 response contains id=control-001 and the pre-seeded control name; no catalog state changes【依据：合成静态产品约束（演示，不构成真实业务依据）；观察：接口返回业务实体 2 及 id；判定：根据唯一标识与取值规则验收 2】 |

### 恢复与清理

每个实例使用不同标识，执行后隔离清理

---

## TC-API-CREATE-RECOVER｜Read B01 regression-created item after repair｜独立准备 item-phase5-b01 后验证恢复可读；不依赖其他用例 PASS

**优先级：** P1　**来源TP：** TP-CREATE-RECOVER　**业务分支：** BR-SYN-3
**设计状态：** design_ready

### 前置条件

- 在本用例中独立通过已验证的合法夹具创建 item-phase5-b01 并核验已存在；不得依赖其他用例执行。

### 数据准备与就绪核验

- 主体/权限：授权合成测试账户
- 业务对象：业务实体 3
- 初始状态：测试账户拥有 3 权限
- 决定性条件：实体标识 3
- 本例取值：fixture="local-memory-catalog"；shared_item_id="item-phase5-b01"
- 准备途径：本用例独立创建 item-phase5-b01 并确认初始化成功，不依赖任何其他测试用例
- 就绪核验：运行本用例前读回 item-phase5-b01，确认名称 Phase5 Item 与目标业务状态
- 隔离/恢复：每个实例使用不同标识，执行后隔离清理

### 执行步骤与预期

| 步骤 | 操作 | 本步预期与判定 |
|---|---|---|
| 1 | 1. GET /api/items/item-phase5-b01，读取本用例准备的对象并核对身份与名称 | 1. 200 response returns id=item-phase5-b01 and name=Phase5 Item, matching this case’s verified fixture【依据：合成静态产品约束（演示，不构成真实业务依据）；观察：接口返回业务实体 3 及 id；判定：根据唯一标识与取值规则验收 3】 |

### 恢复与清理

每个实例使用不同标识，执行后隔离清理

---
