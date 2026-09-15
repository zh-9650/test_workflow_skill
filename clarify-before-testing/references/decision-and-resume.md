# Decision And Resume｜Run 选择与恢复

## Run 自动发现

优先读取 `work/test-runs/*/internal/state/run-status.json`。

- 只有一个 active Run：继续；
- 多个 active Run：根据当前项目/最近更新时间/上下文选择；
- 无法判断：只询问一次让用户选择；
- 不要默认为同一项目再创建新 Run。

## 新 Run

只有用户明确开始一个新的测试任务，且当前没有可继续 Run 时创建。

## 恢复信息

恢复只需加载：

- `run-status.json`
- 当前阶段正式产物
- 当前阶段必要 internal 文件
- 当前 Batch Task / Result（执行阶段）

不要重新加载全部历史聊天和所有证据。

## Case 中断

从 Case 开头重跑，因为中断时最后一个动作是否提交成功可能不确定。

先检查数据当前状态，再重新执行。

## 局部阻塞

一个 Case/Batch 阻塞时：

- 标记受影响范围；
- 检查依赖；
- 无依赖部分继续；
- next_action 指向真正可执行的下一个动作。

## 用户暂停

记录：

- 当前 Stage；
- 当前 Batch；
- 当前 Case；
- pending_user_inputs；
- next_action。

不要生成复杂 Resume Pack。
