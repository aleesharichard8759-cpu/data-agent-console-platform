# DataTool Protocol

DataTool 是 Data Governance Agent Runtime 的统一工具协议。Data Agent 不允许直接调用数据库、调度平台、权限系统或外部治理系统，所有能力都必须封装为 DataTool，并由运行时强制经过 Policy Engine。

## 核心边界

工具调用链路固定为：

```text
ToolCallRequest
  -> DataToolRegistry.execute_tool()
  -> default safety hooks
  -> DataTool.execute()
  -> validate_input()
  -> check_permission()
  -> PolicyEngine.evaluate()
  -> DENY / ASK / ALLOW
  -> connector-backed tool execution
  -> audit event
  -> ToolCallResult
```

任何工具不得绕过 `PolicyEngine.evaluate()`。`DataToolRegistry` 默认安装安全 Hooks，用于审计、审批占位、DLP masking 和模型上下文拦截。当前已移除内置演示数据；没有真实 Connector 的工具必须 fail closed。

## DataTool 接口

每个工具必须提供：

| 属性或方法 | 含义 |
|---|---|
| `name` | 工具唯一名称 |
| `description` | 工具说明 |
| `input_model` | Pydantic v2 输入模型 |
| `output_model` | Pydantic v2 输出模型 |
| `validate_input()` | 校验 `ToolCallRequest.parameters` |
| `check_permission()` | 调用 `PolicyEngine.evaluate()` |
| `execute()` | 统一执行入口，包含校验、权限、执行和审计 |
| `is_read_only()` | 是否只读 |
| `is_destructive()` | 是否破坏性操作 |
| `is_concurrency_safe()` | 是否并发安全 |
| `get_sensitivity_level()` | 工具默认敏感等级 |
| `requires_approval()` | 工具是否默认需要审批 |
| `allow_in_model_context()` | 工具结果是否允许进入模型上下文 |
| `max_rows` | 工具最大返回行数 |
| `max_bytes` | 工具最大返回字节数 |

工具子类只实现受控 `_execute()`，真实系统接入必须放在 connector 中，并继续保留 DataTool + Policy Engine + SQL Gateway 边界。

## ToolExecutionContext

`ToolExecutionContext` 包含：

| 字段 | 含义 |
|---|---|
| `user_context` | 当前用户身份 |
| `task_context` | 当前治理任务上下文，可为空 |
| `policy_engine` | 权限裁决引擎 |
| `audit_logger` | 审计记录器 |
| `dry_run` | 是否试运行 |
| `plan_mode` | 是否处于 Governance Plan Mode |

Plan Mode 下只读工具允许执行；非只读工具返回 `ASK`，不执行。

## ToolExecutionResult

所有工具返回 `ToolCallResult`：

- `DENY`：不执行工具，返回拒绝原因和审计事件。
- `ASK`：不执行工具，返回 `approval_required=true` 和审计事件。
- `ALLOW`：在真实 Connector 可用时执行工具，返回结构化结果、策略决策和审计事件。

## 当前工具

| 工具 | 作用 | 当前行为 |
|---|---|---|
| `QuerySQLTool` | SQL Gateway 审查后执行只读查询 | 使用 StarRocks Connector；未配置时 fail closed |
| `SearchMetadataTool` | 搜索元数据目录 | 需要真实元数据 Connector；未配置时 fail closed |
| `GetMetricDefinitionTool` | 查询指标定义 | 需要真实指标 Connector；未配置时 fail closed |
| `GenerateQualityRulesTool` | 生成质量规则建议 | 需要真实质量 Connector；未配置时 fail closed |

## 安全要求

- 不保存或返回真实密钥、Token、手机号、邮箱、地址。
- 不允许跳过 `PolicyEngine`。
- SQL 工具必须经过 `SQLGateway`。
- 所有工具调用必须写审计事件。
- DENY / ASK 时工具主体不得执行。
- 未配置真实 Connector 时不得返回本地样例数据。
