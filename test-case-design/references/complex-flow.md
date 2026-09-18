# Complex Flow

复杂业务链需要：

```text
Start
→ Checkpoint 1
→ Checkpoint 2
→ ...
→ Final
```

至少两个 intermediate checkpoint。

每个 checkpoint 应检查实际适用的：
- 当前业务数据；
- 当前状态；
- 当前关系；
- 当前下游可见事实；
- 当前权限/候选/索引等业务结果。

不要为了做“长链”把互不相关的 Test Point 串起来。
