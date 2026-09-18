# Test Point Granularity

## Atomic Test Point

一个普通 Test Point 应表达一个 primary mechanism：

```text
前置
+ 动作/事件
+ 一个核心业务 Expected
```

如果两个 Expected 可以独立实现错，则通常拆分。

## Composite Flow

只有真正需要验证端到端连续性时，允许：

```text
granularity = composite_flow
```

Composite Flow 必须引用多个已存在机制点对应的流程事实，不能替代原子机制覆盖。

## Over-broad 信号

- 标题中同时出现多个“并且/同时/同时保持/同时影响”；
- 同一个 TP 同时验证状态、关系、候选、权限、历史事实；
- 一个失败会阻止后续 Expected 被观察；
- 一个 TP 中存在多个可独立修复的缺陷机制。

## Over-split 信号

- 只差具体边界数值；
- 只差具体枚举样本；
- 只差对象实例；
- 业务动作、前置和 Expected 完全相同。

## 判断口诀

```text
Expected 可独立失败 → 倾向拆 TP
仅执行数据不同 → 留到 Case / Instance
```
