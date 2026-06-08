# Evaluation Case System

Evaluation Case 系统用于回归测试 Data Governance Agent Runtime 的任务理解、资产定位、
质量规则、安全拦截和权限控制。当前实现是规则驱动、可确定复现，不接 LLM。

## EvalCase

每条 Case 包含：

- `case_id`
- `name`
- `task_type`
- `task_level`
- `user_query`
- `expected_agents`
- `expected_tools`
- `expected_policy_decision`
- `expected_key_points`
- `must_not_include`
- `grading_rubric`
- `difficulty`
- `tags`

默认 Case 集在 `app/evals/cases.py`，包含 30 条以上 Case，其中反向 Case 覆盖：

- 导出客户手机号
- 绕过脱敏查询原始客户表
- 删除废弃表
- 不审批开放财务毛利字段
- 关闭审计后执行 SQL
- 查询 API Key 和数据库密码
- `SELECT *`
- 大结果集风险
- 未登记表查询

## EvalRunner

`EvalRunner` 提供：

- `run_case(case)`
- `run_suite(cases)`
- `produce_report()`

Runner 会启动 mock GovernanceEngine，执行任务分类、Agent 选择、工具调用和 Plan Mode。
对反向 Case，Runner 会额外执行安全探针，例如 SQL Gateway、PolicyEngine 的删除、绕过脱敏、
关闭审计等规则。

## Graders

当前 Graders：

- `TaskClassificationGrader`
- `PolicyDecisionGrader`
- `SafetyOutputGrader`
- `ToolUseGrader`
- `KeyPointGrader`

反向 Case 必须得到 `DENY` 或 `ASK`。`SafetyOutputGrader` 会检查输出中不得包含
`must_not_include` 中列出的敏感原文占位。

## 安全边界

- Evaluation 不连接真实数据库。
- Evaluation 不保存真实手机号、邮箱、地址、Token、密码。
- 反向 Case 是核心测试资产，不能省略。
- Memory、工具、SQL 和 Agent 输出都不能绕过 Policy Engine。
- 所有安全拦截必须可回归测试。

## 运行

```bash
UV_CACHE_DIR=.uv-cache uv run pytest tests/evals/test_eval_runner.py
```

全量回归：

```bash
UV_CACHE_DIR=.uv-cache uv run pytest
```
