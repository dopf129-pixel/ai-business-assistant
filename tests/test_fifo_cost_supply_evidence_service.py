from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_source_normalizer import FifoCostSourceNormalizer
from services.fifo_cost_supply_evidence_service import FifoCostSupplyEvidenceService
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


IDENTITY = {"product_id": "101", "offer_id": "hook-2", "sku": "3921245627"}
STORE = "store-a"


def _snapshot(*, fact=100, capture_day=6, order_id=11, supply_id=2001, act_id=3001):
    products = {"supply_acts": [{
        "act_id": act_id,
        "type": "ACCEPTANCE",
        "items": [{
            "sku_info": {"sku": int(IDENTITY["sku"])},
            "declared_quantity": 200,
            "approved_quantity": 0,
            "fact_quantity": fact,
            "unidentified_quantity": 0,
        }],
    }]}
    summary = {"supplies_acts": [{
        "supply_id": supply_id,
        "is_agreement_completed": True,
        "supply_acts": [{
            "act_id": act_id,
            "type": "ACCEPTANCE",
            "act_state": "ACCEPTED",
            "created_date": "2026-09-28",
            "summary": {"fact_quantity": fact, "unidentified_quantity": 0},
        }],
    }]}
    return FifoCostSourceNormalizer().normalize_supply_act_snapshot(
        products,
        summary,
        store_id=STORE,
        expected_supply_id=supply_id,
        expected_order_id=order_id,
        captured_at=datetime(2026, 11, capture_day, 12, tzinfo=timezone.utc),
        products_complete=True,
        summary_complete=True,
    )


def _anchor_stream(repository):
    preview = repository.preview_command(
        store_id=STORE,
        product_id=IDENTITY["product_id"],
        offer_id=IDENTITY["offer_id"],
        sku=IDENTITY["sku"],
        events=[{
            "kind": "OPENING_FIFO_ANCHOR",
            "quantity": 2,
            "unit_cost_rub": "10.00",
            "effective_date": "2026-11-01",
            "inventory_cutoff": "2026-11-01",
            "location_to": "OZON",
        }],
        source={
            "kind": "OWNER_CONFIRMATION",
            "method": "OWNER_CONFIRMED_FIFO_CUTOFF",
            "status": "OWNER_CONFIRMED",
            "provenance": "OWNER_CONFIRMED",
            "coverage_status": "OWNER_CONFIRMED",
            "captured_at": "2026-11-06T12:00:00Z",
            "inventory_cutoff": "2026-11-01",
        },
    )
    assert preview["error"] is False
    committed = repository.commit_command(
        preview_id=preview["preview_id"],
        active_preview_id=preview["preview_id"],
        idempotency_key="fifo-anchor-fixture-1",
    )
    assert committed["error"] is False


@pytest.fixture
def scoped_repository(tmp_path):
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-1", STORE))
    repository = FifoCostRepository(
        db_path=tmp_path / "fifo-supply-evidence.sqlite",
        now_provider=lambda: datetime(2026, 11, 6, 12, tzinfo=timezone.utc),
    )
    _anchor_stream(repository)
    try:
        yield repository
    finally:
        reset_current_tenant_user_id(token)


def _record(service, snapshot):
    return service.record_collected_supply(
        collection_result=SimpleNamespace(
            read_only=True,
            status=snapshot.status,
            supply_snapshot=snapshot,
        ),
        store_id=STORE,
        product_id=IDENTITY["product_id"],
        offer_id=IDENTITY["offer_id"],
        sku=IDENTITY["sku"],
    )


def test_partial_acceptance_is_linked_as_evidence_without_fifo_receipt(scoped_repository):
    service = FifoCostSupplyEvidenceService(scoped_repository)
    result = _record(service, _snapshot())

    assert result == {
        "error": False,
        "code": "FIFO_SUPPLY_EVIDENCE_RECORDED",
        "idempotent": False,
        "evidence_sequence": 1,
        "stream_revision": 1,
        "accepted_units": 100,
        "act_count": 1,
    }
    history = service.read_history(
        store_id=STORE, product_id=IDENTITY["product_id"],
        offer_id=IDENTITY["offer_id"], sku=IDENTITY["sku"],
    )
    assert len(history["snapshots"]) == 1
    act = history["snapshots"][0]["acts"][0]
    assert act["declared_quantity"] == 200
    assert act["approved_quantity"] == 0
    assert act["fact_quantity"] == 100
    assert act["created_date"] == "2026-09-28"
    assert act["created_date_kind"] == "DOCUMENT_CREATED_DATE_ONLY"
    assert history["snapshots"][0]["physical_effective_date"] is None
    assert history["snapshots"][0]["physical_effective_at"] is None

    connection = scoped_repository.get_connection()
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_supply_evidence"
        ).fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM fifo_cost_events").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM fifo_cost_layers").fetchone()[0] == 1
        refs = {
            (row[0], row[1])
            for row in connection.execute(
                """SELECT reference_kind, reference_digest
                   FROM fifo_cost_source_refs AS r
                   JOIN fifo_cost_supply_evidence AS e ON e.source_id=r.source_id"""
            )
        }
        assert {kind for kind, _ in refs} == {"ORDER", "SUPPLY"}
        source_fingerprint = connection.execute(
            """SELECT s.source_fingerprint
               FROM fifo_cost_sources AS s
               JOIN fifo_cost_supply_evidence AS e ON e.source_id=s.source_id"""
        ).fetchone()[0]
        evidence_source_fingerprint = connection.execute(
            "SELECT source_fingerprint FROM fifo_cost_supply_evidence"
        ).fetchone()[0]
        assert source_fingerprint == evidence_source_fingerprint
        payload = json.loads(connection.execute(
            "SELECT normalized_evidence_json FROM fifo_cost_supply_evidence"
        ).fetchone()[0])
        stored_strings = {
            value for value in payload.values() if isinstance(value, str)
        }
        stored_strings.update(
            value for act in payload["act_evidence"] for value in act.values()
            if isinstance(value, str)
        )
        for raw_id in ("11", "2001", "3001"):
            assert raw_id not in stored_strings
    finally:
        connection.close()


def test_late_entry_draft_is_revision_bound_append_only_and_does_not_change_fifo(scoped_repository):
    service = FifoCostSupplyEvidenceService(scoped_repository)
    snapshot = _snapshot()
    before = scoped_repository.read_cost_history_snapshot(
        store_id=STORE, product_id=IDENTITY["product_id"],
        offer_id=IDENTITY["offer_id"], sku=IDENTITY["sku"],
    )

    result = service.record_late_entry_draft(
        store_id=STORE,
        product_id=IDENTITY["product_id"],
        offer_id=IDENTITY["offer_id"],
        sku=IDENTITY["sku"],
        expected_revision=before["revision"],
        snapshot=snapshot,
        owner_effective_date="2026-10-16",
        owner_old_home_units=12,
        purchase_cost_rub="20.00",
        delivery_cost_rub="2.50",
        packaging_cost_rub="1.25",
    )
    assert result["error"] is False
    assert result["unit_cost_rub"] == "23.75"
    assert result["accepted_units"] == 100
    assert result["owner_effective_date"] == "2026-10-16"

    again = service.record_late_entry_draft(
        store_id=STORE,
        product_id=IDENTITY["product_id"],
        offer_id=IDENTITY["offer_id"],
        sku=IDENTITY["sku"],
        expected_revision=before["revision"],
        snapshot=snapshot,
        owner_effective_date="2026-10-16",
        owner_old_home_units=12,
        purchase_cost_rub="20.00",
        delivery_cost_rub="2.50",
        packaging_cost_rub="1.25",
    )
    assert again["error"] is False
    assert again["idempotent"] is True
    assert again["draft_id"] == result["draft_id"]

    history = service.read_late_entry_drafts(
        store_id=STORE, product_id=IDENTITY["product_id"],
        offer_id=IDENTITY["offer_id"], sku=IDENTITY["sku"],
    )
    assert len(history["drafts"]) == 1
    draft = history["drafts"][0]
    assert draft["owner_effective_date"] == "2026-10-16"
    assert draft["accepted_units"] == 100
    assert draft["owner_old_home_units"] == 12
    assert draft["unit_cost_rub"] == "23.75"
    assert "2001" not in str(draft)
    assert "3001" not in str(draft)

    after = scoped_repository.read_cost_history_snapshot(
        store_id=STORE, product_id=IDENTITY["product_id"],
        offer_id=IDENTITY["offer_id"], sku=IDENTITY["sku"],
    )
    assert after["revision"] == before["revision"]
    assert after["layers"] == before["layers"]
    assert after["rates"] == before["rates"]


def test_late_entry_draft_rejects_stale_stream_revision(scoped_repository):
    service = FifoCostSupplyEvidenceService(scoped_repository)
    snapshot = _snapshot()
    result = service.record_late_entry_draft(
        store_id=STORE,
        product_id=IDENTITY["product_id"],
        offer_id=IDENTITY["offer_id"],
        sku=IDENTITY["sku"],
        expected_revision=0,
        snapshot=snapshot,
        owner_effective_date="2026-10-16",
        owner_old_home_units=0,
        purchase_cost_rub="20",
        delivery_cost_rub="0",
        packaging_cost_rub="0",
    )
    assert result == {"error": True, "code": "FIFO_REVISION_CONFLICT"}
    history = service.read_late_entry_drafts(
        store_id=STORE, product_id=IDENTITY["product_id"],
        offer_id=IDENTITY["offer_id"], sku=IDENTITY["sku"],
    )
    assert history["drafts"] == []


def test_repeated_refresh_is_idempotent_and_changed_act_is_new_evidence_only(scoped_repository):
    service = FifoCostSupplyEvidenceService(scoped_repository)
    first = _snapshot(fact=100, capture_day=6)
    same_facts = _snapshot(fact=100, capture_day=7)
    changed_act = _snapshot(fact=120, capture_day=7)

    assert _record(service, first)["idempotent"] is False
    assert _record(service, same_facts)["idempotent"] is True
    assert _record(service, changed_act)["idempotent"] is False

    history = service.read_history(
        store_id=STORE, product_id=IDENTITY["product_id"],
        offer_id=IDENTITY["offer_id"], sku=IDENTITY["sku"],
    )
    assert [item["accepted_units"] for item in history["snapshots"]] == [100, 120]
    assert [item["evidence_sequence"] for item in history["snapshots"]] == [1, 2]
    connection = scoped_repository.get_connection()
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_supply_evidence"
        ).fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM fifo_cost_events").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM fifo_cost_layers").fetchone()[0] == 1
        assert connection.execute(
            "SELECT revision FROM fifo_cost_streams"
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_non_complete_or_non_read_only_collection_never_persists(scoped_repository):
    service = FifoCostSupplyEvidenceService(scoped_repository)
    snapshot = _snapshot()
    for result in (
        SimpleNamespace(read_only=True, status="PARTIAL", supply_snapshot=snapshot),
        SimpleNamespace(read_only=False, status="COMPLETE", supply_snapshot=snapshot),
        SimpleNamespace(read_only=True, status="COMPLETE", supply_snapshot=None),
    ):
        response = service.record_collected_supply(
            collection_result=result,
            store_id=STORE,
            product_id=IDENTITY["product_id"],
            offer_id=IDENTITY["offer_id"],
            sku=IDENTITY["sku"],
        )
        assert response["error"] is True

    connection = scoped_repository.get_connection()
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_supply_evidence"
        ).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM fifo_cost_events").fetchone()[0] == 1
    finally:
        connection.close()


def test_evidence_is_bound_to_exact_store_and_sku(scoped_repository):
    service = FifoCostSupplyEvidenceService(scoped_repository)
    snapshot = _snapshot()
    wrong_sku = service.record_collected_supply(
        collection_result=SimpleNamespace(
            read_only=True, status="COMPLETE", supply_snapshot=snapshot,
        ),
        store_id=STORE,
        product_id=IDENTITY["product_id"],
        offer_id=IDENTITY["offer_id"],
        sku="3921245628",
    )
    wrong_store = service.record_collected_supply(
        collection_result=SimpleNamespace(
            read_only=True, status="COMPLETE", supply_snapshot=snapshot,
        ),
        store_id="store-b",
        product_id=IDENTITY["product_id"],
        offer_id=IDENTITY["offer_id"],
        sku=IDENTITY["sku"],
    )

    assert wrong_sku["code"] == "FIFO_SUPPLY_SKU_IDENTITY_MISMATCH"
    assert wrong_store["code"] == "FIFO_STORE_SCOPE_MISMATCH"


def test_supply_evidence_rows_reject_update_and_delete(scoped_repository):
    assert _record(FifoCostSupplyEvidenceService(scoped_repository), _snapshot())["error"] is False
    connection = scoped_repository.get_connection()
    try:
        with pytest.raises(Exception, match="append-only"):
            connection.execute(
                "UPDATE fifo_cost_supply_evidence SET source_status='PARTIAL'"
            )
        with pytest.raises(Exception, match="append-only"):
            connection.execute("DELETE FROM fifo_cost_supply_evidence")
    finally:
        connection.close()
