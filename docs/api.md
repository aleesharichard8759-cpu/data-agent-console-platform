# REST API

Data Governance Agent Runtime 的 REST API 保留确定性规则运行时、InMemoryAuditLogger 和安全审查链路。内置演示数据已移除；涉及真实数据的工具必须通过 Connector、Policy Engine 和 SQL Gateway。

## 通用响应约束

所有业务响应必须包含：

- `trace_id`：单次响应追踪 id。
- `audit_refs`：本次请求相关审计事件 id。审计只保存摘要和 hash，不保存敏感明文。

## Endpoints

### GET /health

返回运行状态。

```json
{"status": "ok", "trace_id": "...", "audit_refs": []}
```

### POST /sessions

创建本地会话。未传请求体时使用默认 `demo_user`。

### POST /tasks

创建治理任务并完成规则分类。

```json
{"user_prompt": "请为订单域生成质量规则建议"}
```

### POST /tasks/{task_id}/run

执行确定性的九节点治理链路。G4/G5 任务会进入 Governance Plan Mode。

### GET /tasks/{task_id}

查看任务状态和最近一次运行结果。

### GET /tasks/{task_id}/audit

查看指定任务的审计事件。兼容入口 `GET /audit?task_id=...` 仍保留。

### POST /sql/review

只审查 SQL，不执行 SQL。

```json
{"sql": "select count(*) from ads_afs_rma_multi_dim_metric_1d limit 20"}
```

危险 SQL 返回 `DENY`，中风险 SQL 返回 `ASK`，低风险聚合查询可返回 `ALLOW`。

### POST /tools/{tool_name}/dry-run

通过 DataToolRegistry 执行工具 dry-run，仍然经过 Policy Engine、Hook、Audit。`query_sql` 在真实 StarRocks 连接配置完整时会进入只读查询路径；未配置时 fail closed。

```json
{
  "parameters": {"sql": "select count(*) from ads_afs_rma_multi_dim_metric_1d limit 20"}
}
```

### POST /plans/{plan_id}/approve

审批治理计划。默认审批人为 `security_reviewer`。

### POST /plans/{plan_id}/reject

拒绝治理计划。

```json
{"approver": "security_reviewer", "reason": "风险待确认"}
```

## 安全边界

- SQL 只能审查或通过真实只读 Connector 执行，且必须经过 SQL Gateway。
- 工具 dry-run 必须经过 DataToolRegistry 和 Policy Engine。
- 未配置真实 Connector 时不返回内置样例结果。
- 不返回敏感原始结果集。
- 审计日志默认不保存原始 payload，只保存摘要、风险、决策和 hash。
