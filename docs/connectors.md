# Connectors

Connector 层用于隔离真实企业系统。当前阶段只实现 mock / stub，不连接生产系统，
不读取环境变量里的生产连接，不保存真实密钥、Token、手机号、邮箱、地址或数据库密码。

## 统一原则

- 默认禁用真实连接，真实 Connector 只能留 TODO 和接口。
- 每个 Connector 必须设置 `timeout_seconds`。
- 每次调用必须写审计：成功为 `connector_called`，失败为 `connector_failed`。
- 调用失败必须 fail closed，并抛出统一 `ConnectorError` 子类。
- Connector 输出不能包含敏感原始值或大结果集。
- SQL 类访问未来也只能位于 SQL Gateway 之后，不能绕过 Gateway 直接查库。

## 基础类型

- `ConnectorConfig`：连接器名称、类别、超时时间、是否启用、是否 mock。
- `ConnectorCallContext`：调用身份、审计器、session、task、agent。
- `BaseConnector`：统一审计、脱敏、错误包装和 timeout 检查。
- `StubConnector`：真实系统占位类，默认抛 `ConnectorUnavailableError`。

## Connector 接口

### MetadataConnector

未来接 OpenMetadata / DataHub。

- `search_assets()`
- `get_table_metadata()`

### WarehouseConnector

未来接 Doris / StarRocks / ClickHouse / Hive。

- `query_preview()`
- `get_column_profile()`

安全边界：不得绕过 SQL Gateway，不得返回原始明细。

### QualityConnector

未来接 Great Expectations / Soda / 自研质量平台。

- `generate_rule_suggestions()`
- `run_quality_check()`

### MetricConnector

未来接指标平台 / 语义层。

- `get_metric_definition()`
- `generate_metric_card()`

### LineageConnector

未来接 OpenMetadata Lineage / Atlas / DataHub。

- `get_lineage()`

### PermissionConnector

未来接 IAM / Ranger / 自研权限系统。

- `check_permission()`

安全边界：PermissionConnector 不是 Policy Engine，不能替代运行时策略裁决。

### MaskingConnector

未来接 DLP / Presidio / 自研脱敏系统。

- `mask_record()`

安全边界：默认只返回脱敏结果，不返回敏感原值。

### WorkflowConnector

未来接 Jira / 飞书 / 钉钉 / 自研工单。

- `create_approval_ticket()`

### SchedulerConnector

未来接 DolphinScheduler / Airflow。

- `submit_dry_run_job()`

安全边界：当前只允许 dry-run，不提交真实调度任务。

## Mock 实现

当前提供：

- `MockMetadataConnector`
- `MockWarehouseConnector`
- `MockQualityConnector`
- `MockMetricConnector`
- `MockLineageConnector`
- `MockPermissionConnector`
- `MockMaskingConnector`
- `MockWorkflowConnector`
- `MockSchedulerConnector`

统一入口：

```python
from app.connectors import build_mock_connectors

connectors = build_mock_connectors()
```

## 真实 Stub

当前仅提供不可用占位类：

- `OpenMetadataConnector`
- `WarehouseEngineConnector`
- `QualityPlatformConnector`
- `MetricPlatformConnector`
- `AtlasLineageConnector`
- `IAMPermissionConnector`
- `DLPMaskingConnector`
- `TicketWorkflowConnector`
- `WorkflowSchedulerConnector`

这些类默认 `enabled=false`、`is_mock=false`，调用会抛 `ConnectorUnavailableError` 并写审计。
