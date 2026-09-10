from pathlib import Path

from services.tax_configuration_service import TaxConfigurationService
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


def _tenant(user_id, callback):
    token = set_current_tenant_user_id(user_id)
    try:
        return callback()
    finally:
        reset_current_tenant_user_id(token)


def test_default_tax_configuration_isolated_between_tenants(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def save_a():
        service = TaxConfigurationService(environment={})
        assert service.save_policy("USN_INCOME", 6.0)["saved"] is True
        return service.file_path

    path_a = _tenant("seller-a", save_a)

    def save_b():
        service = TaxConfigurationService(environment={})
        assert service.get_policy()["configured"] is False
        assert service.save_policy("USN_INCOME", 15.0)["saved"] is True
        return service.file_path

    path_b = _tenant("seller-b", save_b)

    assert path_a != path_b
    assert _tenant(
        "seller-a",
        lambda: TaxConfigurationService(environment={}).get_policy()["policy"]["tax_rate"],
    ) == 6.0
    assert _tenant(
        "seller-b",
        lambda: TaxConfigurationService(environment={}).get_policy()["policy"]["tax_rate"],
    ) == 15.0


def test_tax_configuration_without_tenant_preserves_legacy_default_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    service = TaxConfigurationService(environment={})
    expected = Path(tmp_path) / "data" / "tax_configuration.json"

    assert Path(service.file_path) == expected
    assert service.save_policy("NONE")["saved"] is True
    assert expected.exists()
