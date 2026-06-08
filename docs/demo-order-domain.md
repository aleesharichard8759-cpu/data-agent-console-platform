# Order Domain Governance Demo

This demo runs the Data Governance Agent Runtime with mock catalog and mock warehouse data.
It does not connect to real databases and does not contain real personal information.

## Mock Domains

- `order_domain`
- `product_domain`
- `inventory_domain`
- `customer_domain`
- `after_sale_domain`

## Mock Tables

- `ods_erp_order`
- `ods_erp_order_item`
- `dwd_trade_order_detail_d`
- `dws_trade_order_sku_day`
- `ads_trade_order_dashboard_day`
- `dwd_customer_detail_d`
- `dwd_after_sale_rma_detail_d`
- `dim_product_sku`
- `dim_shop`
- `dim_warehouse`

## Mock Fields

The catalog includes order, product, customer, after-sale, and warehouse fields:

- `order_id`
- `sku_id`
- `customer_id`
- `customer_phone`
- `customer_email`
- `shipping_address`
- `order_amount`
- `gross_profit`
- `order_status`
- `rma_id`
- `rma_reason`
- `warehouse_id`

Sensitive fields are classified as:

- `customer_phone`: `L3`
- `customer_email`: `L3`
- `shipping_address`: `L3`
- `gross_profit`: `L3`
- `token` / `api_key` / `password` if present: `L5`

Mock profiles return only masked sample summaries for sensitive fields.

## Enhanced Mock Tools

- `SearchMetadataTool`: searches `mock_catalog`.
- `GetTableMetadataTool`: returns table fields and metadata issues.
- `GetColumnProfileTool`: returns null rate, unique rate, and masked sample summary.
- `GetLineageTool`: returns mock upstream and downstream assets.
- `RunQualityCheckTool`: returns mock quality rule and check results.

All tool calls still pass through DataTool, Policy Engine, Hooks, and Audit.

## Demo API

Start the app:

```bash
UV_CACHE_DIR=.uv-cache uv run uvicorn app.main:app --reload
```

Create a task:

```bash
curl -X POST http://127.0.0.1:8000/tasks \
  -H 'Content-Type: application/json' \
  -d '{"user_prompt":"请为订单域生成质量规则建议"}'
```

Run the task:

```bash
curl -X POST http://127.0.0.1:8000/tasks/{task_id}/run
```

Query task result:

```bash
curl http://127.0.0.1:8000/tasks/{task_id}
```

Query audit:

```bash
curl 'http://127.0.0.1:8000/audit?task_id={task_id}'
```

## Safety Boundary

- No real personal information is stored.
- No real database is connected.
- SQL requests still go through SQL Gateway.
- `customer_phone`, `customer_email`, `shipping_address`, and `gross_profit` detail access is denied.
- Sensitive mock profiles return masked summaries only.
- Audit events record summaries and references, not raw sensitive values.
