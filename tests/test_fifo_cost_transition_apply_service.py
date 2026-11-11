"""Deterministic prepare-seal coverage for FIFO late-entry transitions."""

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from types import SimpleNamespace

from services.fifo_cost_late_entry_impact_service import (
    FifoCostLateEntryImpactService,
)
from services.fifo_cost_transition_apply_service import (
    FifoCostTransitionApplyService,
)
from services.fifo_cost_transition_contracts import FifoFinancialPeriodSummary
from services.fifo_cost_transition_evidence_service import (
    FifoCostTransitionEvidenceBundle,
    FifoCostTransitionEvidenceService,
)
from services.fifo_cost_transition_review_service import (
    FifoCostTransitionReviewService,
)
from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_transition_service import FifoCostTransitionService
from services.tax_service import TaxService
from test_fifo_cost_transition_atomic_apply import (
    CASE_ID,
    COMPLETE_THROUGH,
    SCOPE,
    STORE,
    TAX_POLICY,
    _prepared_repository,
    _table_counts,
    _transition_no_write_snapshot,
    TENANT,
)
from test_fifo_cost_transition_store import OWNER, _case
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)
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

    def assess(
        self, *, case_id, identity, for_transition_prepare=False,
        sealed_preview_id=None,
    ):
        from types import SimpleNamespace

        assert for_transition_prepare is True
        return {
            "error": False,
            "case_revision": 3,
            "current_case_revision": 4,
            "case_state": "READY_TO_CONFIRM",
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
        require_opening_composition=True, sealed_preview_id=None,
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


def _service(
    repository, bridge, cutover, bundle, clock, *,
    tax_configuration_service=None, cache_invalidator=None, review_service=None,
):
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
        review_service=review_service or _ReadyReview(),
        tax_configuration_service=(
            tax_configuration_service or _TaxConfiguration()
        ),
        impact_service=FifoCostLateEntryImpactService(TaxService()),
        cache_invalidator=cache_invalidator,
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


def test_exact_expired_ready_preview_reopens_with_cas_and_no_fifo_write(tmp_path):
    repository, tenant, _stock, bridge, _impact, cutover, prepared, clock = (
        _prepared_repository(tmp_path)
    )
    try:
        service = _service(
            repository, bridge, cutover, _bundle(), clock,
        )
        baseline = _transition_no_write_snapshot(repository)
        before_expiry = service.reopen_expired_preview(
            case_id=CASE_ID, identity=IDENTITY, expected_case_revision=4,
            preview_id=prepared["preview_id"],
            preview_fingerprint=prepared["preview_fingerprint"],
            idempotency_key="reopen-expired-preview-0001",
        )
        assert before_expiry["code"] == "FIFO_TRANSITION_PREVIEW_NOT_EXPIRED"
        assert _transition_no_write_snapshot(repository) == baseline

        clock[0] += timedelta(hours=1)
        reopened = service.reopen_expired_preview(
            case_id=CASE_ID, identity=IDENTITY, expected_case_revision=4,
            preview_id=prepared["preview_id"],
            preview_fingerprint=prepared["preview_fingerprint"],
            idempotency_key="reopen-expired-preview-0001",
        )
        assert reopened["error"] is False, reopened
        assert reopened["case_revision"] == 5
        assert reopened["state"] == "AWAITING_EVIDENCE"
        current = repository.read_transition_case(case_id=CASE_ID, **IDENTITY)
        assert current["case_revision"] == 5
        assert current["state"] == "AWAITING_EVIDENCE"
        historical = service.read_preview(
            case_id=CASE_ID, identity=IDENTITY,
            preview_id=prepared["preview_id"],
        )
        assert historical["error"] is False, historical
        assert historical["expired"] is True
        assert historical["is_current"] is False

        retry = service.reopen_expired_preview(
            case_id=CASE_ID, identity=IDENTITY, expected_case_revision=4,
            preview_id=prepared["preview_id"],
            preview_fingerprint=prepared["preview_fingerprint"],
            idempotency_key="reopen-expired-preview-0001",
        )
        assert retry["error"] is False, retry
        assert retry["replayed"] is True
        stale_retry = service.reopen_expired_preview(
            case_id=CASE_ID, identity=IDENTITY, expected_case_revision=4,
            preview_id=prepared["preview_id"],
            preview_fingerprint=prepared["preview_fingerprint"],
            idempotency_key="reopen-expired-preview-0002",
        )
        assert stale_retry["code"] == "FIFO_TRANSITION_REVISION_CONFLICT"
        after = _transition_no_write_snapshot(repository)
        assert after["fifo_counts"] == baseline["fifo_counts"]
        assert after["case_revision"] == 5
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


def test_period_summary_catalog_and_finance_reads_share_ten_attempt_root_budget(
    tmp_path,
):
    from services.period_profit_operation_diagnostics import (
        current_period_profit_trace,
    )

    repository, tenant, _stock, bridge, _impact, cutover, _prepared, clock = (
        _prepared_repository(tmp_path, prepare=False)
    )
    try:
        reconstruction = _reconstruct(repository, bridge, cutover)
        assert reconstruction["error"] is False, reconstruction
        bundle = replace(_bundle(), finance_batch=object())
        service = _service(repository, bridge, cutover, bundle, clock)
        calls = {"catalog": 0, "collector": 0}

        def product_provider():
            trace = current_period_profit_trace()
            assert trace is not None
            for _ in range(11):
                calls["catalog"] += 1
                reservation = trace.reserve_ozon_request("product-list")
                if reservation["error"]:
                    break
            return []

        finance = SimpleNamespace(
            get_cached_daily_accruals=lambda *_args: {},
        )
        summary_service = SimpleNamespace(
            finance_service=finance,
            calculate=lambda *_args: {},
        )
        period_profit = SimpleNamespace(
            query_service=SimpleNamespace(
                product_provider=product_provider,
                summary_service=summary_service,
            ),
        )

        class Collector:
            def collect(self, **_kwargs):
                calls["collector"] += 1
                return {"error": False, "status": "COMPLETE"}

        result = service.collect_period_summaries(
            case_id=CASE_ID, identity=IDENTITY,
            expected_case_revision=3,
            summary_collection_service=Collector(),
            period_profit_service=period_profit,
            idempotency_key="period-summary-budget-0001",
        )

        assert result["code"] == "FIFO_PERIOD_SUMMARY_PRODUCTS_UNAVAILABLE"
        assert calls == {"catalog": 11, "collector": 0}
    finally:
        reset_current_tenant_user_id(tenant)


def test_period_summary_collection_reports_catalog_and_finance_attempts_together(
    tmp_path,
):
    from services.period_profit_operation_diagnostics import (
        current_period_profit_trace,
    )

    repository, tenant, _stock, bridge, _impact, cutover, _prepared, clock = (
        _prepared_repository(tmp_path, prepare=False)
    )
    try:
        reconstruction = _reconstruct(repository, bridge, cutover)
        assert reconstruction["error"] is False, reconstruction
        bundle = replace(_bundle(), finance_batch=object())
        service = _service(repository, bridge, cutover, bundle, clock)
        counters = {"catalog": 0, "finance": 0}

        def product_provider():
            trace = current_period_profit_trace()
            assert trace is not None
            assert trace.reserve_ozon_request("product-list")["error"] is False
            counters["catalog"] += 1
            return [{"product_id": "101"}]

        summary_service = SimpleNamespace(
            finance_service=SimpleNamespace(
                get_cached_daily_accruals=lambda *_args: {},
            ),
            calculate=lambda *_args: {},
        )
        period_profit = SimpleNamespace(
            query_service=SimpleNamespace(
                product_provider=product_provider,
                summary_service=summary_service,
            ),
        )

        class Collector:
            def collect(self, **kwargs):
                trace = current_period_profit_trace()
                assert trace is kwargs["parent_trace"]
                for _ in range(9):
                    assert trace.reserve_ozon_request("finance-day")["error"] is False
                    counters["finance"] += 1
                return {
                    "error": False,
                    "status": "COMPLETE",
                    "current_case_revision": 3,
                    "actual_http_attempts": trace.ozon_requests_reserved,
                    "http_attempt_cap": trace.ozon_request_budget,
                }

        result = service.collect_period_summaries(
            case_id=CASE_ID, identity=IDENTITY,
            expected_case_revision=3,
            summary_collection_service=Collector(),
            period_profit_service=period_profit,
            idempotency_key="period-summary-budget-0002",
        )

        assert result["error"] is False, result
        assert counters == {"catalog": 1, "finance": 9}
        assert result["actual_http_attempts"] == 10
        assert result["http_attempt_cap"] == 10
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


def test_apply_commits_exact_seal_and_recovers_same_commit_after_restart_and_ttl(
    tmp_path,
):
    repository, tenant, _stock, bridge, _impact, cutover, _prepared, clock = (
        _prepared_repository(tmp_path, prepare=False)
    )
    invalidation_calls = []

    def fail_cache_invalidation(**kwargs):
        invalidation_calls.append(kwargs)
        raise RuntimeError("simulated cache failure after commit")

    try:
        reconstruction = _reconstruct(repository, bridge, cutover)
        bundle = _bundle((_make_period_summary(reconstruction),))
        service = _service(
            repository, bridge, cutover, bundle, clock,
            cache_invalidator=fail_cache_invalidation,
        )
        prepared = service.prepare(
            case_id=CASE_ID, identity=IDENTITY,
            expected_case_revision=3,
            idempotency_key="apply-service-prepare-0001",
        )
        assert prepared["error"] is False, prepared
        assert prepared["preview_fingerprint"]

        real_evidence = FifoCostTransitionEvidenceService(
            service.transition_service,
        )
        sealed_basis = real_evidence.load(
            case_id=CASE_ID, identity=IDENTITY,
            expected_case_revision=3,
            # This case already has a FIFO stream; the saved seal must be
            # reviewed against its historical basis without asking for a new
            # opening composition.
            require_opening_composition=False,
            sealed_preview_id=prepared["preview_id"],
        )
        assert sealed_basis["error"] is False, sealed_basis
        assert sealed_basis["bundle"].case.case_revision == 3
        assert sealed_basis["missing_requirements"]
        class InitializedHistory(FifoCostHistoryService):
            def get_sku_history(self, **kwargs):
                result = super().get_sku_history(**kwargs)
                result["queue_initialized"] = True
                return result

        real_review = FifoCostTransitionReviewService(
            service.transition_service, InitializedHistory(repository),
            evidence_service=real_evidence,
        ).assess(
            case_id=CASE_ID, identity=IDENTITY,
            for_transition_prepare=True,
            sealed_preview_id=prepared["preview_id"],
        )
        assert real_review["error"] is False, real_review
        assert real_review["case_revision"] == 3
        assert real_review["current_case_revision"] == prepared["case_revision"]
        assert real_review["case_state"] == "READY_TO_CONFIRM"

        before_read = _transition_no_write_snapshot(repository)
        service.impact_service.preview = lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("read_preview must not recalculate impact"),
        )
        preview = service.read_preview(
            case_id=CASE_ID, identity=IDENTITY,
            preview_id=prepared["preview_id"],
        )
        assert preview["error"] is False, preview
        assert preview["is_current"] is True
        assert preview["preview_fingerprint"] == prepared["preview_fingerprint"]
        assert _transition_no_write_snapshot(repository) == before_read
        service.impact_service = FifoCostLateEntryImpactService(TaxService())

        applied = service.apply(
            case_id=CASE_ID, identity=IDENTITY,
            expected_case_revision=prepared["case_revision"],
            expected_preview_id=prepared["preview_id"],
            expected_preview_fingerprint=prepared["preview_fingerprint"],
            idempotency_key="apply-service-commit-0001",
        )
        assert applied["error"] is False, applied
        assert applied["code"] == "FIFO_TRANSITION_APPLIED"
        assert applied["replayed"] is False
        assert applied["cache_invalidation"] == "FAILED"
        assert len(invalidation_calls) == 1
        assert invalidation_calls[0]["identity"] == IDENTITY
        assert invalidation_calls[0]["case_id"] == CASE_ID
        assert invalidation_calls[0]["case_revision"] == prepared["case_revision"] + 1
        assert _table_counts(repository)["fifo_cost_transition_commits"] == 1
        current = repository.read_transition_case(
            case_id=CASE_ID, **IDENTITY,
        )
        assert current["state"] == "APPLIED"
        assert current["case_revision"] == prepared["case_revision"] + 1
        receipt = service.read_commit(case_id=CASE_ID, identity=IDENTITY)
        assert receipt["error"] is False, receipt
        assert receipt["commit_id"] == applied["commit_id"]
        assert receipt["complete_through"] == COMPLETE_THROUGH
        assert receipt["case_revision"] == current["case_revision"]

        retry_repository = FifoCostRepository(
            db_path=tmp_path / "transition-atomic.sqlite",
            now_provider=lambda: clock[0] + timedelta(days=2),
        )
        changed_tax = _TaxConfiguration({
            "error": False, "configured": True,
            "policy": {"mode": "USN_INCOME", "tax_rate": 6,
                       "minimum_tax_rate": 1},
        })
        retry_service = _service(
            retry_repository, bridge, cutover, bundle, clock,
            tax_configuration_service=changed_tax,
            cache_invalidator=fail_cache_invalidation,
        )
        restarted_receipt = retry_service.read_commit(
            case_id=CASE_ID, identity=IDENTITY,
        )
        assert restarted_receipt["error"] is False, restarted_receipt
        assert restarted_receipt["commit_id"] == applied["commit_id"]
        assert restarted_receipt["complete_through"] == COMPLETE_THROUGH
        retry = retry_service.apply(
            case_id=CASE_ID, identity=IDENTITY,
            expected_case_revision=prepared["case_revision"],
            expected_preview_id=prepared["preview_id"],
            expected_preview_fingerprint=prepared["preview_fingerprint"],
            idempotency_key="apply-service-commit-0001",
        )
        assert retry["error"] is False, retry
        assert retry["commit_id"] == applied["commit_id"]
        assert retry["replayed"] is True
        assert retry["cache_invalidation"] == "FAILED"
        assert len(invalidation_calls) == 2
        assert _table_counts(retry_repository)["fifo_cost_transition_commits"] == 1
        stale_new_key = retry_service.apply(
            case_id=CASE_ID, identity=IDENTITY,
            expected_case_revision=prepared["case_revision"],
            expected_preview_id=prepared["preview_id"],
            expected_preview_fingerprint=prepared["preview_fingerprint"],
            idempotency_key="apply-service-new-key-0001",
        )
        assert stale_new_key == {
            "error": True, "code": "FIFO_TRANSITION_PREVIEW_EXPIRED",
        }
        bad_retry = retry_service.apply(
            case_id=CASE_ID, identity=IDENTITY,
            expected_case_revision=prepared["case_revision"],
            expected_preview_id=prepared["preview_id"],
            expected_preview_fingerprint="f" * 64,
            idempotency_key="apply-service-commit-0001",
        )
        assert bad_retry["error"] is True
        assert bad_retry["code"] == "FIFO_TRANSITION_IDEMPOTENCY_CONFLICT"
        assert _table_counts(retry_repository)["fifo_cost_transition_commits"] == 1
    finally:
        reset_current_tenant_user_id(tenant)


def test_apply_same_key_concurrent_services_commit_one_transition(tmp_path):
    repository, tenant, _stock, bridge, _impact, cutover, _prepared, clock = (
        _prepared_repository(tmp_path, prepare=False)
    )
    barrier = Barrier(2)
    try:
        reconstruction = _reconstruct(repository, bridge, cutover)
        bundle = _bundle((_make_period_summary(reconstruction),))
        preparer = _service(repository, bridge, cutover, bundle, clock)
        prepared = preparer.prepare(
            case_id=CASE_ID, identity=IDENTITY,
            expected_case_revision=3,
            idempotency_key="apply-race-prepare-0001",
        )
        assert prepared["error"] is False, prepared

        class RacingReview(_ReadyReview):
            def assess(self, **kwargs):
                result = super().assess(**kwargs)
                barrier.wait(timeout=5)
                return result

        def apply_once(_index):
            request_tenant = set_current_tenant_user_id(TENANT)
            try:
                request_repository = FifoCostRepository(
                    db_path=tmp_path / "transition-atomic.sqlite",
                    now_provider=lambda: clock[0],
                )
                request_service = _service(
                    request_repository, bridge, cutover, bundle, clock,
                    review_service=RacingReview(),
                )
                return request_service.apply(
                    case_id=CASE_ID, identity=IDENTITY,
                    expected_case_revision=prepared["case_revision"],
                    expected_preview_id=prepared["preview_id"],
                    expected_preview_fingerprint=prepared["preview_fingerprint"],
                    idempotency_key="apply-race-confirm-0001",
                )
            finally:
                reset_current_tenant_user_id(request_tenant)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(apply_once, range(2)))
        assert all(result["error"] is False for result in results), results
        assert sorted(result["replayed"] for result in results) == [False, True]
        assert _table_counts(repository)["fifo_cost_transition_commits"] == 1
        assert _table_counts(repository)["fifo_cost_rate_changes"] == 1
        assert _table_counts(repository)["fifo_cost_allocations"] == 1
    finally:
        reset_current_tenant_user_id(tenant)
