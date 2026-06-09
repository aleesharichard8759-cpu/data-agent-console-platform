from __future__ import annotations

import re
from data_governance_agent_runtime.core.enums import SqlStatementType
from data_governance_agent_runtime.core.models import SqlGatewayResult, SqlRequest


class SqlGateway:
    """SQL classifier gate. Real execution is delegated to configured connectors."""

    _mutation_pattern = re.compile(
        r"\b(insert|update|delete|merge|truncate|drop|alter|create|grant|revoke)\b",
        flags=re.IGNORECASE,
    )

    def execute(self, request: SqlRequest) -> SqlGatewayResult:
        statement_type = self.classify(request.statement)
        return SqlGatewayResult(statement_type=statement_type, rows=[], row_count=0)

    def classify(self, statement: str) -> SqlStatementType:
        normalized = statement.strip().lower()
        if self._mutation_pattern.search(normalized):
            if normalized.startswith(("create", "alter", "drop", "truncate")):
                return SqlStatementType.DDL
            return SqlStatementType.MUTATION
        if normalized.startswith("select") or normalized.startswith("with"):
            return SqlStatementType.SELECT
        return SqlStatementType.UNKNOWN
