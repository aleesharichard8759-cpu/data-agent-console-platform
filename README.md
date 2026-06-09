# Data Governance Agent Runtime

Data Governance Agent Runtime 是面向企业 ERP / 数仓场景的数据治理任务执行型智能体运行时骨架。

当前版本保留 Runtime、Policy、Security、Audit、Memory、Connectors 分层结构，已移除内置演示数据，并通过只读 Connector 接入真实数仓。

## 项目目标

- 支撑自动化数据治理任务的运行时框架。
- 为后续 Multi-Agent、DataTool、Policy Engine、SQL Gateway、DLP/Masking、Audit、Memory、Evals 和外部连接器预留清晰模块边界。
- 把数据安全作为运行时默认边界，而不是业务逻辑的事后补丁。

## 架构原则

- Agentic Loop 与工具执行解耦。
- 所有外部能力统一抽象为 DataTool。
- 所有工具调用必须先经过 Policy Engine。
- 所有 SQL 必须通过 SQL Gateway，不允许 Agent 直接执行 SQL。
- 所有结果必须经过 DLP / Masking 后才能返回给 Agent 或用户。
- 高风险动作必须进入 Governance Plan Mode 和审批流程。
- Runtime、Policy、Security、Audit、Memory、Connectors 分层建设。
- 默认拒绝、最小权限、按需授权、全程审计。

## 安全边界

Agent 不直接访问生产数据。

所有数据访问必须通过：

```text
Agent -> DataTool -> Policy Engine -> SQL Gateway -> DLP/Masking -> Audit
```

当前项目支持通过 `app.connectors` 接入真实 StarRocks 只读源。未配置真实连接时，工具调用会 fail closed，不返回内置样例结果。项目仍不保存真实密钥、Token、密码、手机号、邮箱或地址；所有凭证只能通过 `secret_ref` 引用，并由运行环境注入。

## 目录结构

```text
app/
  main.py
  core/
  domain/
  policy/
  tools/
  hooks/
  agents/
  runtime/
  security/
  audit/
  memory/
  evals/
  connectors/
docs/
tests/
```

## 运行项目

```bash
uv run uvicorn app.main:create_app --factory --reload
```

访问：

```bash
curl http://127.0.0.1:8000/health
```

返回：

```json
{"status":"ok"}
```

## 连接真实 StarRocks

真实连接由环境变量启用。`secret_ref` 是凭证引用，不是密码明文；代码会把 `secret://prod/starrocks/rma_ro` 规范化为 `DATAGENT_SECRET_PROD_STARROCKS_RMA_RO` 并读取其中的 JSON。

```bash
export DATAGENT_STARROCKS_SECRET_REF="secret://prod/starrocks/rma_ro"
export DATAGENT_SECRET_PROD_STARROCKS_RMA_RO='{"host":"starrocks-fe.example.com","port":9030,"user":"rma_ro","password":"***","database":"rma_ads"}'
export DATAGENT_STARROCKS_ALLOWED_TABLES="ads_afs_rma_multi_dim_metric_1d"
export DATAGENT_STARROCKS_MAX_ROWS="100"
export DATAGENT_STARROCKS_TIMEOUT_SECONDS="30"
```

连接路径保持：

```text
Agent -> DataTool -> Policy Engine -> SQL Gateway -> StarRocksWarehouseConnector -> Audit
```

只有 SQL Gateway 返回 `ALLOW` 且表名在 `DATAGENT_STARROCKS_ALLOWED_TABLES` 白名单内时，`QuerySQLTool` 才会用只读账号查询真实库。

## 运行测试

```bash
uv run pytest
uv run ruff check .
```
