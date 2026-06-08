from app.domain import PolicyDecision
from app.domain.identity import UserContext, UserRole
from app.security import SQLGateway, SQLRiskType


def make_user() -> UserContext:
    return UserContext(
        user_id="sql_user",
        display_name="SQL User",
        roles=(UserRole.DATA_STEWARD,),
    )


def risk_types(sql: str) -> set[SQLRiskType]:
    return {risk.risk_type for risk in SQLGateway().detect_risks(sql)}


def test_select_star_is_denied() -> None:
    result = SQLGateway().review_sql("select * from ads_order_summary", make_user())

    assert result.decision == PolicyDecision.DENY
    assert result.allowed is False
    assert SQLRiskType.SELECT_STAR in {risk.risk_type for risk in result.risks}
    assert "SELECT *" in result.reason


def test_drop_table_is_denied() -> None:
    result = SQLGateway().review_sql("drop table ads_order_summary", make_user())

    assert result.decision == PolicyDecision.DENY
    assert SQLRiskType.DDL_DETECTED in {risk.risk_type for risk in result.risks}
    assert result.reason


def test_delete_is_denied() -> None:
    result = SQLGateway().review_sql("delete from ads_order_summary", make_user())

    assert result.decision == PolicyDecision.DENY
    assert SQLRiskType.DML_DETECTED in {risk.risk_type for risk in result.risks}
    assert result.reason


def test_no_limit_low_risk_query_is_rewritten() -> None:
    result = SQLGateway().review_sql(
        "select order_count from ads_order_summary",
        make_user(),
    )

    assert result.decision == PolicyDecision.ALLOW
    assert result.allowed is True
    assert result.rewritten_sql == "select order_count from ads_order_summary LIMIT 100"
    assert SQLRiskType.NO_LIMIT in {risk.risk_type for risk in result.risks}


def test_customer_phone_query_is_denied() -> None:
    result = SQLGateway().review_sql(
        "select customer_phone from ads_order_summary limit 10",
        make_user(),
    )

    assert result.decision == PolicyDecision.DENY
    assert SQLRiskType.SENSITIVE_COLUMN in {risk.risk_type for risk in result.risks}
    assert "customer_phone" in result.reason


def test_ads_order_summary_aggregate_is_allowed() -> None:
    result = SQLGateway().review_sql(
        "select order_count from ads_order_summary limit 10",
        make_user(),
    )

    assert result.decision == PolicyDecision.ALLOW
    assert result.allowed is True
    assert result.risks == ()


def test_ods_raw_layer_access_requires_approval() -> None:
    result = SQLGateway().review_sql(
        "select order_id from ods_order_detail limit 10",
        make_user(),
    )

    assert result.decision == PolicyDecision.ASK
    assert result.required_approval is True
    assert SQLRiskType.RAW_LAYER_ACCESS in {risk.risk_type for risk in result.risks}


def test_detect_tables_and_columns() -> None:
    gateway = SQLGateway()

    assert gateway.detect_tables(
        "select s.order_count from ads_order_summary s join dim_product_sku p on s.sku=p.sku"
    ) == ("ads_order_summary", "dim_product_sku")
    assert gateway.detect_columns("select order_count, sku from ads_order_summary") == (
        "order_count",
        "sku",
    )

