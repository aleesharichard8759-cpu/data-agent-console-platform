from __future__ import annotations

from typing import Any

from app.connectors.base import (
    ConnectorCallContext,
    ConnectorConfig,
    ConnectorKind,
    ConnectorSecurityError,
)
from app.connectors.interfaces import MetadataConnector, WarehouseConnector
from app.connectors.secrets import EnvSecretProvider
from app.domain.policy import PolicyDecision
from app.security import SQLGateway


class StarRocksWarehouseConnector(WarehouseConnector):
    """Read-only StarRocks connector guarded by SQL Gateway and secret_ref."""

    def __init__(
        self,
        *,
        secret_ref: str,
        database: str | None = None,
        allowed_tables: tuple[str, ...] = (),
        max_rows: int = 100,
        timeout_seconds: float = 30.0,
        secret_provider: EnvSecretProvider | None = None,
        sql_gateway: SQLGateway | None = None,
    ) -> None:
        super().__init__(
            ConnectorConfig(
                name="starrocks_warehouse",
                connector_kind=ConnectorKind.WAREHOUSE,
                provider="starrocks",
                secret_ref=secret_ref,
                timeout_seconds=timeout_seconds,
                enabled=True,
                is_mock=False,
            )
        )
        self._database = database
        self._allowed_tables = tuple(table.lower() for table in allowed_tables)
        self._max_rows = max_rows
        self._secret_provider = secret_provider or EnvSecretProvider()
        self._sql_gateway = sql_gateway or SQLGateway()

    def query_preview(self, sql: str, context: ConnectorCallContext) -> dict[str, Any]:
        def handler() -> dict[str, Any]:
            review = self._sql_gateway.review_sql(
                sql,
                context.user_context,
                audit_logger=context.audit_logger,
                session_id=context.session_id,
                agent_name=context.agent_name,
                tool_name=self.name,
                metadata={"connector": self.name, "provider": "starrocks"},
            )
            if review.decision != PolicyDecision.ALLOW or not review.allowed:
                return {
                    "allowed": False,
                    "decision": review.decision.value,
                    "reason": review.reason,
                    "risks": [risk.model_dump(mode="json") for risk in review.risks],
                    "columns": [],
                    "rows": [],
                    "row_count": 0,
                }
            reviewed_sql = review.rewritten_sql or sql.strip()
            return self._execute_select(reviewed_sql)

        return self._run_operation(context, "query_preview", {"sql": sql}, handler)

    def get_column_profile(
        self,
        table_name: str,
        column_name: str,
        context: ConnectorCallContext,
    ) -> dict[str, Any]:
        def handler() -> dict[str, Any]:
            if not self._is_allowed_table(table_name):
                return {
                    "table_name": table_name,
                    "column_name": column_name,
                    "allowed": False,
                    "reason": "Table is outside the configured StarRocks read-only scope.",
                }
            sql = (
                f"select count(1) as row_count, count({column_name}) as non_null_count "
                f"from {table_name} limit 1"
            )
            result = self._execute_select(sql)
            return {
                "table_name": table_name,
                "column_name": column_name,
                "allowed": True,
                "profile": result,
            }

        return self._run_operation(
            context,
            "get_column_profile",
            {"table_name": table_name, "column_name": column_name},
            handler,
        )

    def _execute_select(self, sql: str) -> dict[str, Any]:
        self._assert_allowed_tables(sql)
        credentials = self._secret_provider.resolve_starrocks(self.config.secret_ref or "")
        try:
            import pymysql
            from pymysql.cursors import DictCursor
        except ImportError as exc:
            raise RuntimeError(
                "PyMySQL is required for StarRocks connections. Install the project "
                "dependencies with `uv sync` or `pip install pymysql`."
            ) from exc

        connection = pymysql.connect(
            host=credentials.host,
            port=credentials.port,
            user=credentials.user,
            password=credentials.password.get_secret_value(),
            database=self._database or credentials.database,
            connect_timeout=credentials.connect_timeout,
            read_timeout=credentials.read_timeout,
            cursorclass=DictCursor,
            autocommit=True,
            charset="utf8mb4",
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql)
                rows = list(cursor.fetchmany(self._max_rows))
                columns = [description[0] for description in cursor.description or ()]
        finally:
            connection.close()

        return {
            "allowed": True,
            "decision": "allow",
            "reviewed_sql": sql,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "source": "starrocks",
        }

    def _assert_allowed_tables(self, sql: str) -> None:
        if not self._allowed_tables:
            return
        tables = self._sql_gateway.detect_tables(sql)
        disallowed = [table for table in tables if table.lower() not in self._allowed_tables]
        if disallowed:
            raise ConnectorSecurityError(
                "SQL references tables outside the configured StarRocks scope: "
                + ", ".join(disallowed)
            )

    def _is_allowed_table(self, table_name: str) -> bool:
        return not self._allowed_tables or table_name.lower() in self._allowed_tables


class StarRocksMetadataConnector(MetadataConnector):
    """Read-only metadata connector backed by StarRocks information_schema."""

    def __init__(
        self,
        *,
        secret_ref: str,
        database: str | None = None,
        allowed_tables: tuple[str, ...] = (),
        timeout_seconds: float = 30.0,
        secret_provider: EnvSecretProvider | None = None,
    ) -> None:
        super().__init__(
            ConnectorConfig(
                name="starrocks_metadata",
                connector_kind=ConnectorKind.METADATA,
                provider="starrocks",
                secret_ref=secret_ref,
                timeout_seconds=timeout_seconds,
                enabled=True,
                is_mock=False,
            )
        )
        self._database = database
        self._allowed_tables = tuple(table.lower() for table in allowed_tables)
        self._secret_provider = secret_provider or EnvSecretProvider()

    def search_assets(self, query: str, context: ConnectorCallContext) -> dict[str, Any]:
        def handler() -> dict[str, Any]:
            tables = self._fetch_tables(query=query, limit=50)
            return {
                "results": [
                    {
                        "name": str(table["table_name"]),
                        "qualified_name": f"{table['table_schema']}.{table['table_name']}",
                        "database": str(table["table_schema"]),
                        "type": str(table.get("table_type") or "BASE TABLE"),
                        "source": "starrocks_information_schema",
                        "column_count": str(table.get("column_count", 0)),
                        "comment": str(table.get("table_comment") or ""),
                    }
                    for table in tables
                ],
                "source": "starrocks_information_schema",
            }

        return self._run_operation(context, "search_assets", {"query": query}, handler)

    def get_table_metadata(self, table_name: str, context: ConnectorCallContext) -> dict[str, Any]:
        def handler() -> dict[str, Any]:
            normalized = self._normalize_table_name(table_name)
            if not self._is_allowed_table(normalized):
                raise ConnectorSecurityError(
                    f"Table {table_name} is outside the configured StarRocks metadata scope."
                )
            table = self._fetch_tables(query=normalized, limit=1, exact_table=normalized)
            columns = self._fetch_columns(normalized)
            missing_comment_fields = [
                str(column["column_name"])
                for column in columns
                if not str(column.get("column_comment") or "").strip()
            ]
            return {
                "table_name": normalized,
                "qualified_name": (
                    f"{table[0]['table_schema']}.{normalized}" if table else normalized
                ),
                "source": "starrocks_information_schema",
                "columns": [
                    {
                        "name": str(column["column_name"]),
                        "type": str(column.get("data_type") or ""),
                        "nullable": str(column.get("is_nullable") or "").upper() == "YES",
                        "comment": str(column.get("column_comment") or ""),
                        "missing_comment": not str(column.get("column_comment") or "").strip(),
                    }
                    for column in columns
                ],
                "missing_owner_tables": [normalized],
                "missing_comment_fields": missing_comment_fields,
                "duplicate_table_candidates": [],
                "completion_suggestions": self._completion_suggestions(
                    normalized,
                    missing_comment_fields,
                ),
            }

        return self._run_operation(
            context,
            "get_table_metadata",
            {"table_name": table_name},
            handler,
        )

    def _fetch_tables(
        self,
        *,
        query: str,
        limit: int,
        exact_table: str | None = None,
    ) -> list[dict[str, Any]]:
        schema = self._schema_name()
        where = ["table_schema = %s"]
        params: list[Any] = [schema]
        scoped_tables = self._matching_scope_tables(query)
        if scoped_tables:
            placeholders = ", ".join(["%s"] * len(scoped_tables))
            where.append(f"lower(table_name) in ({placeholders})")
            params.extend(scoped_tables)
        elif self._allowed_tables:
            return []
        elif exact_table:
            where.append("lower(table_name) = %s")
            params.append(exact_table.lower())
        elif query.strip():
            where.append("lower(table_name) like %s")
            params.append(f"%{query.strip().lower()}%")
        sql = (
            "select table_schema, table_name, table_type, table_comment "
            "from information_schema.tables "
            f"where {' and '.join(where)} "
            "order by table_name limit %s"
        )
        params.append(limit)
        tables = self._execute(sql, tuple(params))
        if not tables:
            return []
        column_counts = self._column_counts(
            tuple(str(table["table_name"]).lower() for table in tables)
        )
        for table in tables:
            table["column_count"] = column_counts.get(str(table["table_name"]).lower(), 0)
        return tables

    def _fetch_columns(self, table_name: str) -> list[dict[str, Any]]:
        return self._execute(
            "select column_name, data_type, is_nullable, column_comment "
            "from information_schema.columns "
            "where table_schema = %s and lower(table_name) = %s "
            "order by ordinal_position",
            (self._schema_name(), table_name.lower()),
        )

    def _column_counts(self, table_names: tuple[str, ...]) -> dict[str, int]:
        if not table_names:
            return {}
        placeholders = ", ".join(["%s"] * len(table_names))
        rows = self._execute(
            "select lower(table_name) as table_name, count(*) as column_count "
            "from information_schema.columns "
            f"where table_schema = %s and lower(table_name) in ({placeholders}) "
            "group by lower(table_name)",
            (self._schema_name(), *table_names),
        )
        return {str(row["table_name"]): int(row["column_count"]) for row in rows}

    def _execute(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        credentials = self._secret_provider.resolve_starrocks(self.config.secret_ref or "")
        try:
            import pymysql
            from pymysql.cursors import DictCursor
        except ImportError as exc:
            raise RuntimeError(
                "PyMySQL is required for StarRocks metadata connections. Install the project "
                "dependencies with `uv sync` or `pip install pymysql`."
            ) from exc

        connection = pymysql.connect(
            host=credentials.host,
            port=credentials.port,
            user=credentials.user,
            password=credentials.password.get_secret_value(),
            database=self._database or credentials.database,
            connect_timeout=credentials.connect_timeout,
            read_timeout=credentials.read_timeout,
            cursorclass=DictCursor,
            autocommit=True,
            charset="utf8mb4",
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return list(cursor.fetchall())
        finally:
            connection.close()

    def _schema_name(self) -> str:
        credentials = self._secret_provider.resolve_starrocks(self.config.secret_ref or "")
        schema = self._database or credentials.database
        if not schema:
            raise ConnectorSecurityError(
                "StarRocks metadata lookup requires a configured database/schema."
            )
        return schema

    def _matching_scope_tables(self, query: str) -> tuple[str, ...]:
        lowered = query.strip().lower()
        if not self._allowed_tables:
            return tuple()
        if not lowered:
            return self._allowed_tables
        return tuple(table for table in self._allowed_tables if lowered in table)

    def _is_allowed_table(self, table_name: str) -> bool:
        return not self._allowed_tables or table_name.lower() in self._allowed_tables

    @staticmethod
    def _normalize_table_name(table_name: str) -> str:
        return table_name.split(".")[-1].strip().lower()

    @staticmethod
    def _completion_suggestions(
        table_name: str,
        missing_comment_fields: list[str],
    ) -> list[str]:
        suggestions = [f"为 {table_name} 补充 owner、业务域和指标口径责任人。"]
        if missing_comment_fields:
            suggestions.append(
                f"为 {table_name} 的字段补充业务注释："
                + ", ".join(missing_comment_fields[:10])
            )
        return suggestions
