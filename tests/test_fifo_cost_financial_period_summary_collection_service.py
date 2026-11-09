from datetime import date, timedelta

from services.fifo_cost_cutoff_bridge_service import (
    FifoFinanceSaleIdentity,
    FifoFinanceSaleIdentityBatch,
)
from services.fifo_cost_financial_period_summary_collection_service import (
    FifoCostFinancialPeriodSummaryCollectionService,
)
from services.fifo_cost_sale_evidence_normalizer import (
    FifoCostSaleEvidenceNormalizer,
)
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    ScopeIdentity,
    SourceProof,
    TransitionMetadata,
)
from services.period_profit_operation_diagnostics import (
    current_period_profit_trace,
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

    def record_period_profit_summary(self, **kwargs):
        self.saved.append(kwargs)
        return {"error": False, "code": "FIFO_PERIOD_SUMMARY_SNAPSHOT_SAVED"}


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
             finance=None, products=None):
    default_reconstruction, policy, default_products = _inputs()
    return service.collect(
        case_id="case-fr20-1", identity=IDENTITY, expected_case_revision=3,
        reconstruction=reconstruction or default_reconstruction,
        finance_batch=finance or _finance_batch(),
        products=products or default_products,
        tax_policy_result=policy,
        summary_reader=reader,
        finance_service=_FinanceCache(), evidence_service=evidence,
        continuation_token=token,
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
