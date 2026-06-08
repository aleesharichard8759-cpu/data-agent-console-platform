# Hooks

Hooks let the runtime insert safety checks, DLP, audit, and approval handling into the tool lifecycle. The design is inspired by coding-agent hooks, but this runtime uses them for data-governance and data-security enforcement.

Hooks do not replace Policy Engine. A hook can add extra checks or post-processing, but it cannot grant permission that Policy Engine denied. Tool execution still flows through `DataTool.execute()` and `PolicyEngine.evaluate()`.

## HookEventType

| Event | Meaning |
|---|---|
| `SESSION_START` | Runtime session starts |
| `USER_PROMPT_SUBMIT` | User submits a prompt |
| `PRE_TOOL_USE` | Before a DataTool executes |
| `POST_TOOL_USE` | After a DataTool returns |
| `PERMISSION_REQUEST` | Policy or gateway returns ASK |
| `PERMISSION_DENIED` | Policy or gateway returns DENY |
| `TASK_COMPLETED` | Governance task completes |
| `PRE_COMPACT` | Before memory/context compaction |
| `POST_COMPACT` | After memory/context compaction |

## HookResult

`HookResult` contains:

- `continue_execution`: whether the lifecycle should continue.
- `decision`: `ALLOW`, `ASK`, `DENY`, or `NONE`.
- `reason`: safe human-readable reason.
- `system_message`: optional message for runtime coordination.
- `metadata`: structured hook metadata.

If any hook returns `continue_execution=false`, `HookManager` stops running hooks for that event. In `PRE_TOOL_USE`, this blocks tool execution and writes an audit event.

## Default Hooks

| Hook | Event | Behavior |
|---|---|---|
| `AuditPreToolUseHook` | `PRE_TOOL_USE` | Records a pre-tool audit event |
| `AuditPostToolUseHook` | `POST_TOOL_USE` | Records a post-tool audit event |
| `DenySensitiveModelContextHook` | `POST_TOOL_USE` | Prevents L4/L5 results from entering model context |
| `RequireApprovalHook` | `PERMISSION_REQUEST` | Adds an approval placeholder for ASK results |
| `MaskingPostToolUseHook` | `POST_TOOL_USE` | Masks sensitive fields in mock results |

## Registry Integration

`DataToolRegistry.execute_tool()` now runs:

```text
PRE_TOOL_USE hooks
  -> DataTool.execute()
  -> PERMISSION_DENIED hooks if result is DENY
  -> PERMISSION_REQUEST hooks if result is ASK
  -> POST_TOOL_USE hooks
```

The registry never calls a tool implementation directly. It calls the DataTool unified execution method, which still performs input validation and Policy Engine evaluation.

## Security Requirements

- Hooks cannot bypass Policy Engine.
- Hook blocking must be auditable.
- Sensitive data masking must be testable.
- L4/L5 results cannot enter model context.
- Approval hooks only return placeholders; they do not implement a real approval system.

