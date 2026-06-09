# SQL Gateway

SQL Gateway 是 Data Governance Agent Runtime 的 SQL 安全审查层。Data Agent 不允许直接执行 SQL，所有 SQL 必须先进入 SQL Gateway 做风险识别、裁决和必要的安全改写。

当前 `QuerySQLTool` 已切换到真实 Connector 路径：未配置 StarRocks 只读连接时 fail closed；配置后只在 SQL Gateway 返回 `ALLOW` 时执行真实只读查询。

## 执行边界

```text
QuerySQLTool
  -> DataTool permission check
  -> PolicyEngine.evaluate()
  -> SQLGateway.review_sql()
  -> DENY: 不执行，返回 reason
  -> ASK: 不执行，返回 approval_required
  -> ALLOW: 调用 WarehouseConnector.query_preview()
```

## SQLRiskType

| 风险 | 含义 |
|---|---|
| `SELECT_STAR` | 查询使用 `SELECT *`，可能暴露不必要字段 |
| `NO_LIMIT` | SELECT 查询没有 LIMIT |
| `DDL_DETECTED` | 检测到 DROP、ALTER、TRUNCATE、CREATE |
| `DML_DETECTED` | 检测到 INSERT、UPDATE、DELETE、MERGE |
| `SENSITIVE_COLUMN` | 查询敏感字段或 L3/L4/L5 字段 |
| `RAW_LAYER_ACCESS` | 查询 ODS 原始层 |
| `CROSS_DOMAIN_JOIN` | 跨业务域 JOIN |
| `LARGE_RESULT_RISK` | LIMIT 过大 |
| `UNKNOWN_TABLE` | 表不在显式资产上下文或 Connector 白名单中 |
| `UNSAFE_FUNCTION` | 检测到高风险函数或文件操作 |

## SQLReviewResult

SQL Gateway 返回 `SQLReviewResult`：

| 字段 | 含义 |
|---|---|
| `allowed` | 是否允许进入 Connector 执行 |
| `decision` | `ALLOW`、`ASK` 或 `DENY` |
| `risks` | 风险列表，每个风险都有明确 reason |
| `rewritten_sql` | 安全改写后的 SQL，例如自动追加 LIMIT |
| `reason` | 最终裁决原因 |
| `required_approval` | 是否需要审批 |

## 默认规则

| 规则 | 裁决 |
|---|---|
| `SELECT *` | `DENY` |
| DDL：DROP / ALTER / TRUNCATE / CREATE | `DENY` |
| DML：INSERT / UPDATE / DELETE / MERGE | `DENY` |
| 无 LIMIT 明细查询 | `ASK` |
| ODS 原始层 | `ASK` |
| 查询 L3/L4 字段 | `DENY` |
| 查询 L5 字段 | `DENY` |
| 查询 ADS/DWS 聚合指标 | `ALLOW` |
| 低风险 SELECT 无 LIMIT | 自动追加 `LIMIT 100` |

## 真实执行

`QuerySQLTool` 只有在以下条件全部满足时才会调用真实只读 Connector：

1. DataTool 权限检查通过。
2. Policy Engine 返回 `ALLOW`。
3. SQL Gateway 返回 `ALLOW`。
4. `DATAGENT_STARROCKS_SECRET_REF` 已配置并能解析凭证。
5. SQL 引用表在 `DATAGENT_STARROCKS_ALLOWED_TABLES` 白名单内。

如果任一条件不满足，工具主体不执行查询并返回失败或拒绝原因。

即使 SQL 被允许，`QuerySQLTool` 的结果也默认 `allow_in_model_context=false`。治理报告应引用结构化摘要、审计事件和 evidence refs，而不是把通用 SQL 结果直接放入模型上下文。

## 安全要求

- 不允许绕过 SQL Gateway。
- 不允许 DDL / DML / 危险函数。
- 不保存真实数据库连接配置或凭证明文。
- 表访问必须受 Connector 白名单约束。
- 所有风险必须返回明确 reason。
- 所有查询结果必须限制行数，并经过审计链路。
