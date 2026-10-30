# 全量测试用例（独立可读正本）

> 每行即一条完整可独立执行和判定的测试用例；无需查找或拼接“主项/实例”。数据只写已确认的准备方式与要求，未验证的环境能力不得伪称可用。

| 用例ID | 用例标题 | 前置条件（含完整数据准备） | 测试步骤 | 预期结果（逐步与最终判定） | 优先级 | 疑问/备注 |
|---|---|---|---|---|---|---|
| TC-API-CREATE-VALID | Create valid item｜Single isolated synthetic request; first invocation follows formal script execution. | Use isolated synthetic local HTTP fixture; no external services.<br>主体/权限：授权合成测试账户<br>业务对象：业务实体 1<br>初始状态：测试账户拥有 1 权限<br>决定性条件：实体标识 1<br>本例取值：fixture="local-memory-catalog"；shared_item_id="item-phase5-b01"；name="Phase5 Item"<br>准备途径：通过独立合成夹具创建业务实体<br>就绪核验：调用读回接口核对实体1状态<br>隔离/恢复：每个实例使用不同标识，执行后隔离清理 | 1. POST /api/items with id=item-phase5-b01 and name=Phase5 Item | 1. 201 response contains id=item-phase5-b01 and name=Phase5 Item【依据：合成静态产品约束（演示，不构成真实业务依据）；观察：接口返回业务实体 1 及 id；判定：根据唯一标识与取值规则验收 1】 | P1 | 来源TP：TP-CREATE-VALID；分支：BR-SYN-1；设计状态：design_ready |
| TC-API-READ-ISOLATED | Read isolated control item｜Single isolated synthetic request; first invocation follows formal script execution. | Use isolated synthetic local HTTP fixture; no external services.<br>主体/权限：授权合成测试账户<br>业务对象：业务实体 2<br>初始状态：测试账户拥有 2 权限<br>决定性条件：实体标识 2<br>本例取值：fixture="local-memory-catalog"；preseeded_control_id="control-001"<br>准备途径：通过独立合成夹具创建业务实体<br>就绪核验：调用读回接口核对实体2状态<br>隔离/恢复：每个实例使用不同标识，执行后隔离清理 | 1. GET /api/items/control-001 (read pre-seeded fixture control; no write) | 1. 200 response contains id=control-001 and the pre-seeded control name; no catalog state changes【依据：合成静态产品约束（演示，不构成真实业务依据）；观察：接口返回业务实体 2 及 id；判定：根据唯一标识与取值规则验收 2】 | P1 | 来源TP：TP-READ-ISOLATED；分支：BR-SYN-2；设计状态：design_ready |
| TC-API-CREATE-RECOVER | Read B01 regression-created item after repair｜独立准备 item-phase5-b01 后验证恢复可读；不依赖其他用例 PASS | 在本用例中独立通过已验证的合法夹具创建 item-phase5-b01 并核验已存在；不得依赖其他用例执行。<br>主体/权限：授权合成测试账户<br>业务对象：业务实体 3<br>初始状态：测试账户拥有 3 权限<br>决定性条件：实体标识 3<br>本例取值：fixture="local-memory-catalog"；shared_item_id="item-phase5-b01"<br>准备途径：本用例独立创建 item-phase5-b01 并确认初始化成功，不依赖任何其他测试用例<br>就绪核验：运行本用例前读回 item-phase5-b01，确认名称 Phase5 Item 与目标业务状态<br>隔离/恢复：每个实例使用不同标识，执行后隔离清理 | 1. GET /api/items/item-phase5-b01，读取本用例准备的对象并核对身份与名称 | 1. 200 response returns id=item-phase5-b01 and name=Phase5 Item, matching this case’s verified fixture【依据：合成静态产品约束（演示，不构成真实业务依据）；观察：接口返回业务实体 3 及 id；判定：根据唯一标识与取值规则验收 3】 | P1 | 来源TP：TP-CREATE-RECOVER；分支：BR-SYN-3；设计状态：design_ready |

## 说明
每条用例的前置数据、准备方式、就绪检查、步骤和断言均已在本行列出。若正式环境缺少可控入口，该用例只能以候选状态交付。
