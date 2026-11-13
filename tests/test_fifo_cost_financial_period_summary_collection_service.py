from dataclasses import replace
from datetime import date, timedelta

from cryptography.fernet import Fernet

from services.fifo_cost_cutoff_bridge_service import (
    FifoCutoffBridgeEvent,
    FifoCutoffBridgeResult,
    FifoCutoffDescriptor,
    FifoFinanceSaleIdentity,
    FifoFinanceSaleIdentityBatch,
)
from services.fifo_cost_financial_period_summary_collection_service import (
    FifoCostFinancialPeriodSummaryCollectionService,
)
from services.fifo_cost_sale_evidence_normalizer import (
    FifoCostSaleEvidenceNormalizer,
)
from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    ScopeIdentity,
    SourceProof,
    TransitionMetadata,
)
from services.fifo_cost_transition_evidence_service import (
    FifoCostTransitionEvidenceService,
)
from services.fifo_cost_transition_service import FifoCostTransitionService
from services.ozon_account_repository import make_store_tenant_scope
from services.period_profit_operation_diagnostics import (
    current_period_profit_trace,
)
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.telegram_fifo_cost_transition_runtime_service import (
    TelegramFifoCostTransitionRuntimeService,
)


IDENTITY = {
    "store_id": "store-fr20",
    "product_id": "product-fr20",
    "offer_id": "offer-fr20",
    "sku": "3921245627",
}
PERIOD = "2026-11"


def _finance_batch():
    scope = ScopeIdentity(
        owner_id="owner-fr20", store_id=IDENTITY["store_id"],
        product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"],
        sku=IDENTITY["sku"],
    )
    fingerprint = "a" * 64
    metadata = TransitionMetadata(
        scope=scope, source_kind=EvidenceSourceKind.OZON_API,
        completeness=EvidenceCompleteness.COMPLETE,
        source_fingerprint=fingerprint,
    )
    proof = SourceProof(
        metadata=metadata, scope_complete=True, pagination_complete=True,
        source_as_of="2026-12-01T10:00:00Z",
    )
    return FifoFinanceSaleIdentityBatch(
        metadata=metadata, source_fingerprint=fingerprint,
        period_from="2026-11-01", period_to="2026-11-30",
        source_as_of=proof.source_as_of, proof=proof,
        rows=(FifoFinanceSaleIdentity(
            posting_number="synthetic-posting-fr20",
            finance_sku=IDENTITY["sku"],
            offer_id=IDENTITY["offer_id"],
            product_id=IDENTITY["product_id"],
            financial_period=PERIOD,
        ),),
    )


def _multi_month_inputs():
    batch = _finance_batch()
    rows = tuple(
        FifoFinanceSaleIdentity(
            posting_number=f"synthetic-posting-{period}",
            finance_sku=IDENTITY["sku"], offer_id=IDENTITY["offer_id"],
            product_id=IDENTITY["product_id"], financial_period=period,
        )
        for period in ("2026-10", "2026-11")
    )
    batch = FifoFinanceSaleIdentityBatch(
        metadata=batch.metadata, source_fingerprint=batch.source_fingerprint,
        period_from="2026-10-01", period_to="2026-11-30",
        source_as_of=batch.source_as_of, proof=batch.proof, rows=rows,
    )
    digests = {
        row.financial_period: FifoCostSaleEvidenceNormalizer.build_identity_digest(
            store_id=IDENTITY["store_id"], posting_number=row.posting_number,
            finance_sku=IDENTITY["sku"], identity={
                "mapping_confirmed": True, "offer_id": IDENTITY["offer_id"],
                "product_id": IDENTITY["product_id"],
            },
        )["source_identity_digest"]
        for row in rows
    }
    reconstruction = {
        "error": False, "code": "FIFO_LATE_ENTRY_RECONSTRUCTION_READY",
        "before_complete": True, "preview_fingerprint": "b" * 64,
        "sale_identity_digests_by_event": {
            f"event-{period}": digest for period, digest in digests.items()
        },
        "before_allocations": [
            {
                "event_id": f"event-{period}",
                "total_cost_rub": "43.40" if period == "2026-10" else "42.00",
            }
            for period in digests
        ],
    }
    return reconstruction, batch


def _inputs():
    digest = FifoCostSaleEvidenceNormalizer.build_identity_digest(
        store_id=IDENTITY["store_id"],
        posting_number="synthetic-posting-fr20",
        finance_sku=IDENTITY["sku"],
        identity={
            "mapping_confirmed": True,
            "offer_id": IDENTITY["offer_id"],
            "product_id": IDENTITY["product_id"],
        },
    )["source_identity_digest"]
    reconstruction = {
        "error": False,
        "code": "FIFO_LATE_ENTRY_RECONSTRUCTION_READY",
        "before_complete": True,
        "preview_fingerprint": "b" * 64,
        "sale_identity_digests_by_event": {"event-fr20": digest},
        "before_allocations": [{
            "event_id": "event-fr20", "total_cost_rub": "42.00",
        }],
    }
    policy = {
        "error": False, "configured": True,
        "policy": {
            "mode": "USN_INCOME", "tax_rate": 6.0,
            "minimum_tax_rate": 1.0,
        },
    }
    products = [{
        "product_id": IDENTITY["product_id"],
        "offer_id": IDENTITY["offer_id"], "sku": IDENTITY["sku"],
    }]
    return reconstruction, policy, products


def test_financial_period_mapping_partitions_full_batch_by_verified_cutoff_bridge():
    batch = _finance_batch()
    pre_row = FifoFinanceSaleIdentity(
        posting_number="synthetic-pre-cutoff-sale",
        finance_sku=IDENTITY["sku"], offer_id=IDENTITY["offer_id"],
        product_id=IDENTITY["product_id"], financial_period=PERIOD,
    )
    post_row = batch.rows[0]
    full_batch = FifoFinanceSaleIdentityBatch(
        metadata=batch.metadata, source_fingerprint=batch.source_fingerprint,
        period_from=batch.period_from, period_to=batch.period_to,
        source_as_of=batch.source_as_of, proof=batch.proof,
        rows=(pre_row, post_row),
    )

    def digest(row):
        return FifoCostSaleEvidenceNormalizer.build_identity_digest(
            store_id=IDENTITY["store_id"], posting_number=row.posting_number,
            finance_sku=row.finance_sku, identity={
                "mapping_confirmed": True,
                "offer_id": IDENTITY["offer_id"],
                "product_id": IDENTITY["product_id"],
            },
        )["source_identity_digest"]

    pre_digest, post_digest = digest(pre_row), digest(post_row)
    reconstruction = {
        "error": False, "code": "FIFO_LATE_ENTRY_RECONSTRUCTION_READY",
        "before_complete": True, "preview_fingerprint": "b" * 64,
        "sale_identity_digests_by_event": {"event-post": post_digest},
    }
    case_id = "case-fr20"
    cutoff_descriptor = FifoCutoffDescriptor(
        metadata=TransitionMetadata(
            scope=batch.metadata.scope,
            source_kind=EvidenceSourceKind.OWNER_INPUT,
            completeness=EvidenceCompleteness.COMPLETE,
            source_fingerprint="c" * 64,
        ),
        case_id=case_id, case_revision=3, cutoff_date="2026-11-06",
        timezone="Europe/Moscow", precision="STORE_LOCAL_DATE",
        boundary="END_OF_LOCAL_DATE",
    )
    bridge = FifoCutoffBridgeResult(
        status="READY", scope=batch.metadata.scope, case_id=case_id,
        case_revision=3, cutoff_descriptor=cutoff_descriptor,
        complete_through="2026-11-30", confirmed_stock_buckets={},
        pre_cutoff_outflows=(FifoCutoffBridgeEvent(
            source_identity_digest=pre_digest, quantity=1,
            physical_effective_date="2026-11-05",
            finance_source_fingerprint=batch.source_fingerprint,
            document_fingerprint="d" * 64,
            document_row_reference="pre-row-1",
        ),),
        post_cutoff_events=(FifoCutoffBridgeEvent(
            source_identity_digest=post_digest, quantity=1,
            physical_effective_date="2026-11-08",
            finance_source_fingerprint=batch.source_fingerprint,
            document_fingerprint="d" * 64,
            document_row_reference="post-row-1",
        ),),
        finance_to_sale_identity_mappings=(
            (pre_digest, batch.source_fingerprint),
            (post_digest, batch.source_fingerprint),
        ),
        linked_returns_non_sale_movements=(),
        source_set_fingerprint="e" * 64,
        unresolved_issues=(), provenance_by_basis={}, ready_for_fifo_event=True,
    )

    mapped = FifoCostFinancialPeriodSummaryCollectionService._digests_by_period(
        reconstruction, full_batch, IDENTITY, cutoff_bridge=bridge,
        case_id="case-fr20", expected_case_revision=3,
    )
    assert mapped == {PERIOD: (post_digest,)}
    assert FifoCostFinancialPeriodSummaryCollectionService._digests_by_period(
        reconstruction, full_batch, IDENTITY,
    ) == "FIFO_FINANCIAL_PERIOD_MAPPING_UNAVAILABLE"

    incomplete_bridge = replace(
        bridge, finance_to_sale_identity_mappings=(
            (post_digest, batch.source_fingerprint),
        ),
    )
    assert FifoCostFinancialPeriodSummaryCollectionService._digests_by_period(
        reconstruction, full_batch, IDENTITY,
        cutoff_bridge=incomplete_bridge, case_id="case-fr20",
        expected_case_revision=3,
    ) == "FIFO_FINANCIAL_PERIOD_MAPPING_UNAVAILABLE"


class _FinanceCache:
    def get_cached_daily_accruals(self, date_from, date_to):
        current = date.fromisoformat(date_from)
        end = date.fromisoformat(date_to)
        result = {}
        while current <= end:
            result[current.isoformat()] = {
                "error": False,
                "accruals": [{"amount": 1.25, "posting_number": "private"}],
                "last_id": "", "pages_loaded": 1,
            }
            current += timedelta(days=1)
        return result


class _Evidence:
    def __init__(self):
        self.saved = []
        self.case_revision = 3

    def record_period_profit_summary(self, **kwargs):
        if kwargs["expected_case_revision"] != self.case_revision:
            return {"error": True, "code": "FIFO_TRANSITION_REVISION_CONFLICT"}
        self.saved.append(kwargs)
        self.case_revision += 1
        return {
            "error": False, "code": "FIFO_PERIOD_SUMMARY_SNAPSHOT_SAVED",
            "case_revision": self.case_revision,
        }


def _reader(start, end, products):
    first = date.fromisoformat(start)
    last = date.fromisoformat(end)
    days = (last - first).days + 1
    trace = current_period_profit_trace()
    assert trace is not None
    assert trace.reserve_ozon_request("synthetic-period-profit") ["error"] is False
    return {
        "error": False,
        "date_from": start,
        "date_to": end,
        "revenue": 100.0 * days,
        "discount_points": 1.0 * days,
        "net_accrual": 75.0 * days,
        "product_cost": 10.0 * days,
        "sale_quantity_reconciled": True,
        "effective_cost_reconciled": True,
        "account_level_ozon_accruals_included": True,
        "product_revenue_reconciled": True,
        "fee_components_included": True,
        "fifo_cogs_reconciliation_required": False,
        "profit_scope": "SYNTHETIC_CANONICAL_SUMMARY",
        "products": [{
            "product_id": IDENTITY["product_id"],
            "offer_id": IDENTITY["offer_id"], "sku": IDENTITY["sku"],
            "product_cost": 1.4 * days,
        }],
    }


def _collect(service, evidence, *, token=None, reader=_reader, reconstruction=None,
             finance=None, products=None, expected_case_revision=None,
             existing_summaries=()):
    default_reconstruction, policy, default_products = _inputs()
    return service.collect(
        case_id="case-fr20-1", identity=IDENTITY,
        expected_case_revision=(
            evidence.case_revision if expected_case_revision is None
            else expected_case_revision
        ),
        reconstruction=reconstruction or default_reconstruction,
        finance_batch=finance or _finance_batch(),
        products=products or default_products,
        tax_policy_result=policy,
        summary_reader=reader,
        finance_service=_FinanceCache(), evidence_service=evidence,
        continuation_token=token,
        existing_summaries=existing_summaries,
    )


def test_complete_month_is_persisted_only_after_all_bounded_chunks():
    service = FifoCostFinancialPeriodSummaryCollectionService()
    evidence = _Evidence()
    reader_errors = []

    def reader(*args):
        try:
            return _reader(*args)
        except Exception as error:
            reader_errors.append(repr(error))
            raise

    result = _collect(service, evidence, reader=reader)

    assert result["error"] is False
    assert result["status"] == "PARTIAL"
    assert result["days_collected_this_call"] == 4, (
        reader_errors, result.get("issue_code"),
        result.get("actual_http_attempts"), result,
    )
    assert result["actual_http_attempts"] == 1
    assert evidence.saved == []

    token = result["continuation_token"]
    while token:
        result = _collect(service, evidence, token=token)
        token = result["continuation_token"]

    assert result["status"] == "COMPLETE"
    assert result["periods_complete_this_call"] == 1
    assert len(evidence.saved) == 1
    summary = evidence.saved[0]["summary"].as_impact_summary()
    assert summary["period"] == PERIOD
    assert summary["revenue"] == "3000.00"
    assert summary["current_total_product_cost"] == "300.00"
    assert summary["current_sku_product_cost"] == "42.00"
    assert summary["sale_identity_digests"] == [
        FifoCostSaleEvidenceNormalizer.build_identity_digest(
            store_id=IDENTITY["store_id"],
            posting_number="synthetic-posting-fr20",
            finance_sku=IDENTITY["sku"],
            identity={
                "mapping_confirmed": True,
                "offer_id": IDENTITY["offer_id"],
                "product_id": IDENTITY["product_id"],
            },
        )["source_identity_digest"]
    ]


def test_collection_refuses_to_freeze_when_exact_before_cost_is_missing():
    reconstruction, _policy, _products = _inputs()
    reconstruction["before_complete"] = False
    evidence = _Evidence()
    reader_calls = []

    def reader(*args):
        reader_calls.append(args)
        return _reader(*args)

    result = _collect(
        FifoCostFinancialPeriodSummaryCollectionService(), evidence,
        reconstruction=reconstruction, reader=reader,
    )

    assert result["error"] is True
    assert result["code"] == "FIFO_FINANCIAL_PERIOD_MAPPING_UNAVAILABLE"
    assert reader_calls == []
    assert evidence.saved == []


def test_collection_does_not_save_when_daily_source_cache_has_a_gap():
    class IncompleteCache:
        def get_cached_daily_accruals(self, date_from, date_to):
            return {}

    evidence = _Evidence()
    result = FifoCostFinancialPeriodSummaryCollectionService().collect(
        case_id="case-fr20-1", identity=IDENTITY, expected_case_revision=3,
        reconstruction=_inputs()[0], finance_batch=_finance_batch(),
        products=_inputs()[2], tax_policy_result=_inputs()[1],
        summary_reader=_reader, finance_service=IncompleteCache(),
        evidence_service=evidence,
    )

    assert result["error"] is False
    assert result["status"] == "PARTIAL"
    assert result["issue_code"] == "FIFO_PERIOD_SUMMARY_DAILY_SOURCE_INCOMPLETE"
    assert evidence.saved == []


def test_failed_month_snapshot_write_can_resume_without_double_counting_last_chunk():
    class FailOnceEvidence(_Evidence):
        def __init__(self):
            super().__init__()
            self.fail = True

        def record_period_profit_summary(self, **kwargs):
            if self.fail:
                self.fail = False
                return {"error": True, "code": "SYNTHETIC_WRITE_FAILURE"}
            return super().record_period_profit_summary(**kwargs)

    service = FifoCostFinancialPeriodSummaryCollectionService()
    evidence = FailOnceEvidence()
    token = None
    for _ in range(8):
        result = _collect(service, evidence, token=token)
        token = result["continuation_token"]

    assert result["status"] == "PARTIAL"
    assert result["issue_code"] == "SYNTHETIC_WRITE_FAILURE"
    assert token

    retried = _collect(service, evidence, token=token)

    assert retried["status"] == "COMPLETE"
    assert len(evidence.saved) == 1
    assert evidence.saved[0]["summary"].as_impact_summary()["revenue"] == "3000.00"


def test_continuation_is_bound_to_revision_and_rejects_cross_case_reuse():
    service = FifoCostFinancialPeriodSummaryCollectionService()
    evidence = _Evidence()
    first = _collect(service, evidence)
    assert first["continuation_token"]

    second = service.collect(
        case_id="case-fr20-other", identity=IDENTITY, expected_case_revision=3,
        reconstruction=_inputs()[0], finance_batch=_finance_batch(),
        products=_inputs()[2], tax_policy_result=_inputs()[1],
        summary_reader=_reader, finance_service=_FinanceCache(),
        evidence_service=evidence, continuation_token=first["continuation_token"],
    )

    assert second["error"] is True
    assert second["code"] == "FIFO_PERIOD_SUMMARY_CONTINUATION_SCOPE_MISMATCH"
    assert evidence.saved == []


def test_multiple_month_snapshots_advance_case_revision_between_months():
    reconstruction, finance = _multi_month_inputs()
    evidence = _Evidence()
    service = FifoCostFinancialPeriodSummaryCollectionService()
    result = _collect(
        service, evidence, reconstruction=reconstruction, finance=finance,
    )
    for _ in range(40):
        token = result.get("continuation_token")
        if not token:
            break
        result = _collect(
            service, evidence, token=token, reconstruction=reconstruction,
            finance=finance,
        )

    assert result["status"] == "COMPLETE", (
        result.get("issue_code"), result.get("current_case_revision"),
        result.get("days_collected_this_call"), result.get("periods_complete_this_call"),
    )
    assert result["current_case_revision"] == 5
    assert [
        item["summary"].as_impact_summary()["period"]
        for item in evidence.saved
    ] == ["2026-10", "2026-11"]
    assert [item["expected_case_revision"] for item in evidence.saved] == [3, 4]
    assert evidence.case_revision == 5


def test_continuation_rejects_owner_revision_change_after_partial_collection():
    service = FifoCostFinancialPeriodSummaryCollectionService()
    evidence = _Evidence()
    first = _collect(service, evidence)
    assert first["continuation_token"]
    assert first["current_case_revision"] == 3

    # Simulate another owner action appending a case revision between calls.
    evidence.case_revision = 4
    reader_calls = []

    def reader(*args):
        reader_calls.append(args)
        return _reader(*args)

    resumed = _collect(
        service, evidence, token=first["continuation_token"], reader=reader,
        expected_case_revision=4,
    )

    assert resumed["error"] is True
    assert resumed["code"] == "FIFO_TRANSITION_REVISION_CONFLICT"
    assert reader_calls == []
    assert evidence.saved == []


def test_multi_month_collection_persists_through_real_case_revision_cas(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    tenant = set_current_tenant_user_id(
        make_store_tenant_scope("owner-fr20", IDENTITY["store_id"]),
    )
    database = tmp_path / "multi-month-period-summary.sqlite"
    try:
        repository = FifoCostRepository(db_path=database)
        history = FifoCostHistoryService(repository)
        transition = FifoCostTransitionService(repository)
        runtime = TelegramFifoCostTransitionRuntimeService(transition, history)
        created = runtime.start_new_case(
            101, IDENTITY, "Synthetic FR20 Multi-Month", 0, "TOTAL_LANDED",
        )
        assert created["error"] is False, created
        case_id = runtime._sessions["101"]["case_id"]
        evidence = FifoCostTransitionEvidenceService(transition)
        collector = FifoCostFinancialPeriodSummaryCollectionService()
        reconstruction, finance = _multi_month_inputs()
        policy = _inputs()[1]
        products = _inputs()[2]
        case = transition.get_case(case_id=case_id, **IDENTITY)
        assert case["error"] is False, case
        expected_revision = case["case_revision"]
        token = None
        result = None
        restarted_after_snapshot = False
        for _ in range(40):
            result = collector.collect(
                case_id=case_id, identity=IDENTITY,
                expected_case_revision=expected_revision,
                reconstruction=reconstruction, finance_batch=finance,
                products=products, tax_policy_result=policy,
                summary_reader=_reader, finance_service=_FinanceCache(),
                evidence_service=evidence, continuation_token=token,
            )
            assert result["error"] is False, result
            expected_revision = result["current_case_revision"]
            token = result["continuation_token"]
            if token is None:
                break
            current = transition.get_case(case_id=case_id, **IDENTITY)
            assert current["error"] is False, current
            loaded = evidence.load(
                case_id=case_id, identity=IDENTITY,
                expected_case_revision=current["case_revision"],
            )
            assert loaded["error"] is False, loaded
            if len(loaded["bundle"].period_summaries) == 1:
                # Simulate a process restart after October was durably frozen.
                # A fresh collector has no in-memory continuation checkpoint;
                # it must replay October for verification without appending it.
                expected_revision = current["case_revision"]
                existing_summaries = loaded["bundle"].period_summaries
                collector = FifoCostFinancialPeriodSummaryCollectionService()
                restarted_after_snapshot = True
                token = None
                for _ in range(40):
                    result = collector.collect(
                        case_id=case_id, identity=IDENTITY,
                        expected_case_revision=expected_revision,
                        reconstruction=reconstruction, finance_batch=finance,
                        products=products, tax_policy_result=policy,
                        summary_reader=_reader, finance_service=_FinanceCache(),
                        evidence_service=evidence,
                        existing_summaries=existing_summaries,
                        continuation_token=token,
                    )
                    assert result["error"] is False, result
                    expected_revision = result["current_case_revision"]
                    token = result["continuation_token"]
                    if token is None:
                        break
                break

        assert restarted_after_snapshot is True
        assert result["status"] == "COMPLETE", result
        current = transition.get_case(case_id=case_id, **IDENTITY)
        assert current["case_revision"] == 3
        loaded = evidence.load(
            case_id=case_id, identity=IDENTITY,
            expected_case_revision=current["case_revision"],
        )
        assert loaded["error"] is False, loaded
        summaries = loaded["bundle"].period_summaries
        assert [summary.period_from[:7] for summary in summaries] == [
            "2026-10", "2026-11",
        ]
    finally:
        reset_current_tenant_user_id(tenant)


def test_restart_with_different_chunking_and_http_budget_revalidates_same_snapshots():
    reconstruction, finance = _multi_month_inputs()
    evidence = _Evidence()
    products = _inputs()[2]
    policy = _inputs()[1]
    service = FifoCostFinancialPeriodSummaryCollectionService()
    token = None
    for _ in range(100):
        result = service.collect(
            case_id="case-fr20-1", identity=IDENTITY,
            expected_case_revision=evidence.case_revision,
            reconstruction=reconstruction, finance_batch=finance,
            products=products, tax_policy_result=policy,
            summary_reader=_reader, finance_service=_FinanceCache(),
            evidence_service=evidence, continuation_token=token,
            days_per_call=1, http_attempt_budget=1,
        )
        assert result["error"] is False, result
        token = result["continuation_token"]
        if token is None:
            break

    assert result["status"] == "COMPLETE", result
    assert len(evidence.saved) == 2
    frozen_summaries = tuple(item["summary"] for item in evidence.saved)
    revision_after_freeze = evidence.case_revision

    # A new collector has no original chunk schedule. Re-read the same dated
    # facts in four-day chunks and with a larger request budget; v2 fingerprints
    # must remain independent of those transport boundaries.
    restarted = FifoCostFinancialPeriodSummaryCollectionService()
    token = None
    for _ in range(100):
        result = restarted.collect(
            case_id="case-fr20-1", identity=IDENTITY,
            expected_case_revision=revision_after_freeze,
            reconstruction=reconstruction, finance_batch=finance,
            products=products, tax_policy_result=policy,
            summary_reader=_reader, finance_service=_FinanceCache(),
            evidence_service=evidence, continuation_token=token,
            existing_summaries=frozen_summaries,
            days_per_call=4, http_attempt_budget=10,
        )
        assert result["error"] is False, result
        token = result["continuation_token"]
        if token is None:
            break

    assert result["status"] == "COMPLETE", result
    assert result["issue_code"] is None
    assert evidence.case_revision == revision_after_freeze
    assert len(evidence.saved) == 2


def test_collection_rejects_non_month_finance_identity_rows():
    batch = _finance_batch()
    invalid_row = FifoFinanceSaleIdentity(
        posting_number="synthetic-posting-fr20", finance_sku=IDENTITY["sku"],
        offer_id=IDENTITY["offer_id"], product_id=IDENTITY["product_id"],
        financial_period=None,
    )
    invalid_batch = FifoFinanceSaleIdentityBatch(
        metadata=batch.metadata, source_fingerprint=batch.source_fingerprint,
        period_from=batch.period_from, period_to=batch.period_to,
        source_as_of=batch.source_as_of, proof=batch.proof,
        rows=(invalid_row,),
    )
    evidence = _Evidence()
    result = _collect(
        FifoCostFinancialPeriodSummaryCollectionService(), evidence,
        finance=invalid_batch,
    )

    assert result["error"] is True
    assert result["code"] == "FIFO_FINANCIAL_PERIOD_MAPPING_UNAVAILABLE"
    assert evidence.saved == []


def test_collection_rejects_finance_identity_for_another_product():
    batch = _finance_batch()
    other_product_row = FifoFinanceSaleIdentity(
        posting_number="synthetic-posting-fr20", finance_sku=IDENTITY["sku"],
        offer_id="another-offer", product_id="another-product",
        financial_period=PERIOD,
    )
    invalid_batch = FifoFinanceSaleIdentityBatch(
        metadata=batch.metadata, source_fingerprint=batch.source_fingerprint,
        period_from=batch.period_from, period_to=batch.period_to,
        source_as_of=batch.source_as_of, proof=batch.proof,
        rows=(other_product_row,),
    )
    evidence = _Evidence()
    result = _collect(
        FifoCostFinancialPeriodSummaryCollectionService(), evidence,
        finance=invalid_batch,
    )

    assert result["error"] is True
    assert result["code"] == "FIFO_FINANCIAL_PERIOD_MAPPING_CONFLICT"
    assert evidence.saved == []


def test_collection_rejects_finance_batch_from_another_store():
    batch = _finance_batch()
    other_scope = ScopeIdentity(
        owner_id="owner-fr20", store_id="other-store",
        product_id=IDENTITY["product_id"], offer_id=IDENTITY["offer_id"],
        sku=IDENTITY["sku"],
    )
    fingerprint = "f" * 64
    metadata = TransitionMetadata(
        scope=other_scope, source_kind=EvidenceSourceKind.OZON_API,
        completeness=EvidenceCompleteness.COMPLETE,
        source_fingerprint=fingerprint,
    )
    proof = SourceProof(
        metadata=metadata, scope_complete=True, pagination_complete=True,
        source_as_of="2026-12-01T10:00:00Z",
    )
    other_batch = FifoFinanceSaleIdentityBatch(
        metadata=metadata, source_fingerprint=fingerprint,
        period_from=batch.period_from, period_to=batch.period_to,
        source_as_of=proof.source_as_of, proof=proof, rows=batch.rows,
    )
    evidence = _Evidence()
    result = _collect(
        FifoCostFinancialPeriodSummaryCollectionService(), evidence,
        finance=other_batch,
    )

    assert result["error"] is True
    assert result["code"] == "FIFO_FINANCIAL_PERIOD_MAPPING_SCOPE_MISMATCH"
    assert evidence.saved == []
