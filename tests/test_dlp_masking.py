from data_governance_agent_runtime.dlp.masking import DlpMasker


def test_dlp_masks_sensitive_named_fields_recursively() -> None:
    payload = {
        "asset": "dwd_customer_contact_snapshot_di",
        "profile": {
            "customer_name": "synthetic_name",
            "email_hash": "hash_placeholder",
            "safe_metric": 1,
        },
    }

    result = DlpMasker().mask(payload)

    assert result.data["profile"]["customer_name"] == "***MASKED***"
    assert result.data["profile"]["email_hash"] == "***MASKED***"
    assert result.data["profile"]["safe_metric"] == 1
    assert "profile.customer_name" in result.masked_fields
    assert "profile.email_hash" in result.masked_fields

