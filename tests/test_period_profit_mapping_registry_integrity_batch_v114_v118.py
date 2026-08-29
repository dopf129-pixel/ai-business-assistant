import json

from period_profit_mapping_registry_health_response import (
    build_period_profit_mapping_registry_health_response,
)
from return_financial_operation_authorized_mapping import (
    build_return_financial_operation_authorized_mapping,
)
from services.period_profit_mapping_registry_service import PeriodProfitMappingRegistryService


def _mapping(type_id=1, name="Return fee"):
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


def test_corrupt_json_fails_closed_and_blocks_writes(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text("{broken", encoding="utf-8")
    service = PeriodProfitMappingRegistryService(str(path))

    health = service.health()
    assert health["health_status"] == "CORRUPT"
    assert health["load_allowed"] is False
    assert health["writable"] is False
    assert service.load_active("RETURN") is None
    assert service.save("RETURN", _mapping(), activate=True)["code"] == "PERIOD_PROFIT_MAPPING_REGISTRY_HEALTH_BLOCKED"


def test_unsupported_schema_fails_closed(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"schema_version": 999, "scopes": {}}), encoding="utf-8")
    service = PeriodProfitMappingRegistryService(str(path))
    health = service.health()
    assert health["health_status"] == "CORRUPT"
    assert "REGISTRY_SCHEMA_VERSION_UNSUPPORTED" in health["issues"]
    assert service.load_active("RETURN") is None


def test_tampered_mapping_id_is_not_loadable(tmp_path):
    path = tmp_path / "registry.json"
    service = PeriodProfitMappingRegistryService(str(path), clock=lambda: "t")
    saved = service.save("RETURN", _mapping(), activate=True)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["scopes"]["RETURN"]["revisions"][0]["mapping"]["mapping_id"] = "tampered"
    path.write_text(json.dumps(raw), encoding="utf-8")

    assert saved["error"] is False
    health = service.health()
    assert health["health_status"] == "CORRUPT"
    assert service.load_active("RETURN") is None


def test_stale_active_revision_is_reported_but_remains_loadable(tmp_path):
    path = tmp_path / "registry.json"
    service = PeriodProfitMappingRegistryService(str(path), clock=lambda: "t")
    first = _mapping(1, "Return fee")
    service.save("RETURN", first, activate=True)
    service.save("RETURN", _mapping(2, "Return logistics"), activate=False)

    health = service.health()
    state = health["scopes"]["RETURN"]
    assert health["health_status"] == "HEALTHY"
    assert state["active_revision_stale"] is True
    assert state["active_mapping_loadable"] is True
    assert service.load_active("RETURN")["mapping_id"] == first["mapping_id"]


def test_health_response_explains_fail_closed_status(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text("{broken", encoding="utf-8")
    service = PeriodProfitMappingRegistryService(str(path))
    response = build_period_profit_mapping_registry_health_response(service.health())
    assert "Fail-closed: да" in response["text"]
    assert "не загружаются" in response["text"]
    assert response["ozon_mutation"] is False
    assert response["profit_adjustment_allowed"] is False
