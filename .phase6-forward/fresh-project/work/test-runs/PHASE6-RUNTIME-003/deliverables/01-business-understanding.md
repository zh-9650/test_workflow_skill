# PHASE6-RUNTIME-003 — Item Lookup Fixture 业务理解

> **范围声明：**本文仅记录 Phase 6 隔离 smoke fixture 的测试基线（fixture/test baseline），不是对真实产品或真实业务项目的业务确认。文中期望来自冻结的 `PHASE6-CLAUDE-001` 验收任务；历史运行记录仅用于说明此前观察，不代表本次 Run 的当前环境已就绪。

## 1. 本次理解范围

本 Run 只覆盖本地隔离 fixture 的只读 Item Lookup 展示：

- API 观察：`GET /api/items/1` 应返回 HTTP 200，JSON 精确为 `{ "id": "1", "name": "Smoke item", "status": "ready" }`，其中 `id` 是字符串。
- UI 观察：点击 `Load item` 后，页面可见的 `#result` 应精确显示 `Smoke item — ready`。
- Critical UI 观察：点击前 `Item lookup` 标题可见；点击后同样显示 `Smoke item — ready`，并按验收任务要求保留视频证据。

这些是隔离 fixture 的测试基线，不等同于已确认的产品需求。Critical UI Case 不主张数据在刷新或后续会话中仍然存在。

## 2. 模块、对象与行为

| 项目 | 本 fixture 基线 |
| --- | --- |
| 模块 | Fixture Item Lookup：提供 API 查询和 UI 加载/展示两种观察入口 |
| 对象 | Fixture Item，以字符串标识 `1` 指向；基线字段为 `id`、`name`、`status` |
| API 行为 | 发起只读 GET 请求并比较状态码及精确 JSON |
| UI 行为 | 点击 `Load item` 并比较页面可见结果；Critical Case 还检查标题并录制视频 |
| 写入及关系变化 | 本次基线没有创建、更新、删除或关系维护行为 |

API 和 UI 是该 smoke 的两个观察路径，不表示实际业务流程中存在跨模块先后依赖。模型未声明业务状态机、状态迁移、关系、业务不变量或跨模块流程。

## 3. 失败边界

如果 fixture 不可达、HTTP 状态或响应与基线不符、页面控件缺失或显示结果不符，应记录实际观察并按正式 Runtime/Reviewer 流程分类。单凭这些基线不能把环境或脚本问题判定为真实产品缺陷，也不能推断真实系统最终业务状态。

## 4. 明确不在范围内的内容

本模型不定义或确认：

- 真实业务中 Item 的含义、生命周期、状态迁移、创建/编辑/删除规则；
- 生产数据、数据持久化、刷新后状态或历史记录；
- 用户身份、角色权限、租户/数据访问范围；
- 并发、重试、幂等、恢复、唯一性策略；
- 下游系统、跨模块影响或真实业务失败后的最终事实。

这些问题不能从孤立 smoke fixture 的验收任务和历史观察推出。它们作为真实业务范围的未决边界保留；本文件不替用户或业务负责人作答。

## 5. 来源与确认状态

机器可读模型见 `internal/business/business-model.json`，结构与来源审阅见 `internal/business/business-model-review.md`。所用来源被标记为 fixture/test baseline 或历史 fixture observation，没有标记为用户确认的业务事实。

本文件与上述模型描述保持一致。生成本文不代表人工业务确认，也没有执行 Router 的 artifact 注册、确认或阶段迁移；是否确认以及后续阶段应由正式 Router 流程和有权确认者决定。
