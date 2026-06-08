# Audit Logger

Audit Logger 是 Data Governance Agent Runtime 的统一审计底座，用于记录任务、
工具调用、策略裁决、SQL 审查、DLP 脱敏、审批占位和执行结果。

## 设计原则

- 默认不保存原始请求负载、SQL 明文结果集或敏感字段明文。
- 所有高风险执行路径必须先经过 Policy Engine，再经过审计记录。
- SQL 审查只记录 SQL 摘要、长度、哈希、风险类型和裁决。
- 工具结果只记录摘要和结果哈希，不把原始结果集写入审计日志。
- 审计事件不可进入模型上下文，`raw_payload_allowed` 默认固定为 `false`。
- MVP 默认仍可使用 `InMemoryAuditLogger`；需要本地持久化和完整性校验时使用
  `ImmutableFileAuditLogger`。未来可替换为 OpenSearch、对象存储、Langfuse、
  SIEM 或企业审计平台。

## 核心接口

`AuditLogger` 提供三个基础方法：

- `log_event(event)`: 追加写入一个审计事件。
- `list_events(filter)`: 按事件类型、用户、会话、任务、工具、策略裁决查询事件。
- `get_event(event_id)`: 按事件 ID 查询单条事件。

`InMemoryAuditLogger` 额外提供运行时便捷方法：

- `record_tool_requested()`
- `record_policy_evaluation()`
- `record_sql_review()`
- `record_result_masked()`
- `record_tool_event()`

`ImmutableFileAuditLogger` 提供本地 append-only JSONL 审计账本：

- 每条记录保存 `previous_hash` 和 `record_hash`，形成哈希链。
- 初始化、查询和 `verify_integrity()` 会校验账本完整性。
- 写入或读取失败会抛 `AuditWriteError`，系统应 fail closed。
- 篡改账本会抛 `AuditIntegrityError`。
- `AuditRetentionPolicy` 控制活跃查询窗口；过期事件默认仍留在不可变账本中，
  由外部归档/留存系统处理物理生命周期。

## 事件类型

当前支持以下事件：

- `session_started`
- `task_created`
- `tool_requested`
- `policy_evaluated`
- `permission_denied`
- `approval_required`
- `sql_reviewed`
- `tool_executed`
- `result_masked`
- `task_completed`

## 审计字段

每条审计事件包含：

- `event_id`
- `timestamp`
- `user_id`
- `role`
- `session_id`
- `task_id`
- `agent_name`
- `tool_name`
- `asset_refs`
- `sensitivity_level`
- `policy_decision`
- `reason`
- `request_summary`
- `result_summary`
- `request_hash`
- `result_hash`
- `raw_payload_allowed`

旧版领域模型中的 `actor`、`target`、`action`、`outcome`、`metadata`、
`occurred_at` 仍保留，以兼容已有测试和后续审计详情扩展。

## 集成点

`PolicyEngine.evaluate()` 在工具运行时会写入 `policy_evaluated`。

`DataToolRegistry.execute_tool()` 会在工具调度入口写入 `tool_requested`。工具自身会
在 DENY、ASK、SUCCEEDED、FAILED 时写入对应审计事件。

`SQLGateway.review_sql()` 会写入 `sql_reviewed`。该事件不保存 SQL 明文，只保存
SQL 哈希、长度、风险类型和裁决原因。

`MaskingPostToolUseHook` 在实际脱敏字段时写入 `result_masked`。

Hook 阻断由 `DataToolRegistry` 统一转成 `permission_denied` 或 `approval_required`
事件，保证 Hook 不能绕过 Policy Engine。

## 安全边界

审计日志不是数据湖，也不是结果集缓存。它只能保存安全摘要、可检索索引字段和哈希。
敏感字段、SQL 明文结果、Token、密码、个人信息、地址等内容不得默认进入审计日志。

如果未来接入真实审计存储，必须保持相同边界：先脱敏、再写入、可追踪、不可由 Agent
直接关闭审计。

生产级审计存储还必须满足：

- 写入失败不得继续执行高风险动作。
- 不可由 Agent 或普通工具关闭审计链路。
- 账本应具备不可篡改校验或外部 WORM/对象锁能力。
- 留存策略只能影响查询/归档窗口，不能让 Agent 删除审计证据。
