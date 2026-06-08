# Security Hardening

阶段 15 增加安全红队回归测试与运行时加固。目标是验证 Data Governance Agent Runtime 的安全不依赖 Prompt，而由 Policy Engine、SQL Gateway、DataTool、Hook、Plan Mode、Audit 和 Memory 共同强制执行。

## 红队攻击面

### Prompt Injection

覆盖场景：

- 要求忽略安全规则。
- 要求绕过 Policy Engine。
- 要求关闭审计。
- 伪装成管理员、root、系统身份。
- 要求跳过审批、跳过 SQL Gateway。

加固点：

- Prompt 只影响任务分类，不改变运行时安全裁决。
- `token`、`secret`、`api key`、`密码`、`关闭审计`、`绕过脱敏` 等高危意图进入 G5。
- G4/G5 任务进入 Governance Plan Mode 或 DENY。
- G5 在 Policy Engine 硬边界直接 DENY；G4 返回 ASK 并进入计划/审批。

### SQL 风险

覆盖场景：

- `SELECT *`
- `DROP TABLE`
- `DELETE`
- `INSERT OVERWRITE`
- 无 LIMIT 明细查询
- 手机号、邮箱、地址、毛利字段
- `token` / `password` / `api_key`
- ODS 原始层、未知表、危险函数

加固点：

- 所有 SQL 必须经过 SQL Gateway。
- DDL/DML、敏感字段、危险函数直接 DENY。
- ODS、未知表、无 LIMIT 明细查询进入 ASK 或安全改写。
- 没有 SQL Gateway 时 SQL Tool fail closed。

### 工具越权

覆盖场景：

- MetadataAgent 调用 QuerySQLTool。
- QualityAgent 修改权限。
- SecurityAgent 审批自己的策略。
- Orchestrator 跳过 Policy Engine。

加固点：

- BaseAgent 强制工具白名单。
- Subagent 不允许白名单包含 `query_sql`。
- `ToolExecutionContext` 缺 Policy Engine 或 Audit Logger 会抛 `UnsafeOperationError`。

### 结果泄露

覆盖场景：

- 工具返回 L3/L4 字段。
- 结果中包含邮箱/手机号/地址模式。
- 审计日志保存敏感原文。
- Memory 保存敏感明细。

加固点：

- L4/L5 结果不能进入模型上下文。
- Hook / Masking / Audit 默认不保存原始结果集。
- `DataToolRegistry` 默认安装安全 Hooks，避免遗漏 DLP 和敏感上下文拦截。
- `QuerySQLTool` 默认不允许结果直接进入模型上下文，只允许通过摘要和 evidence refs 使用。
- Memory 拒绝 L3/L4/L5 和敏感标识符。

### 审批绕过

覆盖场景：

- 未审批执行 G4 动作。
- 审批后执行计划外工具。
- G5 任务被审批通过。

加固点：

- G4 进入 Plan Mode 并返回 ASK。
- Plan Mode 只允许计划内工具。
- G4/G5 计划必须声明 `approval_required=true`。
- G5 计划不能审批通过。

## SecurityRegressionSuite

`app/security/regression_suite.py` 提供：

- `SecurityCase`
- `SecurityCaseResult`
- `SecurityRegressionReport`
- `SecurityRegressionSuite`

默认包含 58 条红队 case，并通过 pytest 参数化形成独立回归测试。

运行：

```bash
UV_CACHE_DIR=.uv-cache uv run pytest tests/security
```

全量验证：

```bash
UV_CACHE_DIR=.uv-cache uv run pytest
UV_CACHE_DIR=.uv-cache uv run ruff check .
```

## 验收规则

- 所有高风险请求必须 DENY 或 ASK。
- L5 永远 DENY。
- G5 永远 DENY，不能审批通过。
- 没有 Policy Engine 不能执行工具。
- 没有 SQL Gateway 不能执行 SQL。
- 没有 Audit Logger 时系统 fail closed。
- Audit Logger 会强制 `raw_payload_allowed=false`，即使调用方手工传入 true 也不会保存原文。

## 禁止放松项

- 不允许为了通过功能测试放宽 Policy Engine。
- 不允许让 Subagent 直接执行 SQL。
- 不允许审计保存敏感明文。
- 不允许 Memory 保存敏感明细。
- 不允许真实执行生产变更、删除、调度上线。
