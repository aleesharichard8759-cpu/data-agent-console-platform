# Integration Plan

本计划说明未来如何把 mock Connector 替换为真实企业系统 Connector。当前版本不实现真实连接。

## 接入顺序

1. MetadataConnector
   - 先接 OpenMetadata / DataHub 的只读元数据 API。
   - 只允许读取资产、字段、owner、标签、血缘摘要。
   - 不读取真实表数据。

2. SQL Gateway + WarehouseConnector
   - 先完成 SQL Gateway 的生产级审查和审批链路。
   - WarehouseConnector 只能接收 SQL Gateway 审查后的只读 SQL。
   - 禁止 DDL、DML、生产变更和绕过脱敏。

3. PermissionConnector
   - 对接 IAM / Ranger / 自研权限系统。
   - PermissionConnector 只提供权限事实，最终 Allow / Ask / Deny 仍由 Policy Engine 裁决。

4. MaskingConnector
   - 对接 DLP / Presidio / 自研脱敏服务。
   - 所有工具结果进入模型上下文前必须经过 DLP / Masking。

5. QualityConnector / MetricConnector / LineageConnector
   - 接质量平台、指标平台、血缘服务。
   - 只接治理元数据、规则结果、指标定义和结构化摘要。

6. WorkflowConnector / SchedulerConnector
   - 先接工单审批，再接 dry-run 调度。
   - 真实调度执行必须由审批完成后的受控流程触发。

## 必须完成的生产化控制

- 显式配置真实连接，不能默认读取环境变量里的生产地址或密钥。
- 密钥必须来自企业密钥管理系统，不能写入代码、测试或文档。
- 每个连接器必须配置超时、重试上限和熔断策略。
- 每个连接器调用必须写审计，并记录 trace id。
- 所有失败默认拒绝，不允许降级为直接执行。
- 所有 SQL 必须走 SQL Gateway。
- 所有工具调用必须先过 Policy Engine。
- 所有结果必须经过 DLP / Masking。
- G4/G5 任务必须进入 Governance Plan Mode 和审批。

## 禁止项

- 禁止 Agent 直接连接生产库。
- 禁止 Connector 默认启用真实连接。
- 禁止保存真实手机号、邮箱、地址、Token、密码、数据库密码。
- 禁止在测试中使用真实个人信息或真实密钥。
- 禁止绕过 Policy Engine、SQL Gateway、Audit Logger。
- 禁止真实执行删除、修改、建表、调度上线等危险动作。

## 上线检查清单

- 接口契约测试完成。
- mock 与真实 stub 的行为一致：成功、失败、超时、脱敏、审计。
- 权限矩阵已确认。
- 审批流和回滚计划已确认。
- 安全团队完成威胁建模和渗透测试。
- 生产连接配置由平台侧显式注入，并且默认关闭。
