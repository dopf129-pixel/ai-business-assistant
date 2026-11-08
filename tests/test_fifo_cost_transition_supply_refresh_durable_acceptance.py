from datetime import datetime, timezone

from cryptography.fernet import Fernet
import pytest

from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_source_collection_service import FifoSourceCollectionResult
from services.fifo_cost_source_normalizer import FifoCostSourceNormalizer
from services.fifo_cost_transition_review_service import FifoCostTransitionReviewService
from services.fifo_cost_transition_service import FifoCostTransitionService
from services.fifo_cost_transition_supply_refresh_service import (
    FifoCostTransitionSupplyRefreshService,
)
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


IDENTITY = {
    "store_id": "store-a",
    "product_id": "product-a",
    "offer_id": "hook-2",
    "sku": "3921245627",
}


class _SourceCollection:
    def __init__(self, active_snapshot, act_snapshot):
        self.active_snapshot = active_snapshot
        self.act_snapshot = act_snapshot

    def observe_active_supply_by_id(self, *_args, **_kwargs):
        snapshot = self.active_snapshot
        return FifoSourceCollectionResult(
            status=snapshot.status,
            source_status=snapshot.source_status,
            read_only=True,
            actual_http_attempts=1,
            http_attempt_cap=10,
            elapsed_seconds=0.01,
            source_fingerprint=snapshot.source_fingerprint,
            issue_codes=(),
            supply_snapshot=snapshot,
        )

    def find_supply_by_id(self, *_args, **_kwargs):
        snapshot = self.act_snapshot
        return FifoSourceCollectionResult(
            status=snapshot.status,
            source_status=snapshot.source_status,
            read_only=True,
            actual_http_attempts=1,
            http_attempt_cap=10,
            elapsed_seconds=0.01,
            source_fingerprint=snapshot.source_fingerprint,
            issue_codes=(),
            supply_snapshot=snapshot,
        )


@pytest.mark.parametrize("accepted_units", [0, 100])
def test_refresh_persists_acceptance_for_review_after_service_restart(
    tmp_path, monkeypatch, accepted_units,
):
    monkeypatch.setenv(
        "OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"),
    )
    tenant = set_current_tenant_user_id(make_store_tenant_scope("101", "store-a"))
    db_path = tmp_path / "transition-acceptance-restart.sqlite"
    now = lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
    try:
        repository = FifoCostRepository(db_path=db_path, now_provider=now)
        history = FifoCostHistoryService(repository)
        transition = FifoCostTransitionService(repository, now_provider=now)
        from services.telegram_fifo_cost_transition_runtime_service import (
            TelegramFifoCostTransitionRuntimeService,
        )

        runtime = TelegramFifoCostTransitionRuntimeService(
            transition, history, now_provider=now,
        )
        started = runtime.start_new_case(101, IDENTITY, "Hooks", 0, "TOTAL_LANDED")
        assert started["error"] is False, started
        case_id = runtime._sessions["101"]["case_id"]
        declared = transition.declare_supply(
            case_id=case_id, **IDENTITY, reference_kind="SUPPLY",
            reference_id="2001", declared_shipped_units=148,
            dispatch_date="2026-11-05", expected_case_revision=1,
            idempotency_key="durable-acceptance-declaration",
        )
        assert declared["error"] is False, declared
        declaration_id = transition.get_supply_manifest(
            case_id=case_id, **IDENTITY,
        )["declarations"][0]["declaration_id"]

        normalizer = FifoCostSourceNormalizer()
        supply_digest = transition.reference_digest_for_supply(
            owner_id="101", store_id="store-a", reference_id="2001",
        )
        active_snapshot = normalizer.normalize_active_supply_snapshot(
            supply_reference_digest=supply_digest,
            store_id="store-a",
            captured_at=datetime(2026, 11, 8, 11, tzinfo=timezone.utc),
            source_fingerprint="a" * 64,
            presence="PRESENT",
            raw_status="COMPLETED",
            order_id=11,
            scope_complete=True,
            pagination_complete=True,
            source_status="COMPLETE",
        )
        act_snapshot = normalizer.normalize_supply_act_snapshot(
            {"supply_acts": [{
                "type": "ACCEPTANCE",
                "act_id": 7001,
                "items": [{
                    "sku_info": {"sku": 3921245627},
                    "declared_quantity": 148,
                    "approved_quantity": 100,
                    "fact_quantity": accepted_units,
                    "unidentified_quantity": 0,
                }],
            }]},
            {"supplies_acts": [{
                "supply_id": 2001,
                "is_agreement_completed": True,
                "supply_acts": [{
                    "type": "ACCEPTANCE",
                    "act_state": "ACCEPTED",
                    "act_id": 7001,
                    "summary": {
                        "fact_quantity": accepted_units,
                        "unidentified_quantity": 0,
                    },
                }],
            }]},
            store_id="store-a", expected_supply_id=2001,
            expected_order_id=11,
            captured_at=datetime(2026, 11, 8, 11, 1, tzinfo=timezone.utc),
            products_complete=True, summary_complete=True,
        )
        assert act_snapshot.status in {"COMPLETE", "CONFIRMED_ZERO"}, act_snapshot
        assert act_snapshot.units_by_sku == ((IDENTITY["sku"], accepted_units),)

        refresh = FifoCostTransitionSupplyRefreshService(
            transition_service=transition,
            source_collection=_SourceCollection(active_snapshot, act_snapshot),
        )
        refreshed = refresh.refresh(
            case_id=case_id, declaration_id=declaration_id,
            reference_id="2001", **IDENTITY,
            expected_case_revision=declared["case_revision"],
        )
        assert refreshed.status == "COMPLETE", refreshed.issue_codes
        assert refreshed.case_revision == declared["case_revision"] + 1
        assert history.get_sku_history(**IDENTITY)["queue_initialized"] is False

        observations = repository.read_transition_evidence(
            case_id=case_id, **IDENTITY, kind="SUPPLY_OBSERVATION", limit=10,
        )
        assert observations["error"] is False
        assert len(observations["items"]) == 1
        assert observations["items"][0]["accepted_quantity"] == accepted_units
        assert observations["items"][0]["payload"]["accepted_quantity_kind"] == "DOCUMENT_LINES"
        assert len(observations["items"][0]["payload"]["act_evidence"]) == 1
        assert "2001" not in repr(observations)

        restarted_repository = FifoCostRepository(db_path=db_path, now_provider=now)
        restarted_history = FifoCostHistoryService(restarted_repository)
        restarted_transition = FifoCostTransitionService(
            restarted_repository, now_provider=now,
        )
        review = FifoCostTransitionReviewService(
            restarted_transition, restarted_history,
        )
        assessed = review.assess(case_id=case_id, identity=IDENTITY)

        assert assessed["error"] is False, assessed
        declaration = assessed["supply_reconciliation"].declarations[0]
        assert declaration.accepted_quantity == accepted_units
        assert declaration.acceptance_status == "DISCREPANCY"
        assert assessed["ready_to_apply"] is False
        assert assessed["preview_only"] is True
        assert assessed["fifo_queue_initialized"] is False
        assert restarted_repository.read_cost_history_snapshot(
            **IDENTITY,
        )["code"] == "FIFO_HISTORY_NOT_INITIALIZED"
    finally:
        reset_current_tenant_user_id(tenant)
