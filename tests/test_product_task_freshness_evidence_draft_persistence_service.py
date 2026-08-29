from copy import deepcopy

from services.product_task_freshness_evidence_draft_persistence_service import (
    ProductTaskFreshnessEvidenceDraftPersistenceService,
)


class FakeStorage:
    def __init__(self, records, fail=False):
        self.records = deepcopy(records)
        self.fail = fail
        self.save_calls = 0

    def load(self):
        return deepcopy(self.records)

    def save(self, records):
        self.save_calls += 1
        if self.fail:
            raise OSError("write failed")
        self.records = deepcopy(records)
        return True


def _draft(**values):
    result = {
        "draft_id": "draft-1",
        "sku": "hook-2",
        "status": "DRAFT",
        "decision_type": "KEEP_PRICE",
        "execution_allowed": False,
        "executed": False,
    }
    result.update(values)
    return result


def _readiness(**values):
    result = {
        "application_readiness_id": "evidence-application-readiness:evidence-application-permission-signal:p1",
        "permission_signal_id": "evidence-application-permission-signal:p1",
        "draft_id": "draft-1",
        "sku": "hook-2",
        "status": "APPLICATION_READY_FOR_SEPARATE_STEP",
        "application_ready": True,
        "application_review_complete": True,
        "application_allowed": False,
        "application_started": False,
        "readiness_evidence": {
            "sales_source_recorded_at": "2026-08-29T13:00:00+00:00",
            "stock_source_recorded_at": "2026-08-29T13:01:00+00:00",
        },
        "readiness_evidence_count": 2,
        "source_freshness_proven": False,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_persists_only_freshness_evidence_and_preserves_business_fields():
    storage = FakeStorage([_draft()])
    service = ProductTaskFreshnessEvidenceDraftPersistenceService(storage)
    before = deepcopy(storage.records[0])
    result = service.apply_and_persist(_readiness())
    saved = storage.records[0]
    assert result["status"] == "FRESHNESS_EVIDENCE_DRAFT_PERSISTED"
    assert result["persisted"] is True
    assert storage.save_calls == 1
    assert saved["sales_source_recorded_at"] == "2026-08-29T13:00:00+00:00"
    assert saved["stock_source_recorded_at"] == "2026-08-29T13:01:00+00:00"
    assert saved["decision_type"] == before["decision_type"]
    assert saved["execution_allowed"] is False
    assert result["product_decision_recomputed"] is False
    assert result["ozon_mutation_called"] is False


def test_second_application_is_durable_idempotent_noop():
    storage = FakeStorage([_draft()])
    service = ProductTaskFreshnessEvidenceDraftPersistenceService(storage)
    service.apply_and_persist(_readiness())
    snapshot = deepcopy(storage.records)
    result = service.apply_and_persist(_readiness())
    assert result["status"] == "FRESHNESS_EVIDENCE_DRAFT_ALREADY_PERSISTED"
    assert result["persisted"] is True
    assert result["storage_write_attempted"] is False
    assert storage.save_calls == 1
    assert storage.records == snapshot


def test_not_found_blocks_without_write():
    storage = FakeStorage([_draft(draft_id="other")])
    result = ProductTaskFreshnessEvidenceDraftPersistenceService(storage).apply_and_persist(_readiness())
    assert result["code"] == "DURABLE_DRAFT_NOT_FOUND"
    assert storage.save_calls == 0


def test_ambiguous_draft_blocks_without_write():
    storage = FakeStorage([_draft(), _draft()])
    result = ProductTaskFreshnessEvidenceDraftPersistenceService(storage).apply_and_persist(_readiness())
    assert result["code"] == "DURABLE_DRAFT_AMBIGUOUS"
    assert storage.save_calls == 0


def test_unsafe_evidence_blocks_without_write():
    storage = FakeStorage([_draft()])
    evidence = deepcopy(_readiness()["readiness_evidence"])
    evidence["decision_type"] = "CHANGE_PRICE"
    result = ProductTaskFreshnessEvidenceDraftPersistenceService(storage).apply_and_persist(
        _readiness(readiness_evidence=evidence, readiness_evidence_count=3)
    )
    assert result["code"] == "READINESS_EVIDENCE_UNSAFE"
    assert storage.save_calls == 0


def test_execution_boundary_violation_blocks_without_write():
    storage = FakeStorage([_draft()])
    result = ProductTaskFreshnessEvidenceDraftPersistenceService(storage).apply_and_persist(
        _readiness(execution_ready=True)
    )
    assert result["code"] == "READINESS_SAFETY_BOUNDARY_VIOLATION"
    assert storage.save_calls == 0


def test_write_failure_does_not_report_persisted():
    storage = FakeStorage([_draft()], fail=True)
    original = deepcopy(storage.records)
    result = ProductTaskFreshnessEvidenceDraftPersistenceService(storage).apply_and_persist(_readiness())
    assert result["code"] == "DURABLE_DRAFT_WRITE_FAILED"
    assert result["persisted"] is False
    assert result["storage_write_attempted"] is True
    assert storage.records == original


def test_missing_context_blocks_without_load_write_side_effect():
    storage = FakeStorage([_draft()])
    result = ProductTaskFreshnessEvidenceDraftPersistenceService(storage).apply_and_persist(
        _readiness(draft_id="")
    )
    assert result["code"] == "DURABLE_DRAFT_CONTEXT_REQUIRED"
    assert storage.save_calls == 0
