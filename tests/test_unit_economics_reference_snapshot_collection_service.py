from datetime import datetime, timezone
from contextlib import contextmanager

from services.ozon_account_repository import make_store_tenant_scope
from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.planning_unit_economics_experiment_adapter import (
    PlanningUnitEconomicsExperimentAdapter,
)
from services.unit_economics_reference_snapshot_collection_service import (
    UnitEconomicsReferenceSnapshotCollectionService,
)
from services.unit_economics_window_snapshot_service import UnitEconomicsWindowSnapshotService
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


IDENTITY = {
    "owner_id": "owner-1", "store_id": "store-a", "product_id": "product-1",
    "offer_id": "offer-1", "sku": "sku-1", "sale_schema": "FBO",
}


class EvidenceCollector:
    def __init__(self, *, finance_status="COMPLETE", returns_status="COMPLETE",
                 acquiring="-1.00"):
        self.finance_status = finance_status
        self.returns_status = returns_status
        self.acquiring = acquiring
        self.calls = []

    def collect_reference_window(self, identity, *, date_from, date_to, timezone_name):
        self.calls.append((identity, date_from, date_to, timezone_name))
        return {
            "error": False,
            "window": {"from": date_from, "to": date_to, "timezone": timezone_name},
            "sources": [
                {"name": "FINANCE", "status": self.finance_status,
                 "unsupported_types": []},
                {"name": "RETURNS", "status": self.returns_status},
            ],
            "metrics": {
                "acquiring": self.acquiring, "commission": "-2.00",
                "logistics": "-3.00", "other_fees": "-4.00",
                "ordered_units": 100 if self.returns_status == "COMPLETE" else None,
            },
            "diagnostics": {
                "elapsed_seconds": 8, "collection_http_attempts": 57,
                "budget_reason_code": "NONE",
            },
        }


def _service(tmp_path, collector):
    repository = PlanningWorkspaceRepository(db_path=tmp_path / "planning.sqlite")
    service = UnitEconomicsReferenceSnapshotCollectionService(
        repository, collector,
        clock=lambda: datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc),
    )
    return repository, service


@contextmanager
def _tenant_scope():
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-1", "store-a"))
    try:
        yield
    finally:
        reset_current_tenant_user_id(token)


def test_complete_reference_evidence_is_saved_as_exact_56_day_reconciliation_snapshot(tmp_path):
    collector = EvidenceCollector()
    repository, service = _service(tmp_path, collector)
    spec = UnitEconomicsWindowSnapshotService.reference_window("2026-10-30", "Europe/Moscow")
    evidence = collector.collect_reference_window(
        IDENTITY, date_from=spec["window"]["from_date"],
        date_to=spec["window"]["to_date"], timezone_name="Europe/Moscow",
    )
    projection = service._build_snapshot(spec, IDENTITY, evidence)
    assert projection["error"] is False
    normalized = PlanningUnitEconomicsExperimentAdapter.normalize_expense_snapshot(
        {"schema_version": 1, "identity": IDENTITY, "readiness": projection["readiness"]},
        {"owner_id": "owner-1", "store_id": "store-a"},
    )
    assert normalized is not None, projection["readiness"]
    collector.calls.clear()

    with _tenant_scope():
        result = service.collect(
            IDENTITY, owner_id="owner-1", store_id="store-a",
            timezone_name="Europe/Moscow",
        )

        assert result["error"] is False, result
        assert result["status"] == "COMPLETE"
        assert result["read_only"] is True
        assert result["source_io"] is True
        assert (result["window"]["to_date"] == "2026-10-29")
        assert (result["window"]["from_date"] == "2026-09-04")
        assert len(collector.calls) == 1
        stored = repository.get_unit_economics_expense_snapshot(
            result["snapshot_id"], owner_id="owner-1", store_id="store-a",
        )
        assert stored["error"] is False
        assert stored["payload"]["readiness"]["status"] == "COMPLETE"
        assert stored["payload"]["readiness"]["scope_kind"] == "REFERENCE_56_COMPLETED_LOCAL_DAYS"
        assert stored["payload"]["readiness"]["coverage_complete"] is True
        assert all(component["source"] == "OZON_SELLER_FINANCE"
                   and component["applicability"] == "RECONCILIATION_ONLY"
                   for component in stored["payload"]["readiness"]["components"])


def test_partial_returns_never_persist_a_complete_reference_snapshot(tmp_path):
    collector = EvidenceCollector(returns_status="PARTIAL")
    repository, service = _service(tmp_path, collector)

    with _tenant_scope():
        result = service.collect(
            IDENTITY, owner_id="owner-1", store_id="store-a",
            timezone_name="Europe/Moscow",
        )

        assert result["error"] is False, result
        assert result["status"] == "PARTIAL"
        assert result["reason_code"] == "RETURNS_PARTIAL"
        listed = repository.list_unit_economics_expense_snapshots(
            identity=IDENTITY, owner_id="owner-1", store_id="store-a", limit=10,
        )
        assert listed["error"] is False
        assert listed["items"] == []


def test_credit_expense_component_requires_review_and_is_not_saved_as_zero(tmp_path):
    collector = EvidenceCollector(acquiring="2.50")
    repository, service = _service(tmp_path, collector)

    with _tenant_scope():
        result = service.collect(
            IDENTITY, owner_id="owner-1", store_id="store-a",
            timezone_name="Europe/Moscow",
        )

        assert result["error"] is False, result
        assert result["status"] == "PARTIAL"
        assert result["reason_code"] == "EXPENSE_CREDIT_REQUIRES_REVIEW"
        listed = repository.list_unit_economics_expense_snapshots(
            identity=IDENTITY, owner_id="owner-1", store_id="store-a", limit=10,
        )
        assert listed["items"] == []
