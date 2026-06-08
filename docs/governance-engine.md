# GovernanceEngine

GovernanceEngine 是 Data Governance Agent Runtime 的确定性主循环。当前阶段只做
规则驱动编排，不接 LLM、不连接真实数据库、不执行生产变更。

## 主循环

主循环采用九节点任务链路：

1. `request_intake`
2. `task_classification`
3. `clarification`
4. `asset_mapping`
5. `governance_planning`
6. `evidence_collection`
7. `risk_review`
8. `result_synthesis`
9. `knowledge_persist`

每个节点都会生成 `GovernanceStep`，最终汇总为 `TaskRunResult`。

## 规则分类

当前不使用 LLM，而是根据关键词分类：

- “质量规则” -> `DATA_QUALITY`
- “字段注释” / “数据字典” -> `METADATA_COMPLETION`
- “指标” / “口径” -> `METRIC_GOVERNANCE`
- “敏感” / “脱敏” -> `SENSITIVE_DATA_DISCOVERY`
- “权限” -> `PERMISSION_INSPECTION`
- “血缘” / “影响” -> `LINEAGE_IMPACT`
- “治理报告” -> `GOVERNANCE_REPORT`

风险等级同样规则化：

- 删除、关闭审计、生产变更、绕过脱敏 -> `G5`
- 敏感、脱敏、权限、审批 -> `G4`
- 血缘、影响、口径 -> `G3`
- 其他默认 -> `G2`

## 集成组件

GovernanceEngine 集成：

- `DataToolRegistry`
- `PolicyEngine`
- `HookManager`
- `AuditLogger`
- `PlanModeManager`

工具调用必须通过 `DataToolRegistry.execute_tool()`，由工具内部调用 Policy Engine，
再经过 Hook 和 Audit。Engine 不直接连接数据库，也不绕过 SQL Gateway。

## 低风险任务

G1/G2 任务会走完整九节点。当前只使用只读 mock 工具收集证据，然后在
`result_synthesis` 节点生成确定性建议。

例如数据质量任务会建议检查非空、唯一性、新鲜度和值域规则，但不会直接创建真实质量规则。

## 高风险任务

G4/G5 任务在 `governance_planning` 节点进入 Governance Plan Mode：

- 创建治理计划
- 生成审批占位
- 写入审计
- 返回 `waiting_approval`

G5 任务后续仍不能通过 mock 审批。

## 输出

`TaskRunResult` 包含：

- `task_id`
- `status`
- `steps`
- `evidence`
- `recommendations`
- `required_approvals`
- `audit_refs`

所有输出都是可序列化对象，便于后续接入 API、评测集、Trace 或审计平台。

## 安全边界

- 不接 LLM。
- 不接真实数据库。
- 不执行生产变更。
- DENY 请求不会执行工具。
- 高风险任务进入 Plan Mode。
- 所有任务创建、计划、审批占位、工具调用和任务完成都写审计。
