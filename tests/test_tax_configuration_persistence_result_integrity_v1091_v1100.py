import json

from services.tax_configuration_service import (
    TaxConfigurationService,
)
from telegram_core_factory import create_telegram_core


def test_v1091_non_mapping_persisted_policy_fails_closed(tmp_path):
    file_path = tmp_path / "tax.json"
    file_path.write_text(
        json.dumps(["bad"]),
        encoding="utf-8",
    )

    result = TaxConfigurationService(
        file_path=str(file_path)
    ).get_policy()

    assert result == {
        "error": False,
        "configured": False,
        "policy": None,
    }


def test_v1092_non_numeric_persisted_tax_rate_fails_closed(tmp_path):
    file_path = tmp_path / "tax.json"
    file_path.write_text(
        json.dumps(
            {
                "mode": "USN_INCOME",
                "tax_rate": "not-a-number",
                "minimum_tax_rate": 1.0,
            }
        ),
        encoding="utf-8",
    )

    result = TaxConfigurationService(
        file_path=str(file_path)
    ).get_policy()

    assert result["error"] is False
    assert result["configured"] is False
    assert result["policy"] is None


def test_v1093_non_finite_persisted_rates_fail_closed(tmp_path):
    for value in (
        float("nan"),
        float("inf"),
        float("-inf"),
    ):
        file_path = tmp_path / "tax.json"
        file_path.write_text(
            json.dumps(
                {
                    "mode": "USN_INCOME",
                    "tax_rate": value,
                    "minimum_tax_rate": 1.0,
                }
            ),
            encoding="utf-8",
        )

        result = TaxConfigurationService(
            file_path=str(file_path)
        ).get_policy()

        assert result["configured"] is False
        assert result["policy"] is None


def test_v1094_out_of_range_tax_rate_is_rejected_before_write(tmp_path):
    file_path = tmp_path / "tax.json"
    service = TaxConfigurationService(
        file_path=str(file_path)
    )

    for value in (
        -0.01,
        100.01,
        True,
    ):
        result = service.save_policy(
            mode="USN_INCOME",
            tax_rate=value,
        )

        assert result["error"] is True
        assert result["message"] == "Некорректная налоговая ставка"
        assert not file_path.exists()


def test_v1095_invalid_minimum_tax_rate_is_rejected_before_write(tmp_path):
    file_path = tmp_path / "tax.json"
    service = TaxConfigurationService(
        file_path=str(file_path)
    )

    for value in (
        -1,
        101,
        False,
        "bad",
    ):
        result = service.save_policy(
            mode="USN_INCOME_MINUS_EXPENSES",
            tax_rate=15.0,
            minimum_tax_rate=value,
        )

        assert result["error"] is True
        assert result["message"] == (
            "Некорректная минимальная налоговая ставка"
        )
        assert not file_path.exists()


def test_v1096_none_mode_preserves_explicit_zero_tax_contract(tmp_path):
    file_path = tmp_path / "tax.json"
    service = TaxConfigurationService(
        file_path=str(file_path)
    )

    saved = service.save_policy(
        mode="NONE",
        tax_rate="ignored",
        minimum_tax_rate="ignored",
    )
    loaded = service.get_policy()

    expected = {
        "mode": "NONE",
        "tax_rate": 0.0,
        "minimum_tax_rate": 0.0,
    }
    assert saved["error"] is False
    assert saved["saved"] is True
    assert saved["policy"] == expected
    assert loaded == {
        "error": False,
        "configured": True,
        "policy": expected,
    }


def test_v1097_valid_policy_is_atomically_normalized_and_persisted(tmp_path):
    file_path = tmp_path / "tax.json"
    service = TaxConfigurationService(
        file_path=str(file_path)
    )

    result = service.save_policy(
        mode="usn_income_minus_expenses",
        tax_rate="15",
        minimum_tax_rate="1",
    )

    assert result == {
        "error": False,
        "saved": True,
        "atomic_replace": True,
        "policy": {
            "mode": "USN_INCOME_MINUS_EXPENSES",
            "tax_rate": 15.0,
            "minimum_tax_rate": 1.0,
        },
    }
    assert json.loads(
        file_path.read_text(encoding="utf-8")
    ) == result["policy"]
    assert list(tmp_path.glob(
        ".tax-configuration-write-*.tmp"
    )) == []


def test_v1098_failed_atomic_replace_preserves_previous_policy(
    tmp_path,
    monkeypatch,
):
    file_path = tmp_path / "tax.json"
    service = TaxConfigurationService(
        file_path=str(file_path)
    )
    first = service.save_policy(
        mode="USN_INCOME",
        tax_rate=6.0,
    )
    assert first["saved"] is True
    previous = file_path.read_text(
        encoding="utf-8"
    )

    def _fail_replace(source, target):
        raise OSError("private replace failure")

    monkeypatch.setattr(
        "services.tax_configuration_service.os.replace",
        _fail_replace,
    )

    result = service.save_policy(
        mode="USN_INCOME",
        tax_rate=7.0,
    )

    assert result == {
        "error": True,
        "saved": False,
        "message": "TAX_CONFIGURATION_SAVE_FAILED",
    }
    assert "private replace failure" not in str(result)
    assert file_path.read_text(
        encoding="utf-8"
    ) == previous
    assert list(tmp_path.glob(
        ".tax-configuration-write-*.tmp"
    )) == []


def test_v1099_truncated_json_is_unconfigured_not_startup_exception(tmp_path):
    file_path = tmp_path / "tax.json"
    file_path.write_text(
        '{"mode":"USN_INCOME","tax_rate":',
        encoding="utf-8",
    )

    result = TaxConfigurationService(
        file_path=str(file_path)
    ).get_policy()

    assert result == {
        "error": False,
        "configured": False,
        "policy": None,
    }


def test_v1100_production_factory_survives_malformed_tax_config(tmp_path):
    file_path = tmp_path / "tax.json"
    file_path.write_text(
        json.dumps(
            {
                "mode": "USN_INCOME",
                "tax_rate": "broken",
                "minimum_tax_rate": 1.0,
            }
        ),
        encoding="utf-8",
    )
    configuration = TaxConfigurationService(
        file_path=str(file_path)
    )

    core = create_telegram_core(
        tax_configuration_service=configuration
    )

    analytics = (
        core["action_router"]
        .executors["sales"]
        .sales_intelligence_service
        .analytics_service
        .business_analytics
    )
    provider = (
        core["unit_economics_query"]
        .unit_economics_provider
    )

    assert core["tax_configuration"] is configuration
    assert analytics.tax_mode is None
    assert provider.tax_mode is None
