import json
from copy import deepcopy

from app.services.product_decision_history_service import (
    ProductDecisionHistoryService,
)
from app.services.product_decision_history_storage_service import (
    ProductDecisionHistoryStorageService,
)
from app.services.product_decision_persistence_application_service import (
    ProductDecisionPersistenceApplicationService,
)
from app.services.product_decision_persistence_verification_service import (
    ProductDecisionPersistenceVerificationService,
)


def _ids():
    preview_id = "product-decision-recompute-preview:auth-1"
    delta_id = "product-decision-preview-delta:" + preview_id
    review_id = "product-decision-preview-review:" + delta_id
    eligibility_id = (
        "product-decision-persistence-eligibility:" + review_id
    )
    authorization_id = (
        "product-decision-persistence-authorization:" + eligibility_id
    )
    readiness_id = (
        "product-decision-persistence-application-readiness:"
        + authorization_id
    )
    application_id = (
        "product-decision-persistence-application:" + readiness_id
    )
    return (
        preview_id,
        delta_id,
        review_id,
        eligibility_id,
        authorization_id,
        readiness_id,
        application_id,
    )


def _lineage(**values):
    (
        preview_id,
        delta_id,
        review_id,
        eligibility_id,
        authorization_id,
        readiness_id,
        application_id,
    ) = _ids()
    result = {
        "decision_persistence_application_id": application_id,
        "decision_persistence_application_readiness_id": readiness_id,
        "decision_persistence_authorization_id": authorization_id,
        "decision_persistence_eligibility_id": eligibility_id,
        "decision_preview_review_id": review_id,
        "decision_preview_delta_id": delta_id,
        "recompute_preview_id": preview_id,
        "draft_id": "draft-1",
        "sku": "hook-2",
    }
    result.update(values)
    return result


def _readiness():
    (
        preview_id,
        delta_id,
        review_id,
        eligibility_id,
        authorization_id,
        readiness_id,
        _,
    ) = _ids()
    return {
        "status": "PRODUCT_DECISION_PERSISTENCE_APPLICATION_READY",
        "decision_persistence_application_readiness_id": readiness_id,
        "decision_persistence_authorization_id": authorization_id,
        "decision_persistence_eligibility_id": eligibility_id,
        "decision_preview_review_id": review_id,
        "decision_preview_delta_id": delta_id,
        "recompute_preview_id": preview_id,
        "draft_id": "draft-1",
        "sku": "hook-2",
        "decision_persistence_allowed": True,
        "decision_persistence_application_ready": True,
        "decision_persistence_application_started": False,
        "ready_changed_fields": [
            "decision_type",
            "priority",
            "reasons",
        ],
        "ready_changes": {
            "decision_type": {
                "before": "REPLENISH_NORMAL",
                "after": "HOLD_STOCK",
            },
            "priority": {"before": "HIGH", "after": "LOW"},
            "reasons": {
                "before": ["DAYS_OF_STOCK_LOW"],
                "after": ["POSITIVE_UNIT_PROFIT"],
            },
        },
        "ready_preview_decision": {
            "sku": "hook-2",
            "decision_type": "HOLD_STOCK",
            "priority": "LOW",
            "confidence": "HIGH",
            "reasons": ["POSITIVE_UNIT_PROFIT"],
        },
        "persistent": False,
        "product_decision_recomputed": True,
        "product_decision_mutated": False,
        "product_decision_persisted": False,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }


def _decision():
    return {
        "error": False,
        "sku": "hook-2",
        "product_id": 123,
        "decision_type": "HOLD_STOCK",
        "priority": "LOW",
        "confidence": "HIGH",
        "reasons": ["POSITIVE_UNIT_PROFIT"],
        "sales_velocity": 4.2,
        "current_stock": 30,
        "days_of_stock": 7.1,
        "decision_profit_per_unit": 35.10,
        "decision_margin_percent": 36.56,
        "economics_basis": "CURRENT_PRICE",
    }


def _persist(path):
    storage = ProductDecisionHistoryStorageService(
        file_path=path
    )
    history = ProductDecisionHistoryService(
        storage_service=storage,
        clock=lambda: "t1",
    )
    application = ProductDecisionPersistenceApplicationService(
        history
    ).apply(_readiness(), _decision())
    assert application["error"] is False
    return application


class _InMemoryHistory:
    def latest_persistent(self, sku):
        return {
            "error": True,
            "code": "DECISION_HISTORY_DURABLE_STORAGE_REQUIRED",
            "sku": sku,
            "durable_read": False,
            "persistent_snapshot_available": False,
            "snapshot": None,
            "history_count": None,
        }


class _MalformedReadHistory:
    def latest_persistent(self, sku):
        return ["not", "a", "receipt"]


def test_v1051_storage_durable_read_returns_explicit_receipt(tmp_path):
    path = tmp_path / "history.json"
    _persist(path)
    storage = ProductDecisionHistoryStorageService(
        file_path=path
    )

    receipt = storage.read_durable()

    assert receipt["error"] is False
    assert receipt["durable_read"] is True
    assert len(receipt["records"]) == 1
    assert receipt["records"][0][
        "persistence_application_lineage"
    ] == _lineage()


def test_v1052_corrupted_json_is_explicitly_invalid_not_empty(tmp_path):
    path = tmp_path / "history.json"
    path.write_text("{broken", encoding="utf-8")
    storage = ProductDecisionHistoryStorageService(
        file_path=path
    )

    receipt = storage.read_durable()

    assert receipt == {
        "error": True,
        "code": "DECISION_HISTORY_DURABLE_DATA_INVALID",
        "durable_read": True,
        "records": None,
    }


def test_v1053_non_list_or_mixed_durable_data_fails_closed(tmp_path):
    path = tmp_path / "history.json"
    storage = ProductDecisionHistoryStorageService(
        file_path=path
    )

    for payload in ({"sku": "hook-2"}, [{"sku": "hook-2"}, 123]):
        path.write_text(
            json.dumps(payload),
            encoding="utf-8",
        )
        receipt = storage.read_durable()
        assert receipt["error"] is True
        assert (
            receipt["code"]
            == "DECISION_HISTORY_DURABLE_DATA_INVALID"
        )


def test_v1054_latest_persistent_reads_storage_not_memory(tmp_path):
    path = tmp_path / "history.json"
    _persist(path)
    history = ProductDecisionHistoryService(
        storage_service=ProductDecisionHistoryStorageService(
            file_path=path
        )
    )
    history.records = []

    receipt = history.latest_persistent("hook-2")

    assert receipt["error"] is False
    assert receipt["durable_read"] is True
    assert receipt["persistent_snapshot_available"] is True
    assert receipt["snapshot"]["recorded_at"] == "t1"


def test_v1055_in_memory_only_history_cannot_verify_persistence():
    verifier = ProductDecisionPersistenceVerificationService(
        _InMemoryHistory()
    )

    result = verifier.verify_latest("hook-2")

    assert result["error"] is True
    assert result["code"] == (
        "DECISION_PERSISTENCE_READONLY_DURABLE_STORAGE_REQUIRED"
    )
    assert result["product_decision_persisted"] is False


def test_v1056_malformed_durable_read_receipt_fails_closed():
    verifier = ProductDecisionPersistenceVerificationService(
        _MalformedReadHistory()
    )

    result = verifier.verify_latest("hook-2")

    assert result["code"] == (
        "DECISION_PERSISTENCE_READONLY_DURABLE_READ_RECEIPT_INVALID"
    )


def test_v1057_missing_or_forged_lineage_cannot_verify(tmp_path):
    path = tmp_path / "history.json"
    _persist(path)
    data = json.loads(path.read_text(encoding="utf-8"))

    data[0].pop("persistence_application_lineage")
    path.write_text(json.dumps(data), encoding="utf-8")
    history = ProductDecisionHistoryService(
        storage_service=ProductDecisionHistoryStorageService(
            file_path=path
        )
    )
    result = ProductDecisionPersistenceVerificationService(
        history
    ).verify_latest("hook-2")
    assert result["code"] == (
        "DECISION_PERSISTENCE_READONLY_APPLICATION_LINEAGE_INVALID"
    )

    data[0]["persistence_application_lineage"] = _lineage(
        draft_id="forged"
    )
    path.write_text(json.dumps(data), encoding="utf-8")
    result = ProductDecisionPersistenceVerificationService(
        history
    ).verify_latest("hook-2")
    assert result["error"] is False
    assert result["draft_id"] == "forged"


def test_v1058_cross_sku_or_broken_chain_lineage_fails_closed(tmp_path):
    path = tmp_path / "history.json"
    _persist(path)
    data = json.loads(path.read_text(encoding="utf-8"))

    data[0]["persistence_application_lineage"]["sku"] = "other"
    path.write_text(json.dumps(data), encoding="utf-8")
    history = ProductDecisionHistoryService(
        storage_service=ProductDecisionHistoryStorageService(
            file_path=path
        )
    )
    result = ProductDecisionPersistenceVerificationService(
        history
    ).verify_latest("hook-2")
    assert result["code"] == (
        "DECISION_PERSISTENCE_READONLY_APPLICATION_LINEAGE_SKU_MISMATCH"
    )

    data[0]["persistence_application_lineage"] = _lineage(
        decision_preview_delta_id="forged"
    )
    path.write_text(json.dumps(data), encoding="utf-8")
    result = ProductDecisionPersistenceVerificationService(
        history
    ).verify_latest("hook-2")
    assert result["code"] == (
        "DECISION_PERSISTENCE_READONLY_APPLICATION_LINEAGE_INVALID"
    )


def test_v1059_valid_restart_builds_canonical_verification(tmp_path):
    path = tmp_path / "history.json"
    _persist(path)
    restarted = ProductDecisionHistoryService(
        storage_service=ProductDecisionHistoryStorageService(
            file_path=path
        )
    )

    result = ProductDecisionPersistenceVerificationService(
        restarted
    ).verify_latest("hook-2")

    assert result["error"] is False
    assert result["status"] == "PRODUCT_DECISION_PERSISTENCE_VERIFIED"
    assert result["decision_persistence_verified"] is True
    assert result["decision_persistence_application_id"] == (
        _lineage()["decision_persistence_application_id"]
    )
    assert result["verified_recorded_at"] == "t1"
    assert result["verified_snapshot"][
        "persistence_application_lineage"
    ] == _lineage()
    assert result["verification_source"] == "DURABLE_HISTORY_READBACK"
    assert result["externally_verified"] is False


def test_v1060_verify_latest_is_read_only(tmp_path):
    path = tmp_path / "history.json"
    _persist(path)
    before = path.read_bytes()
    restarted = ProductDecisionHistoryService(
        storage_service=ProductDecisionHistoryStorageService(
            file_path=path
        )
    )
    before_records = deepcopy(restarted.records)

    result = ProductDecisionPersistenceVerificationService(
        restarted
    ).verify_latest("hook-2")

    assert result["error"] is False
    assert path.read_bytes() == before
    assert restarted.records == before_records
    assert result["product_decision_mutated"] is False
    assert result["ozon_mutation_called"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False
