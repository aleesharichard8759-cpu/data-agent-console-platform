# Stage 17 Code Review

本审查面向 Data Governance Agent Runtime 当前 MVP。结论：整体分层已经形成可演进的安全运行时骨架，核心调用链是 `GovernanceEngine / Subagents -> DataToolRegistry -> Hooks -> DataTool -> PolicyEngine -> SQLGateway -> Audit / DLP`。当前实现仍是 mock/stub，不连接真实数据库。

## 高风险问题

### G5 策略硬边界不够严格

审查发现：`PolicyEngine` 之前对 G4/G5 统一返回 `ASK`。Plan Mode 会阻止 G5 审批通过，但策略层本身没有体现 “G5 永远 DENY”。

修复：`PolicyEngine` 已拆分硬边界：

- `G5` 直接 `DENY`
- `G4` 返回 `ASK`，进入计划/审批

补充测试：

- `test_policy_g5_task_is_denied`
- `test_g5_policy_request_is_denied_before_plan_mode`

### Registry 可不挂 HookManager

审查发现：`DataToolRegistry()` 允许不传 HookManager，虽然 Policy Engine 仍会执行，但默认 DLP/敏感上下文 Hook 可能缺失。

修复：`DataToolRegistry` 现在默认安装 `build_default_hook_manager()`，显式传入 HookManager 时仍可覆盖用于测试或定制。

补充测试：

- `test_default_registry_hooks_mask_sensitive_tool_output`

### 通用 SQL Tool 结果默认可进入模型上下文

审查发现：`QuerySQLTool.allow_in_model_context()` 返回 `True`。即使 SQL Gateway 会拦截敏感字段，通用 SQL 结果仍不应默认进入模型上下文。

修复：`QuerySQLTool` 默认 `allow_in_model_context=False`。上层应使用压缩摘要和 evidence refs 引用结果。

补充测试：

- `test_query_sql_tool_must_pass_sql_gateway_before_mock_execution`

### 审计 raw payload 标志可被调用方打开

审查发现：`InMemoryAuditLogger` 曾信任 `AuditEvent.raw_payload_allowed=True`，可能导致调用方绕过审计脱敏约束。

修复：审计 logger 存储前强制 `raw_payload_allowed=False` 和 `allow_in_model_context=False`，并对 metadata 中的敏感值模式做哈希化。

补充测试：

- `test_audit_logger_forces_raw_payload_disabled_and_hashes_sensitive_values`

### Plan Mode 审批标志可被高风险计划设为 false

审查发现：`GovernancePlan.approval_required` 可以在 G4/G5 计划中被设为 `False`，虽然执行仍需批准集合，但模型语义会误导 API/报告。

修复：`GovernancePlan` 校验 G4/G5 必须 `approval_required=True`；`PlanModeManager` 缺 Audit Logger 直接 fail closed。

补充测试：

- `test_high_risk_plan_cannot_disable_approval_requirement`
- `test_plan_mode_without_audit_logger_fails_closed`

## 中风险问题

- SQL 解析仍是轻量正则实现，覆盖了 DDL/DML、`SELECT *`、敏感字段、ODS、跨域 JOIN、未知表和危险函数，但复杂 SQL、注释、嵌套查询、方言函数仍应引入正式 SQL parser。
- Audit 已补充 `ImmutableFileAuditLogger`，支持本地 append-only JSONL、哈希链校验、写失败 fail closed 和活跃查询留存策略；真实系统仍建议接 WORM/对象锁/SIEM。
- Hook 的审计事件较多，DENY 路径会同时留下工具拒绝和 Hook 后置事件。审计覆盖更完整，但后续可增加事件关联字段以减少分析噪声。
- Memory 已区分字段名摘要和敏感值：允许保存 `shipping_address` 字段策略摘要，继续拒绝地址赋值、raw value、明细和敏感等级 L3/L4/L5 内容。
- Eval case 数量足够，但 grader 仍是规则驱动，未来需要更细的证据链评分和结构化输出评分。

## 可优化问题

- `SQLGateway.detect_columns()` 对表达式、别名、CTE 的识别能力有限。
- `PolicyEngine` 规则匹配没有条件表达式和组合谓词，复杂企业策略可扩展为 DSL 或决策表。
- `AuditEventType` 里存在兼容别名，长期可统一事件枚举并通过迁移层兼容旧值。
- `GovernanceEngine` 的九节点流程是确定性规则，后续接 LLM 前应保留同样的工具安全边界。
- Connector mock 已具备接口和审计，但真实 connector 的超时、重试、断路器和凭据隔离仍需专门设计。

## 推荐重构计划

1. 将安全硬边界抽成 `RuntimeGuard`，统一承载 G5/L5/无审计/无 SQL Gateway 等 fail-closed 规则。
2. 为 SQL Gateway 引入 `sqlglot` 或等价 parser，保留当前正则规则作为兜底检测。
3. 把 Audit 事件增加 `trace_id`、`parent_event_id`、`tool_call_id`，让重复但必要的审计事件可关联分析。
4. 将 PolicyRule 扩展为版本化策略包，支持规则测试快照和策略变更审计。
5. 将 Memory 安全检测拆成字段名摘要和敏感值检测两类，允许保存安全字段标准，继续禁止明细值。
6. 对 Subagents 增加工具白名单快照测试，防止未来新增工具时越权进入 agent。

## 本阶段已修复

- G5 策略层直接拒绝。
- DataToolRegistry 默认启用安全 Hooks。
- QuerySQLTool 默认不允许结果进入模型上下文。
- Audit Logger 强制关闭 raw payload 并哈希敏感值。
- G4/G5 GovernancePlan 必须要求审批。
- PlanModeManager 缺审计 logger fail closed。

## 验证命令

```bash
UV_CACHE_DIR=.uv-cache uv run pytest
UV_CACHE_DIR=.uv-cache uv run ruff check .
```
