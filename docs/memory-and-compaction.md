# Governance Memory and Context Compaction

Governance Memory 用于保存安全摘要，例如指标口径、字段标准、治理规则模板、
用户反馈和参考资料。它不是权限系统，不能绕过 Policy Engine，也不能保存敏感明细。

Context Compaction 用于长任务压缩上下文，只保留结构化摘要、证据引用和关键裁决，
不把大量工具结果或明细 rows 塞进模型上下文。

## GovernanceMemory

字段：

- `memory_id`
- `memory_type`: `business` / `metric` / `governance` / `security` / `feedback` / `reference`
- `title`
- `content_summary`
- `source_refs`
- `sensitivity_level`
- `allow_retrieval`
- `expires_at`
- `last_verified_at`

## MemoryStore

方法：

- `add_memory()`
- `search_memory(query)`
- `list_memory()`
- `delete_memory()`
- `verify_memory_freshness()`

`search_memory()` 只返回：

- `allow_retrieval = true`
- 未过期
- 匹配查询词

召回前必须检查是否过期。

## 安全规则

- L3/L4/L5 内容不能写入 memory。
- memory 不能保存手机号、邮箱、地址明细、Token、密码等敏感值。
- memory 可以保存字段名和策略摘要，例如 `shipping_address` 的分级、脱敏策略、
  负责人待确认项；但不能保存 `address=...`、原文地址、raw value 或明细样例。
- security memory 只能保存策略摘要，不能保存敏感值或明细。
- Memory 不是权限系统。即使 memory 被召回，后续工具访问仍必须经过 Policy Engine。
- Memory 不能作为生产数据访问的替代缓存。

## Compaction

实现函数：

- `compact_tool_result()`
- `compact_task_trace()`
- `compact_agent_result()`

压缩规则：

- 保留 evidence refs 和 audit refs。
- 保留审批、SQL review、policy decision 的结构化摘要。
- 不保留大结果集。
- 不保留 raw rows、records 或明细结果。
- 对 AgentResult 保留 veto、veto reason、finding keys 和工具证据引用。

## 当前边界

当前实现是 MVP 内存实现，不接真实向量库、文档库或长期存储。未来接入外部存储时，
必须保持同样安全边界：先安全校验，再写入；召回前检查过期；召回后仍不能绕过权限策略。
