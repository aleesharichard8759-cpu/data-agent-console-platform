# Policy Engine

Policy Engine 是 Data Governance Agent Runtime 中所有工具调用前的第一道安全闸。它不依赖 Prompt，不依赖模型自觉，也不信任工具调用方的口头约束，而是在运行时代码中强制执行 Allow / Ask / Deny 裁决。

## 为什么不能靠 Prompt 做安全控制

Prompt 只能影响模型倾向，不能形成可靠的访问控制边界：

- Prompt 可能被用户输入覆盖、诱导或提示词注入绕过。
- 模型可能误解上下文，把高风险动作当成普通查询。
- Prompt 无法证明某次工具调用经过了哪条安全规则。
- Prompt 无法保证默认拒绝、最小权限、审批和审计的一致执行。
- Prompt 无法替代可测试、可审计、可复盘的运行时控制。

因此，Data Agent 的安全必须由 Policy Engine、SQL Gateway、DLP/Masking 和 Audit 等运行时代码共同强制执行。

## Allow / Ask / Deny 模型

| 决策 | 含义 | 运行时处理 |
|---|---|---|
| `ALLOW` | 当前工具调用被策略允许 | 允许进入后续 SQL Gateway、DLP、Audit 等链路 |
| `ASK` | 当前工具调用不能自动执行，需要治理计划或审批 | 返回 ASK，不实现真实审批系统 |
| `DENY` | 当前工具调用被明确拒绝 | 立即阻断，并返回拒绝原因 |

裁决优先级：

1. 硬边界优先，如 G5 任务直接拒绝、G4 任务进入 ASK、L4/L5 数据不能进入模型上下文。
2. 匹配到多条规则时，`DENY` 优先于 `ASK`，`ASK` 优先于 `ALLOW`。
3. 同一 effect 下按 `priority` 排序，数字越小越优先。
4. 没有任何匹配规则时默认 `DENY`。
5. 策略评估异常时应 fail closed，返回 `DENY`。

## PolicyRule

`PolicyRule` 表达一条可测试的运行时策略：

| 字段 | 含义 |
|---|---|
| `rule_id` | 稳定规则编号 |
| `name` | 规则名称 |
| `description` | 规则说明 |
| `effect` | `ALLOW`、`ASK` 或 `DENY` |
| `priority` | 同一 effect 下的排序优先级 |
| `match_tool_names` | 匹配的 DataTool 名称，空表示不限 |
| `match_operations` | 匹配的操作，如 `metadata.query`、`data.detail.query` |
| `match_asset_types` | 匹配的资产类型，如 metadata、metric、table、policy |
| `match_sensitivity_levels` | 匹配的敏感等级 |
| `match_roles` | 匹配的用户角色 |
| `reason` | 命中规则后返回给调用方的原因 |

## 默认策略

当前默认策略：

| 场景 | 决策 |
|---|---|
| 查询元数据 | `ALLOW` |
| 查询指标定义 | `ALLOW` |
| 查询聚合指标 | `ALLOW` |
| 查询 L3 明细 | `DENY` |
| 查询 L4 / L5 | `DENY` |
| 创建质量规则 | `ASK` |
| 修改脱敏策略 | `ASK` |
| 删除数据 | `DENY` |
| 绕过脱敏 | `DENY` |
| 关闭审计 | `DENY` |
| 无匹配规则 | `DENY` |

## 安全边界

- 不接真实数据库。
- 不实现审批系统，只返回 `ASK`。
- 所有拒绝都必须返回 `reason`。
- L4/L5 数据永远不能进入模型上下文。
- G4 任务不能自动执行，必须进入计划/审批。
- G5 任务在策略层直接 `DENY`。
- 所有策略必须可单元测试。
