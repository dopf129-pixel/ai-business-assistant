from copy import deepcopy

from services.product_task_freshness_evidence_draft_persistence_verification_service import (
    ProductTaskFreshnessEvidenceDraftPersistenceVerificationService,
)


class FakeStorage:
    def __init__(self, records):
        self.records = deepcopy(records)

    def load(self):
        return deepcopy(self.records)


def _readiness(**values):
    result = {
        "draft_id": "draft-1",
        "sku": "hook-2",
        "readiness_evidence": {
            "sales_source_recorded_at": "2026-08-29T13:00:00+00:00",
            "stock_source_recorded_at": "2026-08-29T13:01:00+00:00",
        },
        "readiness_evidence_count": 2,
    }
    result.update(values)
    return result


def _persistence(**values):
    result = {
        "draft_id": "draft-1",
        "sku": "hook-2",
        "persisted": True,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
    result.update(values)
    return result


def _draft(**values):
    result = {
        "draft_id": "draft-1",
        "sku": "hook-2",
        "decision_type": "KEEP_PRICE",
        "sales_source_recorded_at": "2026-08-29T13:00:00+00:00",
        "stock_source_recorded_at": "2026-08-29T13:01:00+00:00",
        "execution_allowed": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_verifies_exact_durable_readback_without_execution():
    service = ProductTaskFreshnessEvidenceDraftPersistenceVerificationService(FakeStorage([_draft()]))
    result = service.verify(_readiness(), _persistence())
    assert result["status"] == "FRESHNESS_EVIDENCE_DURABLE_PERSISTENCE_VERIFIED"
    assert result["verified"] is True
    assert result["verified_evidence_count"] == 2
    assert result["mismatched_fields"] == []
    assert result["product_decision_recomputed"] is False
    assert result["product_decision_mutated"] is False
    assert result["ozon_mutation_called"] is False
    assert result["execution_allowed"] is False
    assert result["execution_ready"] is False
    assert result["executed"] is False


def test_unconfirmed_persistence_is_blocked_before_readback():
    result = ProductTaskFreshnessEvidenceDraftPersistenceVerificationService(FakeStorage([_draft()])).verify(
        _readiness(), _persistence(persisted=False)
    )
    assert result["code"] == "DURABLE_PERSISTENCE_NOT_CONFIRMED"


def test_persistence_identity_mismatch_is_blocked():
    result = ProductTaskFreshnessEvidenceDraftPersistenceVerificationService(FakeStorage([_draft()])).verify(
        _readiness(), _persistence(draft_id="other")
    )
    assert result["code"] == "DURABLE_PERSISTENCE_DRAFT_ID_MISMATCH"


def test_execution_boundary_violation_is_blocked():
    result = ProductTaskFreshnessEvidenceDraftPersistenceVerificationService(FakeStorage([_draft()])).verify(
        _readiness(), _persistence(execution_ready=True)
    )
    assert result["code"] == "DURABLE_PERSISTENCE_EXECUTION_BOUNDARY_VIOLATION"


def test_unsafe_expected_evidence_is_blocked():
    evidence = deepcopy(_readiness()["readiness_evidence"])
    evidence["decision_type"] = "CHANGE_PRICE"
    result = ProductTaskFreshnessEvidenceDraftPersistenceVerificationService(FakeStorage([_draft()])).verify(
        _readiness(readiness_evidence=evidence, readiness_evidence_count=3), _persistence()
    )
    assert result["code"] == "DURABLE_VERIFICATION_EVIDENCE_UNSAFE"


def test_missing_durable_draft_is_blocked():
    result = ProductTaskFreshnessEvidenceDraftPersistenceVerificationService(FakeStorage([])).verify(
        _readiness(), _persistence()
    )
    assert result["code"] == "DURABLE_VERIFICATION_DRAFT_NOT_FOUND"


def test_ambiguous_durable_draft_is_blocked():
    result = ProductTaskFreshnessEvidenceDraftPersistenceVerificationService(FakeStorage([_draft(), _draft()])).verify(
        _readiness(), _persistence()
    )
    assert result["code"] == "DURABLE_VERIFICATION_DRAFT_AMBIGUOUS"


def test_mismatched_persisted_evidence_is_reported():
    result = ProductTaskFreshnessEvidenceDraftPersistenceVerificationService(
        FakeStorage([_draft(stock_source_recorded_at="wrong")])
    ).verify(_readiness(), _persistence())
    assert result["code"] == "DURABLE_VERIFICATION_EVIDENCE_MISMATCH"
    assert result["verified"] is False
    assert result["mismatched_fields"] == ["stock_source_recorded_at"]


def test_missing_context_is_blocked():
    result = ProductTaskFreshnessEvidenceDraftPersistenceVerificationService(FakeStorage([_draft()])).verify(
        _readiness(draft_id=""), _persistence()
    )
    assert result["code"] == "DURABLE_VERIFICATION_CONTEXT_REQUIRED"
