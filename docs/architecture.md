# Architecture

## Stage 0 Scope

This document describes the initial project skeleton for Data Governance Agent Runtime.

Stage 0 intentionally does not implement Agent business logic, database access, SQL execution, or production change capabilities. It only defines the module boundaries and a minimal FastAPI health endpoint.

## Runtime Boundary

All future Agent activity must stay inside the governed runtime boundary:

```text
User Request
  -> Agent Runtime
  -> Agent / Subagent
  -> DataTool
  -> Policy Engine
  -> SQL Gateway or Connector
  -> DLP / Masking
  -> Audit / Trace
  -> Response
```

## Module Responsibilities

| Module | Responsibility |
|---|---|
| `app/main.py` | FastAPI application factory and HTTP entrypoint |
| `app/core` | Configuration, shared errors, application constants |
| `app/domain` | Governance domain models such as assets, metrics, lineage, plans |
| `app/policy` | Allow / Ask / Deny policy model and rule evaluation |
| `app/tools` | DataTool protocol and governed tool implementations |
| `app/hooks` | Runtime lifecycle hooks before and after tool execution |
| `app/agents` | Agent and subagent orchestration |
| `app/runtime` | Agentic loop, plan mode, task execution state |
| `app/security` | DLP, masking, sensitive-field checks, safety boundaries |
| `app/audit` | Audit events, trace IDs, immutable execution records |
| `app/memory` | Runtime memory, compaction, and safe context persistence |
| `app/evals` | Case datasets, regression tests, automatic evaluations |
| `app/connectors` | Adapters for OpenMetadata, warehouses, schedulers, observability, tickets |

## Security Principles

- Agent does not directly access production data.
- Agent does not hold raw database credentials.
- Data access must use DataTool.
- DataTool execution must pass Policy Engine.
- SQL execution must use SQL Gateway.
- Results must pass DLP / Masking before they are exposed.
- High-risk actions must enter Governance Plan Mode and approval.
- All steps must be auditable.
- Fail closed on missing policy, missing approval, or runtime errors.

## Future Integration Points

Future stages can add connectors for OpenMetadata, Doris, StarRocks, DolphinScheduler, Langfuse, and ticketing systems. These connectors should remain behind the DataTool and Policy Engine boundary.

