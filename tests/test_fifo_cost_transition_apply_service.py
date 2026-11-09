"""Deterministic prepare-seal coverage for FIFO late-entry transitions."""

from dataclasses import replace
from datetime import timedelta

from services.fifo_cost_late_entry_impact_service import (
    FifoCostLateEntryImpactService,
)
from services.fifo_cost_transition_apply_service import (
    FifoCostTransitionApplyService,
)
from services.fifo_cost_transition_contracts import FifoFinancialPeriodSummary
from services.fifo_cost_transition_evidence_service import (
    FifoCostTransitionEvidenceBundle,
)
from services.fifo_cost_transition_service import FifoCostTransitionService
from services.tax_service import TaxService
from test_fifo_cost_transition_atomic_apply import (
    CASE_ID,
    COMPLETE_THROUGH,
    SCOPE,
    STORE,
    TAX_POLICY,
    _prepared_repository,
    _transition_no_write_snapshot,
)
from test_fifo_cost_transition_store import OWNER, _case
from services.tenant_context import reset_current_tenant_user_id
from services.fifo_cost_repository import FifoCostRepository


IDENTITY = {
    "store_id": STORE,
    "product_id": SCOPE.product_id,
    "offer_id": SCOPE.offer_id,
    "sku": SCOPE.sku,
}
NONE_POLICY = {
    "error": False,
    "configured": True,
    "policy": {"mode": "NONE", "tax_rate": 0, "minimum_tax_rate": 1},
}


class _ReadyReview:
    def __init__(self, *, initialized=False):
        self.initialized = initialized

    def assess(self, *, case_id, identity, for_transition_prepare=False):
        from types import SimpleNamespace

        assert for_transition_prepare is True
        return {
            "error": False,
            "case_revision": 3,
            "readiness": SimpleNamespace(status="PREVIEW_READY", requirements=()),
            "proposal": object(),
            "fifo_queue_initialized": self.initialized,
            "fifo_remaining_status": "COMPLETE",
        }


class _SavedEvidence:
    def __init__(self, bridge, bundle):
        self.bridge = bridge
        self.bundle = bundle

    def load(
        self, *, case_id, identity, expected_case_revision,
        require_opening_composition=True,
    ):
        assert expected_case_revision == 3
        return {
            "error": False, "code": "FIFO_TRANSITION_EVIDENCE_LOADED",
            "case_revision": expected_case_revision,
            "bundle": self.bundle,
            "missing_requirements": self.bundle.missing_requirements,
        }

    def build_cutoff_bridge(self, *, bundle, proposal):
        return {"error": False, "result": self.bridge, "missing_requirements": ()}


class _TaxConfiguration:
    def __init__(self, result=NONE_POLICY):
        self.result = result

    def get_policy(self):
        return self.result


def _make_period_summary(reconstruction):
    digests = tuple(reconstruction["sale_identity_digests_by_event"].values())
    assert len(digests) == 1
    return FifoFinancialPeriodSummary(
        period_from="2026-11-01",
        period_to="2026-11-30",
        source_fingerprint=FifoCostRepository._sha256("period-source"),
        reconstruction_fingerprint=reconstruction["preview_fingerprint"],
        tax_policy_fingerprint=FifoCostLateEntryImpactService._normalize_policy(
            NONE_POLICY,
        )["fingerprint"],
        sale_identity_digests=digests,
        revenue_rub="1000.00",
        discount_points_rub="0.00",
        net_accrual_rub="400.00",
        current_total_product_cost_rub="200.00",
        current_sku_product_cost_rub=reconstruction["before_total_cogs_rub"],
    )


def _service(repository, bridge, cutover, bundle, clock):
    transition = FifoCostTransitionService(
        repository, now_provider=lambda: clock[0],
    )
    transition.read_confirmed_opening_composition = lambda *, case_id, **identity: {
        "error": False,
        "case_revision": 3,
        "stock_report_fingerprint": cutover["stock_report_fingerprint"],
        "layers": cutover["layers"],
        "confirmed": True,
    }
    evidence = _SavedEvidence(bridge, bundle)
    return FifoCostTransitionApplyService(
        transition,
        history_service=object(),
        evidence_service=evidence,
        review_service=_ReadyReview(),
        tax_configuration_service=_TaxConfiguration(),
        impact_service=FifoCostLateEntryImpactService(TaxService()),
    )


def _bundle(period_summaries=()):
    case = _case(CASE_ID, sku=SCOPE.sku, owner=OWNER, store=STORE)
    case = replace(case, metadata=replace(case.metadata, scope=SCOPE), case_revision=3)
    return FifoCostTransitionEvidenceBundle(
        case=case,
        period_summaries=tuple(period_summaries),
    )


def _reconstruct(repository, bridge, cutover):
    return repository.reconstruct_transition_preview(
        case_id=CASE_ID, **IDENTITY, expected_case_revision=3,
        effective_date="2026-11-07", cutoff_bridge=bridge,
        tax_policy_fingerprint=FifoCostLateEntryImpactService._normalize_policy(
            NONE_POLICY,
        )["fingerprint"],
        idempotency_key="prepare-apply-service-0001",
        initial_opening_cutover=cutover,
    )


def test_prepare_seals_real_impact_without_changing_fifo_until_apply(tmp_path):
    repository, tenant, _stock, bridge, _impact, cutover, _prepared, clock = (
        _prepared_repository(tmp_path, prepare=False)
    )
    try:
        reconstruction = _reconstruct(repository, bridge, cutover)
        assert reconstruction["error"] is False, reconstruction
        bundle = _bundle((_make_period_summary(reconstruction),))
        before = _transition_no_write_snapshot(repository)
        service = _service(repository, bridge, cutover, bundle, clock)
        result = service.prepare(
            case_id=CASE_ID, identity=IDENTITY,
            expected_case_revision=3,
            idempotency_key="prepare-apply-service-0001",
        )

        assert result["error"] is False, result
        assert result["code"] == "FIFO_TRANSITION_PREVIEW_READY"
        assert result["effective_date"] == "2026-11-07"
        assert result["candidate_cogs_rub"] == "92.30"
        assert result["impact_preview"]["periods"][0]["delta_profit_rub"] == "12.70"
        after = _transition_no_write_snapshot(repository)
        assert after["fifo_counts"] == before["fifo_counts"]
        assert after["case_state"] == "READY_TO_CONFIRM"
        assert after["case_revision"] == 4
        assert after["preview_count"] == before["preview_count"] + 1

        retry = service.prepare(
            case_id=CASE_ID, identity=IDENTITY,
            expected_case_revision=3,
            idempotency_key="prepare-apply-service-0001",
        )
        assert retry["error"] is False, retry
        assert retry["replayed"] is True
        assert retry["preview_id"] == result["preview_id"]
        assert _transition_no_write_snapshot(repository) == after

        service.tax_configuration_service.result = {
            "error": False,
            "configured": True,
            "policy": {"mode": "USN_INCOME", "tax_rate": 6, "minimum_tax_rate": 1},
        }
        changed_tax = service.prepare(
            case_id=CASE_ID, identity=IDENTITY,
            expected_case_revision=3,
            idempotency_key="prepare-apply-service-0001",
        )
        assert changed_tax["code"] == "FIFO_TRANSITION_PREVIEW_STALE"
        service.tax_configuration_service.result = NONE_POLICY
        clock[0] += timedelta(hours=1)
        expired = service.prepare(
            case_id=CASE_ID, identity=IDENTITY,
            expected_case_revision=3,
            idempotency_key="prepare-apply-service-0001",
        )
        assert expired["code"] == "FIFO_TRANSITION_PREVIEW_EXPIRED"
        assert _transition_no_write_snapshot(repository) == after
    finally:
        reset_current_tenant_user_id(tenant)


def test_missing_financial_baseline_returns_candidate_only_without_ready_seal(
    tmp_path,
):
    repository, tenant, _stock, bridge, _impact, cutover, _prepared, clock = (
        _prepared_repository(tmp_path, prepare=False)
    )
    try:
        before = _transition_no_write_snapshot(repository)
        result = _service(
            repository, bridge, cutover, _bundle(), clock,
        ).prepare(
            case_id=CASE_ID, identity=IDENTITY,
            expected_case_revision=3,
            idempotency_key="prepare-apply-service-candidate-01",
        )
        assert result["error"] is False, result
        assert result["code"] == "FIFO_TRANSITION_CANDIDATE_ONLY"
        assert result["impact_preview"]["candidate_only"] is True
        assert result["impact_preview"]["reason_code"] == (
            "FIFO_PERIOD_SUMMARY_COVERAGE_INCOMPLETE"
        )
        assert _transition_no_write_snapshot(repository) == before
    finally:
        reset_current_tenant_user_id(tenant)


def test_uninitialized_prepare_requires_owner_confirmed_opening_composition(
    tmp_path,
):
    repository, tenant, _stock, bridge, _impact, cutover, _prepared, clock = (
        _prepared_repository(tmp_path, prepare=False)
    )
    try:
        transition = FifoCostTransitionService(repository)
        transition.read_confirmed_opening_composition = lambda **_kwargs: {
            "error": True,
            "code": "FIFO_OPENING_COMPOSITION_NOT_CONFIRMED",
        }
        service = FifoCostTransitionApplyService(
            transition, object(),
            evidence_service=_SavedEvidence(bridge, _bundle()),
            review_service=_ReadyReview(),
            tax_configuration_service=_TaxConfiguration(),
        )
        before = _transition_no_write_snapshot(repository)
        result = service.prepare(
            case_id=CASE_ID, identity=IDENTITY,
            expected_case_revision=3,
            idempotency_key="prepare-apply-service-no-opening-01",
        )
        assert result["code"] == "FIFO_OPENING_COMPOSITION_NOT_CONFIRMED"
        assert _transition_no_write_snapshot(repository) == before
    finally:
        reset_current_tenant_user_id(tenant)
