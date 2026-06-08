# Domain Model

阶段 1 定义 Data Governance Agent Runtime 的核心领域模型。所有模型位于 `app/domain`，使用 Pydantic v2，只表达数据结构和基础安全校验，不实现 Agent 业务逻辑、数据库连接或真实工具执行。

## 用户与身份

| 模型 | 含义 |
|---|---|
| `UserRole` | 用户角色枚举，如 Data Steward、Data Owner、Security Reviewer、Agent Service。 |
| `Department` | 企业组织部门上下文，用于后续权限、审批和审计归属。 |
| `UserContext` | 当前用户或服务账号身份，包含角色、部门、是否服务账号、是否允许进入模型上下文。 |
| `AuthContext` | 一次认证会话，包含用户、session、认证方式、授权 scope、过期时间和是否需要额外审批。 |

安全字段：

- `allow_in_model_context` 明确身份信息是否允许进入模型上下文。
- `requires_approval` 标记认证上下文是否需要额外审批。

## 数据资产

| 模型 | 含义 |
|---|---|
| `DataDomain` | 数据业务域枚举，如交易、商品、库存、物流、财务、客户、安全等。 |
| `AssetOwner` | 数据资产责任人，表达 owner、steward 或其他责任角色。 |
| `DataAsset` | 数据资产基类，包含名称、唯一标识、业务域、Owner、敏感等级、安全标签和上下文边界。 |
| `DatabaseAsset` | 数据库资产，表达数据库类型和环境。 |
| `TableAsset` | 表资产，表达库、Schema、表名和列集合。 |
| `ColumnAsset` | 字段资产，表达所属表、字段名、类型、是否可空、是否必须脱敏。 |
| `MetricAsset` | 指标资产，表达指标定义、聚合逻辑、粒度和来源资产。 |

安全字段：

- `sensitivity_level` 表达资产敏感等级。
- `sensitivity_tags` 表达敏感标签。
- `is_production` 标记是否生产资产。
- `requires_approval` 标记访问是否必须审批。
- `allow_in_model_context` 标记是否允许进入模型上下文。

基础校验：

- L4/L5 资产必须 `requires_approval=true`。
- L4/L5 资产不得 `allow_in_model_context=true`。
- 生产资产不得进入模型上下文。

## 数据分级

| 模型 | 含义 |
|---|---|
| `SensitivityLevel` | 数据敏感等级，取值为 L1、L2、L3、L4、L5。 |
| `SensitivityTag` | 敏感标签，如个人信息、财务敏感、经营敏感、凭证敏感。 |
| `DataClassificationResult` | 一次资产识别或分类结果，包含等级、标签、置信度、证据和审批要求。 |

基础校验：

- `confidence` 必须在 0 到 1 之间。
- L4/L5 分类结果必须审批。
- L4/L5 分类结果不得进入模型上下文。

## 治理任务

| 模型 | 含义 |
|---|---|
| `GovernanceTaskType` | 治理任务类型，如资产盘点、元数据补全、数据质量、指标治理、敏感识别、血缘影响、权限巡检、治理报告。 |
| `GovernanceTaskLevel` | 治理任务等级 G1 到 G5，用于表达风险、影响面和审批强度。 |
| `GovernanceTaskStatus` | 治理任务状态，如 created、planning、pending_approval、running、completed、denied。 |
| `GovernanceTask` | 治理任务主模型，可表达“订单域数据质量治理”这类任务，并关联目标资产。 |

安全字段：

- `requires_approval` 表达任务是否需要审批。
- `allow_in_model_context` 表达任务描述是否允许进入模型上下文。

基础校验：

- G4/G5 任务必须审批。
- G4/G5 任务不得进入模型上下文。

## 工具调用

| 模型 | 含义 |
|---|---|
| `ToolRiskLevel` | 工具调用风险等级，取值 low、medium、high、critical。 |
| `ToolExecutionStatus` | 工具执行状态，如 allowed、asked、denied、succeeded、failed、masked。 |
| `ToolCallRequest` | 工具调用请求，包含工具名、动作、参数、风险等级、审批要求和 SQL Gateway 要求。 |
| `ToolCallResult` | 工具调用结果，包含状态、输出、安全错误信息、脱敏字段和上下文边界。 |

基础校验：

- high / critical 工具调用必须审批。
- high / critical 工具调用不得进入模型上下文。
- `sql.*` 动作必须声明 `requires_sql_gateway=true`。

## 权限决策

| 模型 | 含义 |
|---|---|
| `PolicyDecision` | 权限决策枚举，取值 allow、ask、deny。 |
| `PolicyReason` | 策略原因，包含 code、message 和 rule_id。 |
| `PolicyEvaluationResult` | 策略评估结果，包含最终决策、原因、是否需要审批和上下文边界。 |

设计原则：

- `ALLOW` 表示允许执行。
- `ASK` 表示进入 Governance Plan Mode 或审批。
- `DENY` 表示默认拒绝或明确阻断。

## 审计

| 模型 | 含义 |
|---|---|
| `AuditEventType` | 审计事件类型，如任务创建、策略评估、工具请求、审批、脱敏、错误。 |
| `AuditActor` | 审计行为人，可能是用户、服务或 Agent。 |
| `AuditTarget` | 审计对象，如资产、任务、工具调用或审批单。 |
| `AuditEvent` | 审计事件，记录行为人、目标、动作、结果、原因和安全元数据。 |

安全字段：

- `allow_in_model_context` 默认 false，避免审计记录中的敏感上下文被注入模型。
- `sensitivity_level` 可以记录目标对象敏感等级。

## 审批

| 模型 | 含义 |
|---|---|
| `ApprovalStatus` | 审批状态，如 pending、approved、rejected、canceled、expired。 |
| `ApprovalDecision` | 审批决策，取值 approve 或 reject。 |
| `ApprovalRequest` | 审批请求，包含申请人、审批人、目标、原因、状态、决策和时间。 |

基础校验：

- 待审批状态不得有最终决策。
- 已批准或已拒绝状态必须有最终决策。
- 审批请求默认 `requires_approval=true`。

