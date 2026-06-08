# Data Governance Agent Runtime

Data Governance Agent Runtime 是面向企业 ERP / 数仓场景的数据治理任务执行型智能体运行时骨架。

阶段 0 只创建项目结构、基础配置、FastAPI health check 和结构测试，不实现 Agent 业务逻辑，不连接真实数据库，不执行任何生产变更。

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

当前阶段不提供真实数据库连接、不保存真实密钥、不写入真实 Token、密码、手机号、邮箱或地址。未来即使接入 OpenMetadata、Doris、StarRocks、DolphinScheduler、Langfuse 或工单系统，也必须通过 connectors 模块和安全策略层进行隔离。

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

## 运行测试

```bash
uv run pytest
uv run ruff check .
```

