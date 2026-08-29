from copy import deepcopy

from app.product_task_freshness_evidence_approval_contract import (
    build_freshness_evidence_approval_contract,
)


def _draft(**values):
    result = {
        "draft_id": "d1",
        "sku": "hook-2",
        "proposal_type": "REVIEW_REPLENISHMENT",
    }
    result.update(values)
    return result


def _candidate(**evidence):
    return {
        "request_id": "refresh:d1",
        "draft_id": "d1",
        "sku": "hook-2",
        "evidence_update": evidence,
        "persistent": False,
        "executed": False,
    }


def _preview(**values):
    result = {
        "request_id": "refresh:d1",
        "draft_id": "d1",
        "sku": "hook-2",
        "status": "PREVIEW_READY",
        "preview_only": True,
        "preview_freshness_status": "FRESH",
        "preview_freshness_validated": True,
        "applied_evidence": {
            "sales_source_recorded_at": "2026-08-29T11:55:00+00:00",
            "stock_source_recorded_at": "2026-08-29T11:56:00+00:00",
        },
        "source_freshness_proven": False,
        "executed": False,
    }
    result.update(values)
    return result


def test_validated_preview_builds_approval_required_contract_without_granting_it():
    candidate = _candidate(
        sales_source_recorded_at="2026-08-29T11:55:00+00:00",
        stock_source_recorded_at="2026-08-29T11:56:00+00:00",
    )

    result = build_freshness_evidence_approval_contract(
        _draft(), candidate, _preview()
    )

    assert result["status"] == "APPROVAL_REQUIRED"
    assert result["approval_ready"] is True
    assert result["approval_required"] is True
    assert result["approval_granted"] is False
    assert result["application_allowed"] is False
    assert result["freshness_guard_validated"] is True
    assert result["source_freshness_proven"] is False
    assert result["execution_allowed"] is False
    assert result["executed"] is False


def test_non_fresh_preview_is_blocked():
    result = build_freshness_evidence_approval_contract(
        _draft(),
        _candidate(sales_source_recorded_at="old"),
        _preview(
            preview_freshness_status="STALE",
            preview_freshness_validated=False,
            applied_evidence={"sales_source_recorded_at": "old"},
        ),
    )

    assert result["status"] == "APPROVAL_BLOCKED"
    assert result["code"] == "FRESHNESS_NOT_VALIDATED"
    assert result["approval_ready"] is False
    assert result["application_allowed"] is False


def test_candidate_and_preview_evidence_must_match_exactly():
    result = build_freshness_evidence_approval_contract(
        _draft(),
        _candidate(
            sales_source_recorded_at="2026-08-29T11:55:00+00:00",
            stock_source_recorded_at="2026-08-29T11:56:00+00:00",
        ),
        _preview(applied_evidence={
            "sales_source_recorded_at": "2026-08-29T11:55:00+00:00",
        }),
    )

    assert result["code"] == "VALIDATED_EVIDENCE_MISMATCH"
    assert result["validated_evidence"] == {}


def test_cross_draft_or_cross_sku_context_is_blocked():
    wrong_draft = build_freshness_evidence_approval_contract(
        _draft(),
        {**_candidate(), "draft_id": "d2"},
        _preview(),
    )
    wrong_sku = build_freshness_evidence_approval_contract(
        _draft(),
        _candidate(),
        _preview(sku="other-sku"),
    )

    assert wrong_draft["code"] == "DRAFT_ID_MISMATCH"
    assert wrong_sku["code"] == "SKU_MISMATCH"


def test_unexpected_candidate_fields_are_not_approved():
    candidate = _candidate(
        sales_source_recorded_at="2026-08-29T11:55:00+00:00",
        stock_source_recorded_at="2026-08-29T11:56:00+00:00",
        execution_allowed=True,
        updated_at="2026-08-29T12:00:00+00:00",
    )
    snapshot = deepcopy(candidate)

    result = build_freshness_evidence_approval_contract(
        _draft(), candidate, _preview()
    )

    assert "execution_allowed" not in result["validated_evidence"]
    assert "updated_at" not in result["validated_evidence"]
    assert candidate == snapshot
    assert result["execution_allowed"] is False


def test_preview_must_remain_read_only():
    result = build_freshness_evidence_approval_contract(
        _draft(),
        _candidate(
            sales_source_recorded_at="2026-08-29T11:55:00+00:00",
            stock_source_recorded_at="2026-08-29T11:56:00+00:00",
        ),
        _preview(preview_only=False),
    )

    assert result["code"] == "VALIDATION_PREVIEW_NOT_READ_ONLY"
    assert result["approval_granted"] is False
    assert result["application_allowed"] is False
