from period_profit_mapping_registry_factory import load_active_period_profit_mappings
from period_profit_expense_operation_authorized_mapping import (
    build_period_profit_expense_operation_authorized_mapping,
)
from return_financial_operation_authorized_mapping import (
    build_return_financial_operation_authorized_mapping,
)
from services.period_profit_mapping_registry_service import PeriodProfitMappingRegistryService


def _return_mapping(type_id=1, name="Return fee"):
    return build_return_financial_operation_authorized_mapping({
        "error": False,
        "status": "RETURN_FINANCIAL_OPERATION_SELECTION_AUTHORIZED",
        "mapping_authorized": True,
        "financial_evidence_mapping_allowed": True,
        "selected_operations": [{
            "type_id": type_id,
            "name": name,
            "description": None,
            "source": "OZON_FINANCE_ACCRUAL_TYPES",
        }],
    })


def _expense_mapping(scope, type_id=1, name=None):
    return build_period_profit_expense_operation_authorized_mapping({
        "error": False,
        "status": "PERIOD_PROFIT_EXPENSE_OPERATION_AUTHORIZED",
        "scope": scope,
        "mapping_authorized": True,
        "financial_evidence_mapping_allowed": True,
        "selected_operations": [{
            "type_id": type_id,
            "name": name or scope.title(),
            "description": None,
            "source": "OZON_FINANCE_ACCRUAL_TYPES",
        }],
    })


def test_registry_persists_versioned_revisions_and_active_mapping(tmp_path):
    path = tmp_path / "registry.json"
    clock_values = iter(["t1", "t2", "t3", "t4"])
    service = PeriodProfitMappingRegistryService(str(path), clock=lambda: next(clock_values))

    first_mapping = _return_mapping(1, "Return fee")
    second_mapping = _return_mapping(2, "Return logistics")
    first = service.save("RETURN", first_mapping, activate=True)
    second = service.save("RETURN", second_mapping, activate=False)

    assert first["revision_id"] == "return-mapping-r1"
    assert second["revision_id"] == "return-mapping-r2"
    assert service.load_active("RETURN")["mapping_id"] == first_mapping["mapping_id"]

    history = service.history("RETURN")
    assert len(history["revisions"]) == 2
    assert history["active_revision_id"] == "return-mapping-r1"
    assert history["revisions"][0]["immutable_revision"] is True


def test_activation_and_rollback_keep_lineage_without_profit_permission(tmp_path):
    path = tmp_path / "registry.json"
    service = PeriodProfitMappingRegistryService(str(path), clock=lambda: "t")
    first_mapping = _expense_mapping("ADVERTISING", 1, "Promo")
    second_mapping = _expense_mapping("ADVERTISING", 2, "Promo 2")
    first = service.save("ADVERTISING", first_mapping, activate=True)
    second = service.save("ADVERTISING", second_mapping, activate=False)

    activated = service.activate("ADVERTISING", second["revision_id"])
    rolled_back = service.rollback("ADVERTISING", first["revision_id"])

    assert activated["profit_adjustment_allowed"] is False
    assert rolled_back["previous_revision_id"] == second["revision_id"]
    assert rolled_back["profit_adjustment_allowed"] is False
    assert service.load_active("ADVERTISING")["mapping_id"] == first_mapping["mapping_id"]
    events = service.history("ADVERTISING")["events"]
    assert [event["event"] for event in events][-2:] == ["ACTIVATE", "ROLLBACK"]


def test_unsafe_mapping_is_rejected(tmp_path):
    service = PeriodProfitMappingRegistryService(str(tmp_path / "registry.json"))
    unsafe = _expense_mapping("STORAGE", 1, "Storage")
    unsafe["profit_adjustment_allowed"] = True
    result = service.save("STORAGE", unsafe)
    assert result["code"] == "PERIOD_PROFIT_AUTHORIZED_MAPPING_REQUIRED"
    assert result["ozon_mutation"] is False
    assert result["executed"] is False


def test_loader_returns_three_independent_active_scopes(tmp_path):
    service = PeriodProfitMappingRegistryService(str(tmp_path / "registry.json"), clock=lambda: "t")
    return_mapping = _return_mapping(1, "Return fee")
    advertising_mapping = _expense_mapping("ADVERTISING", 1, "Promo")
    service.save("RETURN", return_mapping, activate=True)
    service.save("ADVERTISING", advertising_mapping, activate=True)
    mappings = load_active_period_profit_mappings(service)

    assert mappings["RETURN"]["mapping_id"] == return_mapping["mapping_id"]
    assert mappings["ADVERTISING"]["mapping_id"] == advertising_mapping["mapping_id"]
    assert mappings["STORAGE"] is None
