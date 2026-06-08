from __future__ import annotations

from app.domain.assets import DataDomain
from app.domain.classification import SensitivityLevel

MOCK_DOMAINS: dict[str, dict[str, str]] = {
    "order_domain": {"name": "Order Domain", "domain": DataDomain.TRADE.value},
    "product_domain": {"name": "Product Domain", "domain": DataDomain.PRODUCT.value},
    "inventory_domain": {"name": "Inventory Domain", "domain": DataDomain.INVENTORY.value},
    "customer_domain": {"name": "Customer Domain", "domain": DataDomain.CUSTOMER.value},
    "after_sale_domain": {"name": "After Sale Domain", "domain": DataDomain.UNKNOWN.value},
}

FIELD_SENSITIVITY: dict[str, SensitivityLevel] = {
    "customer_phone": SensitivityLevel.L3,
    "customer_email": SensitivityLevel.L3,
    "shipping_address": SensitivityLevel.L3,
    "gross_profit": SensitivityLevel.L3,
    "token": SensitivityLevel.L5,
    "api_key": SensitivityLevel.L5,
    "password": SensitivityLevel.L5,
}

DEFAULT_FIELD_COMMENTS: dict[str, str] = {
    "order_id": "Order business identifier.",
    "sku_id": "Product SKU identifier.",
    "customer_id": "Customer surrogate identifier.",
    "customer_phone": "Masked customer contact phone field.",
    "customer_email": "Masked customer contact email field.",
    "shipping_address": "Masked shipping address field.",
    "order_amount": "Order paid amount.",
    "gross_profit": "Gross profit amount.",
    "order_status": "Order lifecycle status.",
    "rma_id": "After-sale RMA identifier.",
    "rma_reason": "After-sale RMA reason.",
    "warehouse_id": "Warehouse identifier.",
}

TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "ods_erp_order": (
        "order_id",
        "customer_id",
        "customer_phone",
        "customer_email",
        "shipping_address",
        "order_amount",
        "order_status",
    ),
    "ods_erp_order_item": ("order_id", "sku_id", "order_amount", "order_status"),
    "dwd_trade_order_detail_d": (
        "order_id",
        "sku_id",
        "customer_id",
        "order_amount",
        "gross_profit",
        "order_status",
        "warehouse_id",
    ),
    "dws_trade_order_sku_day": (
        "sku_id",
        "order_amount",
        "gross_profit",
        "warehouse_id",
    ),
    "ads_trade_order_dashboard_day": (
        "order_amount",
        "gross_profit",
        "order_status",
    ),
    "dwd_customer_detail_d": (
        "customer_id",
        "customer_phone",
        "customer_email",
        "shipping_address",
    ),
    "dwd_after_sale_rma_detail_d": (
        "rma_id",
        "order_id",
        "sku_id",
        "rma_reason",
        "customer_id",
    ),
    "dim_product_sku": ("sku_id",),
    "dim_shop": ("warehouse_id",),
    "dim_warehouse": ("warehouse_id",),
}

TABLE_METADATA: dict[str, dict[str, object]] = {
    "ods_erp_order": {
        "domain": "order_domain",
        "layer": "ods",
        "owner": None,
        "description": "Mock raw ERP order table.",
    },
    "ods_erp_order_item": {
        "domain": "order_domain",
        "layer": "ods",
        "owner": "data_engineer",
        "description": "Mock raw ERP order item table.",
    },
    "dwd_trade_order_detail_d": {
        "domain": "order_domain",
        "layer": "dwd",
        "owner": "trade_data_owner",
        "description": "Mock governed order detail table.",
    },
    "dws_trade_order_sku_day": {
        "domain": "order_domain",
        "layer": "dws",
        "owner": "trade_data_owner",
        "description": "Mock SKU-day order summary table.",
    },
    "ads_trade_order_dashboard_day": {
        "domain": "order_domain",
        "layer": "ads",
        "owner": "analytics_owner",
        "description": "Mock order dashboard aggregate table.",
    },
    "dwd_customer_detail_d": {
        "domain": "customer_domain",
        "layer": "dwd",
        "owner": "customer_data_owner",
        "description": "Mock governed customer detail table with masked contact fields.",
    },
    "dwd_after_sale_rma_detail_d": {
        "domain": "after_sale_domain",
        "layer": "dwd",
        "owner": None,
        "description": "Mock after-sale RMA detail table.",
    },
    "dim_product_sku": {
        "domain": "product_domain",
        "layer": "dim",
        "owner": "product_data_owner",
        "description": "Mock product SKU dimension.",
    },
    "dim_shop": {
        "domain": "product_domain",
        "layer": "dim",
        "owner": "operations_owner",
        "description": "Mock shop dimension.",
    },
    "dim_warehouse": {
        "domain": "inventory_domain",
        "layer": "dim",
        "owner": "inventory_owner",
        "description": "Mock warehouse dimension.",
    },
}

MISSING_COMMENTS: dict[str, tuple[str, ...]] = {
    "ods_erp_order": ("order_status",),
    "dwd_trade_order_detail_d": ("gross_profit",),
    "dwd_after_sale_rma_detail_d": ("rma_reason",),
}

DUPLICATE_CANDIDATES: dict[str, tuple[str, ...]] = {
    "ods_erp_order": ("ods_erp_order_legacy_candidate",),
}

LINEAGE: dict[str, tuple[str, ...]] = {
    "ods_erp_order": ("dwd_trade_order_detail_d",),
    "ods_erp_order_item": ("dwd_trade_order_detail_d",),
    "dwd_trade_order_detail_d": ("dws_trade_order_sku_day", "ads_trade_order_dashboard_day"),
    "dws_trade_order_sku_day": ("ads_trade_order_dashboard_day",),
    "dwd_customer_detail_d": ("dwd_trade_order_detail_d",),
    "dwd_after_sale_rma_detail_d": ("ads_trade_order_dashboard_day",),
}


def list_tables() -> tuple[str, ...]:
    return tuple(TABLE_METADATA)


def search_metadata(query: str, limit: int = 10) -> list[dict[str, str]]:
    lowered = query.lower()
    results: list[dict[str, str]] = []
    for table_name, metadata in TABLE_METADATA.items():
        domain = str(metadata["domain"])
        haystack = " ".join((table_name, domain, str(metadata.get("description", "")))).lower()
        if lowered in haystack:
            results.append(table_summary(table_name))
    return results[:limit]


def table_summary(table_name: str) -> dict[str, str]:
    metadata = TABLE_METADATA[table_name]
    columns = TABLE_COLUMNS[table_name]
    sensitivity = max(
        (field_sensitivity(column) for column in columns),
        default=SensitivityLevel.L1,
    )
    return {
        "name": table_name,
        "asset_type": "table",
        "domain": str(metadata["domain"]),
        "layer": str(metadata["layer"]),
        "owner": str(metadata["owner"] or "missing"),
        "sensitivity_level": sensitivity.value,
    }


def get_table_metadata(table_name: str) -> dict[str, object]:
    metadata = TABLE_METADATA.get(table_name)
    if metadata is None:
        return {
            "table_name": table_name,
            "columns": [],
            "missing_owner_tables": [table_name],
            "missing_comment_fields": [],
            "duplicate_table_candidates": [],
            "completion_suggestions": ["Confirm whether the table should be onboarded."],
        }
    columns = [column_metadata(table_name, column) for column in TABLE_COLUMNS[table_name]]
    missing_owner = [table_name] if metadata.get("owner") is None else []
    missing_comments = list(MISSING_COMMENTS.get(table_name, ()))
    duplicate_candidates = list(DUPLICATE_CANDIDATES.get(table_name, ()))
    return {
        "table_name": table_name,
        "domain": metadata["domain"],
        "layer": metadata["layer"],
        "owner": metadata.get("owner") or "missing",
        "description": metadata["description"],
        "columns": columns,
        "missing_owner_tables": missing_owner,
        "missing_comment_fields": missing_comments,
        "duplicate_table_candidates": duplicate_candidates,
        "completion_suggestions": metadata_completion_suggestions(
            table_name,
            missing_owner,
            missing_comments,
            duplicate_candidates,
        ),
    }


def column_metadata(table_name: str, column_name: str) -> dict[str, str | bool]:
    comment = (
        ""
        if column_name in MISSING_COMMENTS.get(table_name, ())
        else column_comment(column_name)
    )
    sensitivity = field_sensitivity(column_name)
    return {
        "table_name": table_name,
        "column_name": column_name,
        "comment": comment,
        "sensitivity_level": sensitivity.value,
        "masking_required": sensitivity in {SensitivityLevel.L3, SensitivityLevel.L5},
    }


def field_sensitivity(column_name: str) -> SensitivityLevel:
    lowered = column_name.lower()
    if any(token in lowered for token in ("token", "api_key", "password")):
        return SensitivityLevel.L5
    return FIELD_SENSITIVITY.get(column_name, SensitivityLevel.L2)


def column_comment(column_name: str) -> str:
    return DEFAULT_FIELD_COMMENTS.get(column_name, "Mock governed column.")


def metadata_completion_suggestions(
    table_name: str,
    missing_owner_tables: list[str],
    missing_comment_fields: list[str],
    duplicate_table_candidates: list[str],
) -> list[str]:
    suggestions: list[str] = []
    if missing_owner_tables:
        suggestions.append(f"Assign owner for {table_name}.")
    if missing_comment_fields:
        suggestions.append("Complete comments for missing fields.")
    if duplicate_table_candidates:
        suggestions.append("Review duplicate table candidates before publication.")
    if not suggestions:
        suggestions.append("Metadata is complete enough for the mock demo.")
    return suggestions


def get_lineage(table_name: str) -> dict[str, object]:
    upstream = tuple(source for source, targets in LINEAGE.items() if table_name in targets)
    downstream = LINEAGE.get(table_name, tuple())
    return {
        "table_name": table_name,
        "upstream": upstream,
        "downstream": downstream,
        "impact_summary": (
            f"{table_name} has {len(upstream)} upstream and "
            f"{len(downstream)} downstream assets."
        ),
    }
