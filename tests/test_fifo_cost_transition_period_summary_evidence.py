from datetime import datetime, timezone

from cryptography.fernet import Fernet

from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_transition_contracts import (
    FifoFinancialPeriodSummary,
    TransitionBridgeEvidenceKind,
)
from services.fifo_cost_transition_evidence_service import (
    FifoCostTransitionEvidenceService,
)
from services.fifo_cost_transition_service import FifoCostTransitionService
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.telegram_fifo_cost_transition_runtime_service import (
    TelegramFifoCostTransitionRuntimeService,
)


IDENTITY = {
    "store_id": "store-fr20-period",
    "product_id": "product-fr20-period",
    "offer_id": "offer-fr20-period",
    "sku": "3921245627",
}
TENANT = make_store_tenant_scope("owner-fr20-period", IDENTITY["store_id"])


def _summary(*, fingerprint="a" * 64, revenue="1000.00"):
    return FifoFinancialPeriodSummary(
        period_from="2026-11-01",
        period_to="2026-11-30",
        source_fingerprint=fingerprint,
        reconstruction_fingerprint="b" * 64,
        tax_policy_fingerprint="c" * 64,
        sale_identity_digests=("d" * 64,),
        revenue_rub=revenue,
        discount_points_rub="25.00",
        net_accrual_rub="750.00",
        current_total_product_cost_rub="100.00",
        current_sku_product_cost_rub="42.00",
    )


def _make_case(database, now):
    repository = FifoCostRepository(db_path=database, now_provider=now)
    history = FifoCostHistoryService(repository)
    transition = FifoCostTransitionService(repository, now_provider=now)
    runtime = TelegramFifoCostTransitionRuntimeService(
        transition, history, now_provider=now,
    )
    created = runtime.start_new_case(
        101, IDENTITY, "Synthetic FR20", 0, "TOTAL_LANDED",
    )
    assert created["error"] is False, created
    return repository, transition, runtime._sessions["101"]["case_id"]


def _revision(transition, case_id):
    result = transition.get_case(case_id=case_id, **IDENTITY)
    assert result["error"] is False, result
    return result["case_revision"]


def test_period_profit_summary_snapshot_is_encrypted_and_rehydrates_after_restart(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    tenant = set_current_tenant_user_id(TENANT)
    now = lambda: datetime(2026, 12, 2, 12, tzinfo=timezone.utc)
    database = tmp_path / "period-summary.sqlite"
    try:
        repository, transition, case_id = _make_case(database, now)
        evidence = FifoCostTransitionEvidenceService(transition)
        saved = evidence.record_period_profit_summary(
            case_id=case_id,
            identity=IDENTITY,
            summary=_summary(),
            expected_case_revision=_revision(transition, case_id),
            idempotency_key="fr20-period-summary-1",
        )
        assert saved["error"] is False, saved

        restarted_repository = FifoCostRepository(db_path=database, now_provider=now)
        restarted_transition = FifoCostTransitionService(
            restarted_repository, now_provider=now,
        )
        restarted_evidence = FifoCostTransitionEvidenceService(restarted_transition)
        loaded = restarted_evidence.load(
            case_id=case_id,
            identity=IDENTITY,
            expected_case_revision=_revision(restarted_transition, case_id),
        )
        assert loaded["error"] is False, loaded
        assert len(loaded["bundle"].period_summaries) == 1
        impact_row = loaded["bundle"].period_summaries[0].as_impact_summary()
        assert impact_row["period"] == "2026-11"
        assert impact_row["current_sku_product_cost"] == "42.00"
        assert impact_row["current_total_product_cost"] == "100.00"

        public = restarted_repository.read_transition_bridge_evidence(
            case_id=case_id,
            **IDENTITY,
            evidence_kind=TransitionBridgeEvidenceKind.PERIOD_SUMMARY_SNAPSHOT,
            limit=10,
        )
        assert public["error"] is False, public
        assert "3921245627" not in repr(public)
        assert "d" * 64 not in repr(public)
        assert "current_sku_product_cost" not in repr(public)
    finally:
        reset_current_tenant_user_id(tenant)


def test_conflicting_frozen_summaries_for_same_financial_period_fail_closed(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    tenant = set_current_tenant_user_id(TENANT)
    now = lambda: datetime(2026, 12, 2, 12, tzinfo=timezone.utc)
    database = tmp_path / "period-summary-conflict.sqlite"
    try:
        _repository, transition, case_id = _make_case(database, now)
        evidence = FifoCostTransitionEvidenceService(transition)
        first = evidence.record_period_profit_summary(
            case_id=case_id, identity=IDENTITY, summary=_summary(),
            expected_case_revision=_revision(transition, case_id),
            idempotency_key="fr20-period-summary-first",
        )
        assert first["error"] is False, first
        second = evidence.record_period_profit_summary(
            case_id=case_id, identity=IDENTITY,
            summary=_summary(fingerprint="e" * 64, revenue="1001.00"),
            expected_case_revision=_revision(transition, case_id),
            idempotency_key="fr20-period-summary-second",
        )
        assert second["error"] is False, second

        loaded = evidence.load(
            case_id=case_id, identity=IDENTITY,
            expected_case_revision=_revision(transition, case_id),
        )
        assert loaded["error"] is False, loaded
        assert "FINANCIAL_PERIOD_SUMMARY_VERSION_CONFLICT" in (
            loaded["missing_requirements"]
        )
        assert loaded["bundle"].period_summaries == ()
    finally:
        reset_current_tenant_user_id(tenant)
