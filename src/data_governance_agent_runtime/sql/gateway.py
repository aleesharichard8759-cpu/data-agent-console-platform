from __future__ import annotations

import re
from typing import Any

from data_governance_agent_runtime.core.enums import SqlStatementType
from data_governance_agent_runtime.core.models import SqlGatewayResult, SqlRequest
from data_governance_agent_runtime.dlp.masking import DlpMasker


class SqlGateway:
    """Mock SQL Gateway. It never opens a database connection."""

    _mutation_pattern = re.compile(
        r"\b(insert|update|delete|merge|truncate|drop|alter|create|grant|revoke)\b",
        flags=re.IGNORECASE,
    )

    def __init__(self, dlp: DlpMasker | None = None) -> None:
        self._dlp = dlp or DlpMasker()

    def execute(self, request: SqlRequest) -> SqlGatewayResult:
        statement_type = self.classify(request.statement)
        if statement_type != SqlStatementType.SELECT:
            return SqlGatewayResult(statement_type=statement_type, rows=[], row_count=0)

        rows = self._mock_rows()[: request.max_rows]
        masked_rows: list[dict[str, Any]] = []
        masked_fields: list[str] = []
        for row in rows:
            masked = self._dlp.mask(row)
            masked_rows.append(masked.data)
            masked_fields.extend(masked.masked_fields)
        return SqlGatewayResult(
            statement_type=statement_type,
            rows=masked_rows,
            row_count=len(masked_rows),
            masked_fields=tuple(masked_fields),
        )

    def classify(self, statement: str) -> SqlStatementType:
        normalized = statement.strip().lower()
        if self._mutation_pattern.search(normalized):
            if normalized.startswith(("create", "alter", "drop", "truncate")):
                return SqlStatementType.DDL
            return SqlStatementType.MUTATION
        if normalized.startswith("select") or normalized.startswith("with"):
            return SqlStatementType.SELECT
        return SqlStatementType.UNKNOWN

    @staticmethod
    def _mock_rows() -> list[dict[str, Any]]:
        return [
            {
                "asset_name": "ads_governed_order_metric_1d",
                "business_domain": "trade",
                "owner": "data_steward",
                "sensitive_level": "L2",
            },
            {
                "asset_name": "dwd_customer_contact_snapshot_di",
                "business_domain": "customer",
                "owner": "data_steward",
                "email_hash": "hash_placeholder",
                "sensitive_level": "L3",
            },
        ]

