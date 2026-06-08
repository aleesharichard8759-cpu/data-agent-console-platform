from data_governance_agent_runtime.core.enums import SqlStatementType
from data_governance_agent_runtime.core.models import SqlRequest
from data_governance_agent_runtime.sql.gateway import SqlGateway


def test_sql_gateway_allows_only_mock_select_execution() -> None:
    gateway = SqlGateway()

    result = gateway.execute(
        SqlRequest(statement="select asset_name from governed_catalog", purpose="test")
    )

    assert result.statement_type == SqlStatementType.SELECT
    assert result.row_count == 2
    assert result.rows[1]["email_hash"] == "***MASKED***"


def test_sql_gateway_blocks_mutation_execution() -> None:
    gateway = SqlGateway()

    result = gateway.execute(SqlRequest(statement="delete from governed_catalog", purpose="test"))

    assert result.statement_type == SqlStatementType.MUTATION
    assert result.row_count == 0
    assert result.rows == []


def test_sql_gateway_blocks_ddl_execution() -> None:
    gateway = SqlGateway()

    result = gateway.execute(SqlRequest(statement="drop table governed_catalog", purpose="test"))

    assert result.statement_type == SqlStatementType.DDL
    assert result.row_count == 0
