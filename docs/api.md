# REST API

Data Governance Agent Runtime 的 REST API 默认只使用 mock catalog、mock warehouse、
InMemoryAuditLogger 和确定性规则运行时。API 不连接真实数据库，不返回真实 SQL 结果集，
不暴露敏感原文。

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

创建 mock 会话。未传请求体时使用默认 `demo_user`。

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
{"sql": "select * from dwd_customer_detail_d"}
```

危险 SQL 返回 `DENY`，中风险 SQL 返回 `ASK`，低风险聚合查询可返回 `ALLOW`。

### POST /tools/{tool_name}/dry-run

通过 DataToolRegistry 执行 mock dry-run，仍然经过 Policy Engine、Hook、Audit。

```json
{
  "parameters": {"query": "order", "limit": 5}
}
```

### POST /plans/{plan_id}/approve

mock 审批通过。默认审批人为 `mock_security_reviewer`。

### POST /plans/{plan_id}/reject

mock 审批拒绝。

```json
{"approver": "mock_security_reviewer", "reason": "风险待确认"}
```

## 安全边界

- API 默认只使用 mock 数据。
- SQL 只能审查或 mock 执行，且必须经过 SQL Gateway。
- 工具 dry-run 必须经过 DataToolRegistry 和 Policy Engine。
- 不返回敏感原始结果集。
- 审计日志默认不保存原始 payload，只保存摘要、风险、决策和 hash。
