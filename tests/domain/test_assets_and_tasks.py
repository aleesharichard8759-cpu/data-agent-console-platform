import pytest
from pydantic import ValidationError

from app.domain import (
    AssetOwner,
    DataDomain,
    GovernanceTask,
    GovernanceTaskLevel,
    GovernanceTaskStatus,
    GovernanceTaskType,
    SensitivityLevel,
    TableAsset,
)


def test_table_asset_serialization_round_trip() -> None:
    owner = AssetOwner(owner_id="owner_001", name="Data Steward", role="data_steward")
    table = TableAsset(
        name="ads_order_quality_1d",
        qualified_name="mock.ads.ads_order_quality_1d",
        domain=DataDomain.TRADE,
        owner=owner,
        sensitivity_level=SensitivityLevel.L2,
        database="mock_dw",
        table_name="ads_order_quality_1d",
        allow_in_model_context=True,
    )

    restored = TableAsset.model_validate_json(table.model_dump_json())

    assert restored.domain == DataDomain.TRADE
    assert restored.owner is not None
    assert restored.owner.role == "data_steward"


def test_l5_production_asset_cannot_enter_model_context() -> None:
    with pytest.raises(ValidationError):
        TableAsset(
            name="dwd_order_secret_di",
            qualified_name="prod.dwd.dwd_order_secret_di",
            domain=DataDomain.TRADE,
            sensitivity_level=SensitivityLevel.L5,
            database="prod_dw",
            table_name="dwd_order_secret_di",
            is_production=True,
            requires_approval=True,
            allow_in_model_context=True,
        )


def test_governance_task_expresses_order_domain_data_quality_task() -> None:
    table = TableAsset(
        name="ads_order_quality_1d",
        qualified_name="mock.ads.ads_order_quality_1d",
        domain=DataDomain.TRADE,
        sensitivity_level=SensitivityLevel.L2,
        database="mock_dw",
        table_name="ads_order_quality_1d",
    )
    task = GovernanceTask(
        title="订单域数据质量治理",
        task_type=GovernanceTaskType.DATA_QUALITY,
        task_level=GovernanceTaskLevel.G2,
        domain=DataDomain.TRADE,
        objective="检查订单域核心指标表的完整性、唯一性和及时性规则。",
        target_assets=(table,),
        created_by="data_steward",
        allow_in_model_context=True,
    )

    restored = GovernanceTask.model_validate_json(task.model_dump_json())

    assert restored.title == "订单域数据质量治理"
    assert restored.task_type == GovernanceTaskType.DATA_QUALITY
    assert restored.status == GovernanceTaskStatus.CREATED
    assert restored.target_assets[0].qualified_name == "mock.ads.ads_order_quality_1d"


def test_g5_task_requires_approval() -> None:
    with pytest.raises(ValidationError):
        GovernanceTask(
            title="高风险权限巡检",
            task_type=GovernanceTaskType.PERMISSION_INSPECTION,
            task_level=GovernanceTaskLevel.G5,
            domain=DataDomain.SECURITY,
            objective="检查并准备回收高敏权限。",
            created_by="security_reviewer",
        )

