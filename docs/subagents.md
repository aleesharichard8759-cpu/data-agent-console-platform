# Specialized Subagents

Data Governance Agent Runtime 使用 Orchestrator + 专业 Subagents，而不是一个万能 Agent。
每个 Agent 都有独立职责、工具白名单和权限边界。

## BaseAgent

`BaseAgent` 定义：

- `name`
- `description`
- `allowed_tools`
- `disallowed_tools`
- `max_turns`
- `permission_mode`
- `run(task_context) -> AgentResult`

所有工具调用必须经过 `BaseAgent.call_tool()`。该方法会先检查 Agent 工具白名单，
再调用 `DataToolRegistry.execute_tool()`，因此仍然经过 Policy Engine、Hooks 和 Audit。

任何 Agent 都不能调用 `query_sql`，也不能提交 `sql.*` action。

## 专业 Agent

### MetadataAgent

允许工具：

- `search_metadata`
- `get_table_metadata`

输出：

- 缺 Owner 表
- 缺注释字段
- 疑似重复表
- 元数据补全建议

### DataQualityAgent

允许工具：

- `generate_quality_rules`
- `run_quality_check`

输出：

- 完整性规则
- 唯一性规则
- 有效性规则
- 一致性规则
- 强规则
- 弱规则

当前只生成 mock 建议，不创建真实质量规则。

### SecurityAgent

允许工具：

- `classify_sensitivity`
- `check_permission`

输出：

- 敏感字段清单
- L1-L5 分级
- 脱敏建议
- 是否允许进入模型上下文

SecurityAgent 有一票否决权。只要发现 L4/L5 字段，`AgentResult.veto` 为 `true`，
Orchestrator 的汇总状态为 `vetoed`。

### MetricAgent

允许工具：

- `get_metric_definition`
- `generate_metric_card`

输出：

- 业务口径
- 技术口径
- 维度
- 时间字段
- 待确认问题

## AgentRegistry

`AgentRegistry` 支持：

- `register(agent)`
- `get_agent(name)`
- `list_agents()`
- `select_agents_for_task(task)`

默认选择策略：

- `DATA_QUALITY` -> MetadataAgent + DataQualityAgent
- `METADATA_COMPLETION` -> MetadataAgent
- `METRIC_GOVERNANCE` -> MetadataAgent + MetricAgent
- `SENSITIVE_DATA_DISCOVERY` / `PERMISSION_INSPECTION` -> SecurityAgent
- `GOVERNANCE_REPORT` -> MetadataAgent + DataQualityAgent + SecurityAgent + MetricAgent

## Orchestrator

`AgentOrchestrator` 根据任务类型选择 Agent，运行后汇总多个 `AgentResult`：

- `agent_results`
- 合并后的 `findings`
- 合并后的 `recommendations`
- `security_veto`
- `vetoed_by`

GovernanceEngine 在结果综合阶段可以调用 Orchestrator 汇总专业 Agent 发现。

## 安全边界

- 每个 Agent 必须有工具白名单。
- Agent 不允许直接执行 SQL。
- Agent 不允许绕过 DataToolRegistry。
- SecurityAgent 有一票否决权。
- 当前所有专业工具都是 mock，不连接真实数据库，不调用真实权限系统，不执行生产变更。
