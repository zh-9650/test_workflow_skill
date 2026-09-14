# Data Builder Method

优先确认真实业务入口：前端调用、API 文档、Controller/DTO/Validator、已有脚本，必要时看 UI Network。先最小试建一条，再 read-back 和核对业务状态，成功后沉淀可复用 Builder。

Builder 的 `business_entry` 只能是 API/UI；script 只是实现方式。业务对象必须核对存在性、状态、关联关系和 read-back，分别通过 `verified/read_back_verified/relations_verified` 表达。

Manifest 不允许人工写顶层 `ready=true`。通过 `data_manifest.py --finalize` 由 Contract 计算 `readiness.ready`；Runtime Precheck 仍会重新执行 Contract，避免伪造 readiness。
