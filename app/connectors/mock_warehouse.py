from __future__ import annotations

from app.connectors.mock_catalog import field_sensitivity
from app.domain.classification import SensitivityLevel

QUALITY_RESULTS: dict[str, dict[str, object]] = {
    "ods_erp_order": {
        "row_count": 1200,
        "failed_checks": 3,
        "completeness_rules": ["order_id must not be null", "customer_id should not be null"],
        "uniqueness_rules": ["order_id should be unique"],
        "validity_rules": ["order_status should be in governed status enum"],
        "consistency_rules": ["order_amount should be non-negative"],
        "strong_rules": ["order_id not null", "order_id unique"],
        "weak_rules": ["status distribution drift warning"],
    },
    "dwd_trade_order_detail_d": {
        "row_count": 1180,
        "failed_checks": 1,
        "completeness_rules": ["order_id must not be null", "sku_id must not be null"],
        "uniqueness_rules": ["order_id + sku_id should be unique by day"],
        "validity_rules": ["gross_profit should be within governed threshold"],
        "consistency_rules": ["detail amount should reconcile to order amount"],
        "strong_rules": ["order_id not null", "partition freshness"],
        "weak_rules": ["gross profit range warning"],
    },
}


def get_column_profile(table_name: str, column_name: str) -> dict[str, object]:
    level = field_sensitivity(column_name)
    sensitive = level in {SensitivityLevel.L3, SensitivityLevel.L4, SensitivityLevel.L5}
    return {
        "table_name": table_name,
        "column_name": column_name,
        "null_rate": 0.0 if column_name.endswith("_id") else 0.02,
        "unique_rate": 0.98 if column_name.endswith("_id") else 0.42,
        "sample_summary": "***MASKED***" if sensitive else f"mock_pattern:{column_name}",
        "sample_values_returned": not sensitive,
        "sensitivity_level": level.value,
        "masking_applied": sensitive,
    }


def run_quality_check(table_name: str) -> dict[str, object]:
    default = {
        "row_count": 100,
        "failed_checks": 0,
        "completeness_rules": [f"{table_name}.primary_key should not be null"],
        "uniqueness_rules": [f"{table_name}.primary_key should be unique"],
        "validity_rules": ["numeric fields should remain in governed ranges"],
        "consistency_rules": ["dimension references should be valid"],
        "strong_rules": ["primary key not null"],
        "weak_rules": ["distribution drift warning"],
    }
    return {"table_name": table_name, **QUALITY_RESULTS.get(table_name, default)}
