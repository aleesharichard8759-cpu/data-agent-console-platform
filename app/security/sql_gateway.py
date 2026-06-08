from __future__ import annotations

import re
from collections.abc import Mapping
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import Field

from app.domain.classification import SensitivityLevel
from app.domain.common import DomainModel
from app.domain.identity import UserContext
from app.domain.policy import PolicyDecision

if TYPE_CHECKING:
    from app.domain.tasks import GovernanceTask
    from app.domain.tools import ToolCallRequest
    from app.tools.context import AuditLogger


class SQLRiskType(StrEnum):
    SELECT_STAR = "select_star"
    NO_LIMIT = "no_limit"
    DDL_DETECTED = "ddl_detected"
    DML_DETECTED = "dml_detected"
    SENSITIVE_COLUMN = "sensitive_column"
    RAW_LAYER_ACCESS = "raw_layer_access"
    CROSS_DOMAIN_JOIN = "cross_domain_join"
    LARGE_RESULT_RISK = "large_result_risk"
    UNKNOWN_TABLE = "unknown_table"
    UNSAFE_FUNCTION = "unsafe_function"


class SQLRisk(DomainModel):
    risk_type: SQLRiskType = Field(description="Detected SQL risk type.")
    reason: str = Field(description="Human-readable risk reason.")
    target: str | None = Field(default=None, description="SQL table, column, or function target.")


class SQLReviewResult(DomainModel):
    allowed: bool = Field(description="Whether SQL may be mock-executed.")
    decision: PolicyDecision = Field(description="Gateway decision: allow, ask, or deny.")
    risks: tuple[SQLRisk, ...] = Field(default_factory=tuple, description="Detected SQL risks.")
    rewritten_sql: str | None = Field(
        default=None,
        description="Safely rewritten SQL if applicable.",
    )
    reason: str = Field(description="Gateway decision reason.")
    required_approval: bool = Field(description="Whether human approval is required.")


class SQLAssetContext(DomainModel):
    known_tables: tuple[str, ...] = Field(
        default=(
            "ads_order_summary",
            "dws_order_metric",
            "dim_product_sku",
            "ods_order_detail",
            "dwd_order_detail",
            "ods_erp_order",
            "ods_erp_order_item",
            "dwd_trade_order_detail_d",
            "dws_trade_order_sku_day",
            "ads_trade_order_dashboard_day",
            "dwd_customer_detail_d",
            "dwd_after_sale_rma_detail_d",
            "dim_product_sku",
            "dim_shop",
            "dim_warehouse",
        ),
        description="Tables known to the mock gateway.",
    )
    table_domains: dict[str, str] = Field(
        default_factory=lambda: {
            "ads_order_summary": "trade",
            "dws_order_metric": "trade",
            "ods_order_detail": "trade",
            "dwd_order_detail": "trade",
            "ods_erp_order": "trade",
            "ods_erp_order_item": "trade",
            "dwd_trade_order_detail_d": "trade",
            "dws_trade_order_sku_day": "trade",
            "ads_trade_order_dashboard_day": "trade",
            "dwd_customer_detail_d": "customer",
            "dwd_after_sale_rma_detail_d": "after_sale",
            "dim_product_sku": "product",
            "dim_shop": "organization",
            "dim_warehouse": "inventory",
        },
        description="Table to data-domain mapping.",
    )
    column_sensitivity: dict[str, SensitivityLevel] = Field(
        default_factory=lambda: {
            "api_key": SensitivityLevel.L5,
            "customer_phone": SensitivityLevel.L3,
            "customer_email": SensitivityLevel.L3,
            "shipping_address": SensitivityLevel.L3,
            "customer_address": SensitivityLevel.L3,
            "gross_profit": SensitivityLevel.L3,
            "password": SensitivityLevel.L5,
            "secret_token": SensitivityLevel.L5,
        },
        description="Column sensitivity map.",
    )


class SQLGateway:
    """SQL safety reviewer and mock executor gate. It never connects to a database."""

    _ddl_pattern = re.compile(r"\b(drop|alter|truncate|create)\b", re.IGNORECASE)
    _dml_pattern = re.compile(r"\b(insert|update|delete|merge)\b", re.IGNORECASE)
    _unsafe_function_pattern = re.compile(
        r"\b(load_file|sleep|benchmark|into\s+outfile|xp_cmdshell)\b",
        re.IGNORECASE,
    )
    _limit_pattern = re.compile(r"\blimit\s+\d+\b", re.IGNORECASE)
    _large_limit_pattern = re.compile(r"\blimit\s+(\d+)\b", re.IGNORECASE)
    _table_pattern = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][\w.]*)(?:\s+\w+)?", re.IGNORECASE)
    _aggregate_pattern = re.compile(r"\b(count|sum|avg|min|max)\s*\(", re.IGNORECASE)

    def review_sql(
        self,
        sql: str,
        user_context: UserContext,
        asset_context: SQLAssetContext | Mapping[str, Any] | None = None,
        audit_logger: AuditLogger | None = None,
        request: ToolCallRequest | None = None,
        task: GovernanceTask | None = None,
        session_id: str | None = None,
        agent_name: str | None = None,
        tool_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SQLReviewResult:
        context = self._normalize_asset_context(asset_context)
        risks = self.detect_risks(sql, context)

        deny_risks = {
            SQLRiskType.SELECT_STAR,
            SQLRiskType.DDL_DETECTED,
            SQLRiskType.DML_DETECTED,
            SQLRiskType.SENSITIVE_COLUMN,
            SQLRiskType.UNSAFE_FUNCTION,
        }
        ask_risks = {
            SQLRiskType.NO_LIMIT,
            SQLRiskType.RAW_LAYER_ACCESS,
            SQLRiskType.CROSS_DOMAIN_JOIN,
            SQLRiskType.LARGE_RESULT_RISK,
            SQLRiskType.UNKNOWN_TABLE,
        }

        if any(risk.risk_type in deny_risks for risk in risks):
            return self._audited_review(
                SQLReviewResult(
                    allowed=False,
                    decision=PolicyDecision.DENY,
                    risks=tuple(risks),
                    rewritten_sql=None,
                    reason=self._join_reasons(risks, deny_risks),
                    required_approval=False,
                ),
                sql,
                user_context,
                audit_logger,
                request,
                task,
                session_id,
                agent_name,
                tool_name,
                metadata,
            )

        if any(risk.risk_type in ask_risks for risk in risks):
            if self._can_auto_limit(sql, risks):
                return self._audited_review(
                    SQLReviewResult(
                        allowed=True,
                        decision=PolicyDecision.ALLOW,
                        risks=tuple(risks),
                        rewritten_sql=self.rewrite_sql_with_limit(sql),
                        reason="Low-risk SELECT was rewritten with LIMIT 100.",
                        required_approval=False,
                    ),
                    sql,
                    user_context,
                    audit_logger,
                    request,
                    task,
                    session_id,
                    agent_name,
                    tool_name,
                    metadata,
                )
            return self._audited_review(
                SQLReviewResult(
                    allowed=False,
                    decision=PolicyDecision.ASK,
                    risks=tuple(risks),
                    rewritten_sql=None,
                    reason=self._join_reasons(risks, ask_risks),
                    required_approval=True,
                ),
                sql,
                user_context,
                audit_logger,
                request,
                task,
                session_id,
                agent_name,
                tool_name,
                metadata,
            )

        return self._audited_review(
            SQLReviewResult(
                allowed=True,
                decision=PolicyDecision.ALLOW,
                risks=tuple(),
                rewritten_sql=sql.strip(),
                reason="SQL passed gateway review.",
                required_approval=False,
            ),
            sql,
            user_context,
            audit_logger,
            request,
            task,
            session_id,
            agent_name,
            tool_name,
            metadata,
        )

    def rewrite_sql_with_limit(self, sql: str, default_limit: int = 100) -> str:
        cleaned = sql.strip().rstrip(";")
        if self._limit_pattern.search(cleaned):
            return cleaned
        return f"{cleaned} LIMIT {default_limit}"

    def detect_tables(self, sql: str) -> tuple[str, ...]:
        tables = []
        for match in self._table_pattern.finditer(sql):
            table = match.group(1).split(".")[-1].lower()
            if table not in tables:
                tables.append(table)
        return tuple(tables)

    def detect_columns(self, sql: str) -> tuple[str, ...]:
        match = re.search(
            r"\bselect\b(?P<select>.*?)\bfrom\b",
            sql,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match is None:
            return tuple()
        columns: list[str] = []
        for raw_column in match.group("select").split(","):
            column = raw_column.strip()
            column = re.sub(r"\bas\b\s+\w+$", "", column, flags=re.IGNORECASE).strip()
            column = column.split(".")[-1].strip()
            column = re.sub(r"\W+$", "", column)
            if column and column not in columns:
                columns.append(column.lower())
        return tuple(columns)

    def detect_risks(
        self,
        sql: str,
        asset_context: SQLAssetContext | Mapping[str, Any] | None = None,
    ) -> tuple[SQLRisk, ...]:
        context = self._normalize_asset_context(asset_context)
        normalized = sql.strip()
        lowered = normalized.lower()
        risks: list[SQLRisk] = []

        if self._ddl_pattern.search(lowered):
            risks.append(
                SQLRisk(
                    risk_type=SQLRiskType.DDL_DETECTED,
                    reason="DDL statements are not allowed through SQL Gateway.",
                )
            )
        if self._dml_pattern.search(lowered):
            risks.append(
                SQLRisk(
                    risk_type=SQLRiskType.DML_DETECTED,
                    reason="DML statements are not allowed through SQL Gateway.",
                )
            )
        if re.search(r"\bselect\s+\*", lowered):
            risks.append(
                SQLRisk(
                    risk_type=SQLRiskType.SELECT_STAR,
                    reason="SELECT * is denied because it may expose unnecessary fields.",
                )
            )
        unsafe_function = self._unsafe_function_pattern.search(lowered)
        if unsafe_function is not None:
            risks.append(
                SQLRisk(
                    risk_type=SQLRiskType.UNSAFE_FUNCTION,
                    reason="Unsafe SQL function or file operation detected.",
                    target=unsafe_function.group(1),
                )
            )

        tables = self.detect_tables(sql)
        columns = self.detect_columns(sql)
        risks.extend(self._table_risks(tables, context))
        risks.extend(self._column_risks(columns, context))

        if self._is_select(lowered) and not self._limit_pattern.search(lowered):
            risks.append(
                SQLRisk(
                    risk_type=SQLRiskType.NO_LIMIT,
                    reason="SELECT query has no LIMIT.",
                )
            )
        limit_match = self._large_limit_pattern.search(lowered)
        if limit_match is not None and int(limit_match.group(1)) > 10000:
            risks.append(
                SQLRisk(
                    risk_type=SQLRiskType.LARGE_RESULT_RISK,
                    reason="LIMIT is too large and may create a large result risk.",
                    target=limit_match.group(1),
                )
            )
        if self._has_cross_domain_join(tables, context):
            risks.append(
                SQLRisk(
                    risk_type=SQLRiskType.CROSS_DOMAIN_JOIN,
                    reason="Cross-domain JOIN requires governance approval.",
                    target=", ".join(tables),
                )
            )
        return tuple(risks)

    def _table_risks(self, tables: tuple[str, ...], context: SQLAssetContext) -> list[SQLRisk]:
        risks: list[SQLRisk] = []
        known_tables = set(context.known_tables)
        for table in tables:
            if table not in known_tables:
                risks.append(
                    SQLRisk(
                        risk_type=SQLRiskType.UNKNOWN_TABLE,
                        reason=f"Unknown table requires review: {table}.",
                        target=table,
                    )
                )
            if table.startswith("ods_"):
                risks.append(
                    SQLRisk(
                        risk_type=SQLRiskType.RAW_LAYER_ACCESS,
                        reason=f"ODS raw-layer access requires approval: {table}.",
                        target=table,
                    )
                )
        return risks

    def _column_risks(self, columns: tuple[str, ...], context: SQLAssetContext) -> list[SQLRisk]:
        risks: list[SQLRisk] = []
        sensitive_tokens = (
            "phone",
            "email",
            "address",
            "id_card",
            "secret",
            "token",
            "api_key",
            "password",
        )
        for column in columns:
            level = context.column_sensitivity.get(column)
            is_sensitive_name = any(token in column for token in sensitive_tokens)
            if is_sensitive_name or level in {
                SensitivityLevel.L3,
                SensitivityLevel.L4,
                SensitivityLevel.L5,
            }:
                risks.append(
                    SQLRisk(
                        risk_type=SQLRiskType.SENSITIVE_COLUMN,
                        reason=f"Sensitive column is denied: {column}.",
                        target=column,
                    )
                )
        return risks

    def _has_cross_domain_join(self, tables: tuple[str, ...], context: SQLAssetContext) -> bool:
        if len(tables) < 2:
            return False
        domains = {context.table_domains.get(table, "unknown") for table in tables}
        return len(domains) > 1

    def _can_auto_limit(self, sql: str, risks: tuple[SQLRisk, ...]) -> bool:
        risk_types = {risk.risk_type for risk in risks}
        if risk_types != {SQLRiskType.NO_LIMIT}:
            return False
        tables = self.detect_tables(sql)
        if all(table.startswith(("ads_", "dws_")) for table in tables):
            return True
        return bool(self._aggregate_pattern.search(sql))

    @staticmethod
    def _is_select(lowered_sql: str) -> bool:
        return lowered_sql.startswith("select") or lowered_sql.startswith("with")

    @staticmethod
    def _join_reasons(risks: tuple[SQLRisk, ...], risk_types: set[SQLRiskType]) -> str:
        reasons = [risk.reason for risk in risks if risk.risk_type in risk_types]
        return " ".join(reasons) if reasons else "SQL requires review."

    @staticmethod
    def _audited_review(
        review: SQLReviewResult,
        sql: str,
        user_context: UserContext,
        audit_logger: AuditLogger | None,
        request: ToolCallRequest | None,
        task: GovernanceTask | None,
        session_id: str | None,
        agent_name: str | None,
        tool_name: str | None,
        metadata: dict[str, Any] | None,
    ) -> SQLReviewResult:
        if audit_logger is not None:
            audit_logger.record_sql_review(
                sql=sql,
                user=user_context,
                decision=review.decision,
                reason=review.reason,
                risks=review.risks,
                request=request,
                task=task,
                session_id=session_id,
                agent_name=agent_name,
                tool_name=tool_name,
                metadata=metadata,
            )
        return review

    @staticmethod
    def _normalize_asset_context(
        asset_context: SQLAssetContext | Mapping[str, Any] | None,
    ) -> SQLAssetContext:
        if asset_context is None:
            return SQLAssetContext()
        if isinstance(asset_context, SQLAssetContext):
            return asset_context
        return SQLAssetContext.model_validate(asset_context)
