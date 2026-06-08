# CLI

`datagent` 是 Runtime 的轻量 mock CLI。它用于本地验证任务分类、SQL 审查、评测和审计
响应格式，不连接真实数据库，也不读取真实数据源。

## 安装入口

项目通过 `pyproject.toml` 注册脚本：

```bash
uv run datagent --help
```

也可以直接运行模块：

```bash
uv run python -m app.cli --help
```

## 命令

### datagent task

创建并运行一个 mock 治理任务。

```bash
uv run datagent task "帮我治理订单域数据"
```

输出包含 `trace_id`、`audit_refs`、`task_id`、任务类型、任务等级和治理建议。

### datagent sql-review

只审查 SQL，不执行 SQL。

```bash
uv run datagent sql-review "select * from dwd_customer_detail_d"
```

危险 SQL 会返回 `decision=deny` 和明确风险原因。

### datagent eval run

运行默认 Evaluation Case 套件。

```bash
uv run datagent eval run
```

### datagent audit

查看 CLI 当前进程内的 mock 审计视图。

```bash
uv run datagent audit --task-id xxx
```

当前 MVP 的 CLI 不持久化跨进程运行状态；正在运行的 API 任务审计请使用：

```bash
GET /tasks/{task_id}/audit
```

## 安全边界

- CLI 只使用 mock runtime。
- SQL review 不执行 SQL。
- CLI 输出不包含敏感原始结果集。
- 每个命令输出都包含 `trace_id` 或 `audit_refs`。
