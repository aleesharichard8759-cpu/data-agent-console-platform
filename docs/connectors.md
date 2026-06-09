# Connectors

Connector 层用于隔离真实企业系统。当前代码已移除内置演示数据，运行态默认不再返回本地样例结果；未配置真实 Connector 时，相关工具 fail closed。

## 统一原则

- 真实凭证只能通过 `secret_ref` 引用，禁止把密码、Token、连接串明文写入配置或代码。
- 每个 Connector 必须设置 `timeout_seconds`。
- 每次调用必须写审计：成功为 `connector_called`，失败为 `connector_failed`。
- 调用失败必须 fail closed，并抛出统一 `ConnectorError` 子类。
- Connector 输出不能包含敏感原始值或大结果集。
- SQL 类访问只能位于 SQL Gateway 之后，不能绕过 Gateway 直接查库。

## 基础类型

- `ConnectorConfig`：连接器名称、类别、provider、`secret_ref`、超时时间、启用状态和兼容标记。
- `ConnectorCallContext`：调用身份、审计器、session、task、agent。
- `BaseConnector`：统一审计、脱敏、错误包装和 timeout 检查。
- `StarRocksWarehouseConnector`：真实 StarRocks 只读查询连接器。
- `UnconfiguredWarehouseConnector`：未配置真实数仓时的 fail-closed 连接器。

## StarRocks 只读连接

启用真实连接需要配置：

```bash
export DATAGENT_STARROCKS_SECRET_REF="secret://prod/starrocks/rma_ro"
export DATAGENT_SECRET_PROD_STARROCKS_RMA_RO='{"host":"starrocks-fe.example.com","port":9030,"user":"rma_ro","password":"***","database":"rma_ads"}'
export DATAGENT_STARROCKS_ALLOWED_TABLES="ads_afs_rma_multi_dim_metric_1d"
export DATAGENT_STARROCKS_MAX_ROWS="100"
export DATAGENT_STARROCKS_TIMEOUT_SECONDS="30"
```

`EnvSecretProvider` 会把 `secret_ref` 规范化成环境变量名，例如：

```text
secret://prod/starrocks/rma_ro -> DATAGENT_SECRET_PROD_STARROCKS_RMA_RO
```

该环境变量的 JSON 必须包含：

```json
{
  "host": "starrocks-fe.example.com",
  "port": 9030,
  "user": "rma_ro",
  "password": "***",
  "database": "rma_ads"
}
```

## Connector 接口

### MetadataConnector

预留 OpenMetadata / DataHub 接口。当前未配置真实元数据连接时，相关工具 fail closed。

- `search_assets()`
- `get_table_metadata()`

### WarehouseConnector

当前实现 `StarRocksWarehouseConnector`。

- `query_preview()`
- `get_column_profile()`

安全边界：不得绕过 SQL Gateway，不得返回不受控的大结果集；表访问必须在 `DATAGENT_STARROCKS_ALLOWED_TABLES` 白名单内。

### QualityConnector

预留 Great Expectations / Soda / 自研质量平台接口。当前未配置真实质量平台连接时，相关工具 fail closed。

- `generate_rule_suggestions()`
- `run_quality_check()`

### MetricConnector

预留指标平台 / 语义层接口。当前未配置真实指标平台连接时，相关工具 fail closed。

- `get_metric_definition()`
- `generate_metric_card()`

### LineageConnector

预留 OpenMetadata Lineage / Atlas / DataHub 接口。

- `get_lineage()`

### PermissionConnector

预留 IAM / Ranger / 自研权限系统接口。

- `check_permission()`

安全边界：PermissionConnector 不是 Policy Engine，不能替代运行时策略裁决。

### MaskingConnector

预留 DLP / Presidio / 自研脱敏系统接口。

- `mask_record()`

安全边界：默认只返回脱敏结果，不返回敏感原值。

### WorkflowConnector

预留 Jira / 飞书 / 钉钉 / 自研工单接口。

- `create_approval_ticket()`

### SchedulerConnector

预留 DolphinScheduler / Airflow 接口。

- `submit_dry_run_job()`

安全边界：只允许受控 dry-run，不提交生产调度任务。
