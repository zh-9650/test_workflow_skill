# Case Merge Rules

多个测试点共用一个用例主项时，必须同时满足：

1. 前置环境等价；
2. 主动作骨架一致；
3. 每个 TP 都有独立 Assertion；
4. 一个 Assertion 失败不会让其它 Assertion 无法观察；
5. 合并不会降低缺陷定位能力到不可接受程度。

高风险专项类型默认不合并：
- failure_atomicity；
- recovery；
- concurrency；
- stale_state；
- scope_isolation。

若确需合并，填写 `merge_exception_reason`。
