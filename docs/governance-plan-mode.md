# Governance Plan Mode

Governance Plan Mode 是中高风险数据治理动作的运行时安全闸。它不依赖 Prompt，
而是在代码层控制状态、审批占位、工具白名单和审计。

## 状态

- `disabled`: 未进入计划模式。
- `planning`: 正在生成治理计划，只允许只读工具。
- `waiting_approval`: 已生成计划，等待 mock 审批。
- `approved`: 计划已由 mock approver 批准。
- `rejected`: 计划被拒绝，或触发 G5 硬边界。
- `executing`: 已批准计划进入执行态。

## GovernancePlan

计划对象包含：

- `plan_id`
- `task_id`
- `title`
- `summary`
- `affected_assets`
- `proposed_actions`
- `risk_level`
- `required_approvers`
- `rollback_plan`
- `approval_required`
- `allowed_tools_after_approval`

每个计划必须包含 `rollback_plan`。没有回滚方案的计划不能提交。

## 运行规则

`PLANNING` 状态只允许 `is_read_only() == true` 的工具。

`is_destructive() == true` 的工具不能在计划模式直接执行，即使计划已审批。

计划审批后，仍然只能执行 `allowed_tools_after_approval` 中列出的工具。

未审批计划不能进入 `EXECUTING`。

G5 任务和 G5 计划永远不能审批通过。系统会把状态切到 `rejected` 并写入审计。

## 审计

所有状态变化都写入 Audit Logger：

- 进入计划模式：`plan_mode_entered`
- 创建计划：`plan_created`
- 请求审批：`approval_required`
- 审批通过：`plan_approved`
- 审批拒绝：`plan_rejected`
- 执行计划：`plan_execution_started`
- 工具阻断：`permission_denied`

审计事件只保存计划摘要、资产引用、状态和原因，不保存敏感原文或真实执行结果。

## MVP 边界

当前阶段只实现 mock approver 和状态机，不接真实工单、审批平台或生产执行系统。

真实审批系统接入时，应把 `request_approval()` 映射到企业审批/工单系统，把审批回调
映射到 `approve_plan()` 或 `reject_plan()`，并保持默认拒绝和全程审计。
