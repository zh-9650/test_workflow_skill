# 冒烟测试用例（每条同样独立完整）

> 这里不是全量用例 ID 引用表。每条冒烟用例重复带有自己的数据前置、步骤、预期和来源，可独立执行。

| 用例ID | 测试步骤（含前置数据准备） | 预期结果 | 提取来源 |
|---|---|---|---|
| TC-API-CREATE-VALID | 【前置】<br>Use isolated synthetic local HTTP fixture; no external services.<br>主体/权限：授权合成测试账户<br>业务对象：业务实体 1<br>初始状态：测试账户拥有 1 权限<br>决定性条件：实体标识 1<br>本例取值：fixture="local-memory-catalog"；shared_item_id="item-phase5-b01"；name="Phase5 Item"<br>准备途径：通过独立合成夹具创建业务实体<br>就绪核验：调用读回接口核对实体1状态<br>隔离/恢复：每个实例使用不同标识，执行后隔离清理<br>【步骤】<br>1. POST /api/items with id=item-phase5-b01 and name=Phase5 Item | 1. 201 response contains id=item-phase5-b01 and name=Phase5 Item【依据：合成静态产品约束（演示，不构成真实业务依据）；观察：接口返回业务实体 1 及 id；判定：根据唯一标识与取值规则验收 1】 | TP-CREATE-VALID / BR-SYN-1 |
| TC-API-READ-ISOLATED | 【前置】<br>Use isolated synthetic local HTTP fixture; no external services.<br>主体/权限：授权合成测试账户<br>业务对象：业务实体 2<br>初始状态：测试账户拥有 2 权限<br>决定性条件：实体标识 2<br>本例取值：fixture="local-memory-catalog"；preseeded_control_id="control-001"<br>准备途径：通过独立合成夹具创建业务实体<br>就绪核验：调用读回接口核对实体2状态<br>隔离/恢复：每个实例使用不同标识，执行后隔离清理<br>【步骤】<br>1. GET /api/items/control-001 (read pre-seeded fixture control; no write) | 1. 200 response contains id=control-001 and the pre-seeded control name; no catalog state changes【依据：合成静态产品约束（演示，不构成真实业务依据）；观察：接口返回业务实体 2 及 id；判定：根据唯一标识与取值规则验收 2】 | TP-READ-ISOLATED / BR-SYN-2 |

## 提测准入说明
冒烟选择应覆盖项目实际存在的关键入口、主链、权限与强阻断；不得机械要求固定比例或编造缺失业务。
