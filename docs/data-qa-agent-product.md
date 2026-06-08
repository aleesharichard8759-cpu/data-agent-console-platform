# Data&QA Agent Product MVP

Data&QA Agent Product is the product layer above Data Governance Agent Runtime. It turns a user question into a structured, auditable data or knowledge QA task. The product layer is intentionally separate from the runtime security kernel.

## Boundary

```text
Data&QA Agent Product
  -> request intake
  -> task identification
  -> clarification
  -> semantic mapping
  -> execution planning
  -> analysis execution
  -> answer synthesis
  -> risk review
  -> feedback persistence

Data Governance Agent Runtime
  -> DataTool
  -> Policy Engine
  -> SQL Gateway
  -> DLP / Masking
  -> Audit
```

The product layer never connects directly to production databases and never stores raw credentials. Data lookup is routed through existing governed tools such as `search_metadata`, `get_metric_definition`, and `query_sql`.

## MVP Scope

Stable MVP tasks:

- L1 metric query, such as "上个月华东区的销售额是多少？"
- L1 metric explanation, such as "其他收入是什么？"
- L1 knowledge QA for usage rules, process, and policy explanation

Escalated MVP tasks:

- L2 anomaly diagnosis
- L3 attribution analysis
- L4 business advice or operating action suggestions

Sensitive detail, secret, raw ODS, masking-bypass, and ungoverned asset requests are denied by default or routed to human review.

## Product Objects

The implementation in `app/data_qa/` defines:

- `DataQATaskRequest`
- `StructuredTask`
- `SemanticIntent`
- `ExecutionPlan`
- `AgentAnswer`
- `DataQAFeedbackEvent`
- `TraceRecord`

These objects are product-level contracts. They can later be backed by DeerFlow, Langfuse, real MCP connectors, or a web workspace without changing the runtime boundary.

## REST API

- `GET /data-qa/mvp-targets`: returns MVP scope, thresholds, and safety defaults.
- `POST /data-qa/run`: runs one deterministic Data&QA task.
- `GET /data-qa/tasks/{task_id}`: returns a stored run result.
- `POST /data-qa/feedback`: stores positive or negative user feedback.
- `GET /data-qa/bad-cases`: returns feedback routed into the Bad Case queue.

## Evaluation

The existing `EvalCase` model now supports Data&QA product fields:

- `expected_sql`
- `expected_result_schema`
- `expected_answer_key_points`
- `reference_solution`
- `last_verified_at`

The deterministic tests cover L1 query, metric explanation, ambiguity clarification, sensitive denial, L2+ escalation, feedback, and Bad Case routing.

## Current Limitations

- The MVP uses deterministic rules instead of an LLM.
- Knowledge QA uses built-in mock entries instead of a real knowledge connector.
- Query execution returns mock results after SQL Gateway review.
- Langfuse integration is represented by `TraceRecord`; a real Langfuse client is still a future connector.
- IAM, SSO, approval system, DLP platform, SIEM, log retention, and model-provider security controls remain `待确认`.
