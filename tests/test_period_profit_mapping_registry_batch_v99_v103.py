from period_profit_mapping_registry_factory import load_active_period_profit_mappings
from services.period_profit_mapping_registry_service import PeriodProfitMappingRegistryService


def _return_mapping(mapping_id="return-financial-mapping:a"):
    return {
        "error": False,
        "status": "RETURN_FINANCIAL_OPERATION_AUTHORIZED_MAPPING_READY",
        "mapping_id": mapping_id,
        "operation_names": ["Return fee"],
        "mapping_authorized": True,
        "financial_evidence_mapping_allowed": True,
        "returns_profit_adjustment_allowed": False,
        "automatic_activation_allowed": False,
        "immutable_artifact": True,
        "executed": False,
    }


def _expense_mapping(scope, mapping_id):
    return {
        "error": False,
        "status": "PERIOD_PROFIT_EXPENSE_OPERATION_AUTHORIZED_MAPPING_READY",
        "scope": scope,
        "mapping_id": mapping_id,
        "operation_names": [scope.title()],
        "mapping_authorized": True,
        "financial_evidence_mapping_allowed": True,
        "profit_adjustment_allowed": False,
        "automatic_activation_allowed": False,
        "immutable_artifact": True,
        "executed": False,
    }


def test_registry_persists_versioned_revisions_and_active_mapping(tmp_path):
    path = tmp_path / "registry.json"
    clock_values = iter(["t1", "t2", "t3", "t4"])
    service = PeriodProfitMappingRegistryService(str(path), clock=lambda: next(clock_values))

    first = service.save("RETURN", _return_mapping("m1"), activate=True)
    second = service.save("RETURN", _return_mapping("m2"), activate=False)

    assert first["revision_id"] == "return-mapping-r1"
    assert second["revision_id"] == "return-mapping-r2"
    assert service.load_active("RETURN")["mapping_id"] == "m1"

    history = service.history("RETURN")
    assert len(history["revisions"]) == 2
    assert history["active_revision_id"] == "return-mapping-r1"
    assert history["revisions"][0]["immutable_revision"] is True


def test_activation_and_rollback_keep_lineage_without_profit_permission(tmp_path):
    path = tmp_path / "registry.json"
    service = PeriodProfitMappingRegistryService(str(path), clock=lambda: "t")
    first = service.save("ADVERTISING", _expense_mapping("ADVERTISING", "a1"), activate=True)
    second = service.save("ADVERTISING", _expense_mapping("ADVERTISING", "a2"), activate=False)

    activated = service.activate("ADVERTISING", second["revision_id"])
    rolled_back = service.rollback("ADVERTISING", first["revision_id"])

    assert activated["profit_adjustment_allowed"] is False
    assert rolled_back["previous_revision_id"] == second["revision_id"]
    assert rolled_back["profit_adjustment_allowed"] is False
    assert service.load_active("ADVERTISING")["mapping_id"] == "a1"
    events = service.history("ADVERTISING")["events"]
    assert [event["event"] for event in events][-2:] == ["ACTIVATE", "ROLLBACK"]


def test_unsafe_mapping_is_rejected(tmp_path):
    service = PeriodProfitMappingRegistryService(str(tmp_path / "registry.json"))
    unsafe = _expense_mapping("STORAGE", "s1")
    unsafe["profit_adjustment_allowed"] = True
    result = service.save("STORAGE", unsafe)
    assert result["code"] == "PERIOD_PROFIT_AUTHORIZED_MAPPING_REQUIRED"
    assert result["ozon_mutation"] is False
    assert result["executed"] is False


def test_loader_returns_three_independent_active_scopes(tmp_path):
    service = PeriodProfitMappingRegistryService(str(tmp_path / "registry.json"), clock=lambda: "t")
    service.save("RETURN", _return_mapping("r1"), activate=True)
    service.save("ADVERTISING", _expense_mapping("ADVERTISING", "a1"), activate=True)
    mappings = load_active_period_profit_mappings(service)

    assert mappings["RETURN"]["mapping_id"] == "r1"
    assert mappings["ADVERTISING"]["mapping_id"] == "a1"
    assert mappings["STORAGE"] is None
