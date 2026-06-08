# Demo Walkthrough: Order Domain Governance for ChatBI

本 Demo 展示一个端到端的订单域自动化数据治理流程。输入固定为：

```text
帮我治理订单域数据，后续要支持 ChatBI 查询。
```

Demo 只使用 mock catalog、mock warehouse、mock lineage、mock approval 和 in-memory audit。
它不会连接真实数据库，不会输出真实敏感明细。

## 运行方式

```bash
UV_CACHE_DIR=.uv-cache uv run python scripts/demo_order_governance.py
```

脚本会输出 JSON 治理报告。

## 自动化流程

### 1. 创建治理任务

脚本创建 `GovernanceEngine` session，并把用户输入分类为：

- `task_type`: `data_domain_governance`
- `task_level`: `G4`
- `domain`: `trade`

G4 代表后续 ChatBI 语义层发布、脱敏策略、质量规则落地等动作需要审批。

### 2. MetadataAgent

MetadataAgent 通过 mock catalog 完成：

- 发现订单域表。
- 发现缺 Owner 表：`ods_erp_order`。
- 发现缺注释字段：如 `order_status`。
- 输出元数据补全建议。

### 3. DataQualityAgent

DataQualityAgent 通过 mock quality result 输出：

- 完整性规则。
- 唯一性规则。
- 有效性规则。
- 一致性规则。
- 强规则。
- 弱规则。
- 观察规则。

强规则可用于后续阻断，弱规则和观察规则用于告警、观察和人工确认。

### 4. MetricAgent

MetricAgent 生成四个 ChatBI 指标卡片草案：

- 订单数 `order_count`
- 销售额 `sales_amount`
- 退款率 `refund_rate`
- RMA 客诉率 `rma_complaint_rate`

每个指标卡包含：

- 业务口径。
- 技术口径。
- 维度。
- 时间字段。
- 待确认问题。

### 5. SecurityAgent

SecurityAgent 识别以下敏感字段，仅输出字段名、等级和脱敏建议：

- `customer_phone`: L3
- `customer_email`: L3
- `shipping_address`: L3
- `gross_profit`: L3

Demo 不输出手机号、邮箱、地址或毛利明细值。

### 6. Lineage Mock

脚本生成订单域到 ChatBI 的影响链路：

```text
ODS -> DWD -> DWS -> ADS -> ChatBI
```

具体链路：

```text
ods_erp_order
ods_erp_order_item
dwd_trade_order_detail_d
dws_trade_order_sku_day
ads_trade_order_dashboard_day
chatbi_order_semantic_layer
```

### 7. GovernancePlan

Demo 生成 G4 治理计划，包含：

- `affected_assets`
- `proposed_actions`
- `risk_level`
- `approval_required`
- `required_approvers`
- `allowed_tools_after_approval`
- `rollback_plan`

低风险动作会 mock 执行；高风险动作生成 mock 审批。

### 8. 最终治理报告

报告包含：

- 资产清单。
- 元数据问题。
- 质量规则建议。
- 指标口径建议。
- 敏感字段清单。
- 权限与脱敏建议。
- 需要审批的动作。
- 回滚方案。
- 审计引用。
- 生成的 eval case。

## 安全边界

- 不连接真实生产库。
- 不输出真实敏感明细。
- 敏感字段只输出字段名、等级和脱敏建议。
- 所有工具调用走 DataTool、Policy Engine 和 Audit。
- SQL 类能力仍由 SQL Gateway 控制。
- G4 高风险动作进入 mock 审批。

## 验证

```bash
UV_CACHE_DIR=.uv-cache uv run pytest tests/e2e/test_order_governance_demo.py
```

全量验证：

```bash
UV_CACHE_DIR=.uv-cache uv run pytest
UV_CACHE_DIR=.uv-cache uv run ruff check .
```
