import sqlite3
from datetime import datetime, timezone
from dataclasses import replace

import pytest

from services.fifo_cost_anchor_service import FifoCostAnchorService
from services.fifo_cost_history_service import FifoCostHistoryService
from services.fifo_cost_rate_service import FifoCostRateService
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_source_normalizer import FifoStockSnapshot
from services.fifo_cost_source_normalizer import FifoCostSourceNormalizer
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


IDENTITY = {
    "store_id": "store-a",
    "product_id": "product-101",
    "offer_id": "hook-2",
    "sku": "3921245627",
}


def _layers():
    return [
        {"sequence": 1, "unit_cost_rub": "5.00", "ozon_units": 10,
         "transit_units": 0, "home_units": 0},
        {"sequence": 2, "unit_cost_rub": "10.00", "ozon_units": 5,
         "transit_units": 2, "home_units": 0},
    ]


def _setup(tmp_path):
    repository = FifoCostRepository(
        db_path=tmp_path / "fifo-rates.sqlite",
        now_provider=lambda: datetime(2026, 11, 6, 12, tzinfo=timezone.utc),
    )
    service = FifoCostRateService(repository)
    anchor = FifoCostAnchorService(
        repository,
        now_provider=lambda: datetime(2026, 11, 6, 12, tzinfo=timezone.utc),
    )
    preview = anchor.preview_opening_anchor(
        **IDENTITY,
        inventory_cutoff="2026-11-05",
        cost_layers=_layers(),
        ozon_units_include_reserved_confirmed=True,
        transit_not_in_ozon_confirmed=True,
    )
    assert preview["error"] is False
    committed = anchor.commit_opening_anchor(
        preview_id=preview["preview_id"],
        active_preview_id=preview["preview_id"],
        idempotency_key="anchor-for-rate01",
    )
    assert committed["error"] is False
    return repository, service


def _preview(service, **overrides):
    payload = {
        **IDENTITY,
        "effective_date": "2026-11-07",
        "purchase_cost_rub": "12.00",
        "delivery_cost_rub": "2.00",
        "packaging_cost_rub": "1.00",
        "old_home_units": 0,
        "expected_revision": 1,
    }
    payload.update(overrides)
    return service.preview_new_cost(**payload)


def _stock_snapshot(*, date="2026-11-08", fbo=20, reserved=4, transit=0,
                    source_fingerprint="a" * 64, status="COMPLETE"):
    return FifoStockSnapshot(
        status=status,
        source_status="COMPLETE" if status == "COMPLETE" else status,
        store_id=IDENTITY["store_id"],
        product_id=IDENTITY["product_id"],
        offer_id=IDENTITY["offer_id"],
        sku=IDENTITY["sku"],
        captured_at=f"{date}T12:00:00Z",
        source_as_of=None,
        pagination_complete=True,
        pages_read=1,
        total_items=1,
        fbo_units=fbo,
        reserved_units=reserved,
        available_units=fbo - reserved,
        transit_units=transit,
        transit_status="DISJOINT_CONFIRMED",
        source_fingerprint=source_fingerprint,
        issue_codes=(),
        anchor_eligible=False,
    )


@pytest.fixture
def scoped_rate_service(tmp_path):
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-1", "store-a"))
    try:
        yield _setup(tmp_path)
    finally:
        reset_current_tenant_user_id(token)


def test_new_rate_preview_keeps_unknown_quantity_separate_and_does_not_write(
    scoped_rate_service,
):
    repository, service = scoped_rate_service
    preview = _preview(service)

    assert preview["error"] is False
    assert preview["code"] == "FIFO_RATE_PREVIEW_READY"
    assert preview["unit_cost_rub"] == "15.00"
    assert preview["finite_units_at_anchor"] == 17
    assert preview["owner_old_home_units"] == 0
    assert preview["inventory_units_added"] == 0
    assert preview["new_batch_quantity"] is None
    assert preview["threshold_status"] == "INVENTORY_CUTOFF_UNRECONCILED"

    connection = repository.get_connection()
    try:
        assert connection.execute("SELECT COUNT(*) FROM fifo_cost_rate_changes").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM fifo_cost_events").fetchone()[0] == 3
        projection = connection.execute(
            "SELECT revision, known_quantity, known_cost_rub, next_unit_cost_rub, "
            "queue_complete, cutoff_status FROM fifo_cost_projections"
        ).fetchone()
        assert tuple(projection) == (
            1, 17, "120.00", "5.00", 1, "INVENTORY_CUTOFF_UNRECONCILED",
        )
    finally:
        connection.close()


def test_confirmed_rate_is_append_only_idempotent_and_not_a_stock_layer(
    scoped_rate_service,
):
    repository, service = scoped_rate_service
    preview = _preview(service, old_home_units=7)
    result = service.confirm_new_cost(
        preview_id=preview["preview_id"],
        active_preview_id=preview["preview_id"],
        idempotency_key="confirm-new-rate01",
    )
    assert result == {
        "error": False,
        "code": "FIFO_RATE_COMMITTED",
        "idempotent": False,
        "revision": 2,
        "rate_sequence": 1,
        "unit_cost_rub": "15.00",
        "owner_old_home_units": 7,
    }
    repeated = service.confirm_new_cost(
        preview_id=preview["preview_id"],
        active_preview_id=preview["preview_id"],
        idempotency_key="confirm-new-rate01",
    )
    assert repeated["idempotent"] is True
    assert repeated["revision"] == 2

    connection = repository.get_connection()
    try:
        row = connection.execute(
            "SELECT stream_revision, rate_sequence, effective_date, unit_cost_rub, "
            "purchase_cost_rub, delivery_cost_rub, packaging_cost_rub, "
            "owner_old_home_units FROM fifo_cost_rate_changes"
        ).fetchone()
        assert tuple(row) == (2, 1, "2026-11-07", "15.00", "12.00", "2.00", "1.00", 7)
        assert connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_layers"
        ).fetchone()[0] == 3
        assert connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_events"
        ).fetchone()[0] == 3
        stream = connection.execute(
            "SELECT state, revision FROM fifo_cost_streams"
        ).fetchone()
        assert tuple(stream) == ("FIFO_PARTIAL", 2)
        projection = connection.execute(
            "SELECT state, revision, known_quantity, known_cost_rub, "
            "next_unit_cost_rub, queue_complete, cutoff_status "
            "FROM fifo_cost_projections"
        ).fetchone()
        assert tuple(projection) == (
            "FIFO_PARTIAL", 2, 17, "120.00", "5.00", 0,
            "INVENTORY_CUTOFF_UNRECONCILED",
        )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE fifo_cost_rate_changes SET unit_cost_rub='99.00'"
            )
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"old_home_units": None}, "FIFO_RATE_OLD_HOME_QUANTITY_INVALID"),
        ({"old_home_units": True}, "FIFO_RATE_OLD_HOME_QUANTITY_INVALID"),
        ({"old_home_units": -1}, "FIFO_RATE_OLD_HOME_QUANTITY_INVALID"),
        ({"purchase_cost_rub": 12.25}, "FIFO_MONEY_INPUT_INVALID"),
        ({"effective_date": "2026-11-07T00:00:00"}, "FIFO_RATE_EFFECTIVE_DATE_INVALID"),
        ({"expected_revision": 0}, "FIFO_REVISION_CONFLICT"),
    ],
)
def test_invalid_rate_inputs_fail_before_write(scoped_rate_service, overrides, code):
    repository, service = scoped_rate_service
    result = _preview(service, **overrides)
    assert result == {"error": True, "code": code}
    connection = repository.get_connection()
    try:
        assert connection.execute("SELECT COUNT(*) FROM fifo_cost_rate_changes").fetchone()[0] == 0
        assert connection.execute("SELECT revision FROM fifo_cost_streams").fetchone()[0] == 1
    finally:
        connection.close()


def test_later_rate_preserves_fifo_order_and_rejects_old_effective_date(scoped_rate_service):
    repository, service = scoped_rate_service
    first = _preview(service)
    first_result = service.confirm_new_cost(
        preview_id=first["preview_id"],
        active_preview_id=first["preview_id"],
        idempotency_key="first-rate-change01",
    )
    assert first_result["error"] is False
    repository._now_provider = lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
    later = _preview(
        service,
        effective_date="2026-11-08",
        expected_revision=2,
        purchase_cost_rub="20.00",
        stock_snapshot=_stock_snapshot(fbo=20, reserved=4),
        owner_confirms_reconciliation_scope=True,
    )
    assert later["error"] is False
    assert later["rate_sequence"] == 2
    assert later["prior_rate_unit_cost_rub"] == "15.00"
    assert later["rate_reconciliation"]["older_finite_units"] == 17
    assert later["rate_reconciliation"]["prior_rate_units"] == 3
    earlier = _preview(
        service,
        effective_date="2026-11-06",
        expected_revision=2,
    )
    assert earlier == {"error": True, "code": "FIFO_RATE_DATE_ORDER_UNRESOLVED"}
    same_day = _preview(
        service,
        effective_date="2026-11-07",
        expected_revision=2,
    )
    assert same_day == {"error": True, "code": "FIFO_RATE_DATE_ORDER_UNRESOLVED"}


def test_fc23_equal_date_with_last_finite_layer_is_unresolved(scoped_rate_service):
    _repository, service = scoped_rate_service
    same_day = _preview(service, effective_date="2026-11-05")
    assert same_day == {"error": True, "code": "FIFO_RATE_DATE_ORDER_UNRESOLVED"}


def test_fc23_future_stock_snapshot_cannot_activate_rate_automatically(
    scoped_rate_service,
):
    repository, service = scoped_rate_service
    first = _preview(service)
    committed = service.confirm_new_cost(
        preview_id=first["preview_id"],
        active_preview_id=first["preview_id"],
        idempotency_key="future-anchor-base01",
    )
    assert committed["error"] is False

    future = _preview(
        service,
        effective_date="2026-11-08",
        expected_revision=2,
        stock_snapshot=_stock_snapshot(
            date="2026-11-08", fbo=20, reserved=4,
        ),
        owner_confirms_reconciliation_scope=True,
    )

    assert future == {
        "error": True,
        "code": "FIFO_RATE_RECONCILIATION_FUTURE_SNAPSHOT",
    }
    snapshot = repository.read_cost_history_snapshot(**IDENTITY)
    assert snapshot["revision"] == 2
    assert len(snapshot["rates"]) == 1
    assert snapshot["rate_reconciliations"] == []


def test_fc14_third_and_fourth_prices_reconcile_only_the_previous_open_rate(tmp_path):
    repository = FifoCostRepository(
        db_path=tmp_path / "four-price-transitions.sqlite",
        now_provider=lambda: datetime(2026, 11, 6, 12, tzinfo=timezone.utc),
    )
    rate_service = FifoCostRateService(repository)
    anchor_service = FifoCostAnchorService(
        repository,
        now_provider=lambda: datetime(2026, 11, 6, 12, tzinfo=timezone.utc),
    )
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-1", "store-a"))
    try:
        anchor = anchor_service.preview_opening_anchor(
            **IDENTITY,
            inventory_cutoff="2026-11-05",
            cost_layers=[{
                "sequence": 1,
                "unit_cost_rub": "20.00",
                "ozon_units": 150,
                "transit_units": 0,
                "home_units": 0,
            }],
            ozon_units_include_reserved_confirmed=True,
            transit_not_in_ozon_confirmed=True,
        )
        anchored = anchor_service.commit_opening_anchor(
            preview_id=anchor["preview_id"],
            active_preview_id=anchor["preview_id"],
            idempotency_key="four-price-anchor01",
        )
        assert anchored["error"] is False

        second_price = rate_service.preview_new_cost(
            **IDENTITY, effective_date="2026-11-06",
            purchase_cost_rub="25.00", delivery_cost_rub="0.00",
            packaging_cost_rub="0.00", old_home_units=0, expected_revision=1,
        )
        second_saved = rate_service.confirm_new_cost(
            preview_id=second_price["preview_id"],
            active_preview_id=second_price["preview_id"],
            idempotency_key="four-price-rate-two",
        )
        assert second_saved["error"] is False

        repository._now_provider = lambda: datetime(
            2026, 11, 7, 12, tzinfo=timezone.utc,
        )

        third_price = rate_service.preview_new_cost(
            **IDENTITY, effective_date="2026-11-07",
            purchase_cost_rub="30.00", delivery_cost_rub="0.00",
            packaging_cost_rub="0.00", old_home_units=50, expected_revision=2,
            stock_snapshot=_stock_snapshot(
                date="2026-11-07", fbo=300, reserved=40, source_fingerprint="b" * 64,
            ),
            owner_confirms_reconciliation_scope=True,
        )
        assert third_price["error"] is False
        assert third_price["rate_reconciliation"]["reconciled_total_units"] == 350
        assert third_price["rate_reconciliation"]["older_finite_units"] == 150
        assert third_price["rate_reconciliation"]["prior_rate_units"] == 200
        third_saved = rate_service.confirm_new_cost(
            preview_id=third_price["preview_id"],
            active_preview_id=third_price["preview_id"],
            idempotency_key="four-price-rate-three",
        )
        assert third_saved["error"] is False
        assert third_saved["reconciled_previous_rate_units"] == 200

        repository._now_provider = lambda: datetime(
            2026, 11, 8, 12, tzinfo=timezone.utc,
        )

        unexplained_lower_count = rate_service.preview_new_cost(
            **IDENTITY, effective_date="2026-11-08",
            purchase_cost_rub="40.00", delivery_cost_rub="0.00",
            packaging_cost_rub="0.00", old_home_units=50, expected_revision=3,
            stock_snapshot=_stock_snapshot(
                date="2026-11-08", fbo=290, reserved=40, source_fingerprint="d" * 64,
            ),
            owner_confirms_reconciliation_scope=True,
        )
        assert unexplained_lower_count == {
            "error": True, "code": "FIFO_RATE_STOCK_DISCREPANCY",
        }
        unchanged = repository.read_cost_history_snapshot(**IDENTITY)
        assert [rate["unit_cost_rub"] for rate in unchanged["rates"]] == [
            "25.00", "30.00",
        ]
        assert unchanged["projection"]["known_quantity"] == 350

        fourth_price = rate_service.preview_new_cost(
            **IDENTITY, effective_date="2026-11-08",
            purchase_cost_rub="40.00", delivery_cost_rub="0.00",
            packaging_cost_rub="0.00", old_home_units=50, expected_revision=3,
            stock_snapshot=_stock_snapshot(
                date="2026-11-08", fbo=360, reserved=40, transit=10,
                source_fingerprint="c" * 64,
            ),
            owner_confirms_reconciliation_scope=True,
        )
        assert fourth_price["error"] is False
        assert fourth_price["rate_reconciliation"]["older_finite_units"] == 350
        assert fourth_price["rate_reconciliation"]["prior_rate_units"] == 70
        fourth_saved = rate_service.confirm_new_cost(
            preview_id=fourth_price["preview_id"],
            active_preview_id=fourth_price["preview_id"],
            idempotency_key="four-price-rate-four",
        )
        assert fourth_saved["error"] is False

        history = repository.read_cost_history_snapshot(**IDENTITY)
        assert [rate["unit_cost_rub"] for rate in history["rates"]] == [
            "25.00", "30.00", "40.00",
        ]
        assert [item["prior_rate_units"] for item in history["rate_reconciliations"]] == [
            200, 70,
        ]
        connection = repository.get_connection()
        try:
            assert [row[0] for row in connection.execute(
                "SELECT source_fingerprint FROM fifo_cost_rate_reconciliations "
                "ORDER BY transition_rate_sequence"
            )] == ["b" * 64, "c" * 64]
        finally:
            connection.close()
        assert history["layers"] == [{
            "sequence": 1,
            "recorded_quantity": 150,
            "unit_cost_rub": "20.00",
            "effective_date": "2026-11-05",
            "provenance": "OWNER_CONFIRMED",
            "location": "OZON",
            "source_status": "OWNER_CONFIRMED",
            "coverage_status": "OWNER_CONFIRMED",
        }]
        assert history["projection"]["known_quantity"] == 420
        assert history["projection"]["known_cost_rub"] == "10100.00"
        assert history["projection"]["next_unit_cost_rub"] == "20.00"
        history_view = FifoCostHistoryService(repository).get_sku_history(
            **IDENTITY, as_of_date="2026-11-09",
        )
        assert [rate["reconciled_quantity"] for rate in history_view["rates"]] == [
            200, 70, None,
        ]

        connection = repository.get_connection()
        try:
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                connection.execute(
                    "UPDATE fifo_cost_rate_reconciliations SET prior_rate_units=1"
                )
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_fc14_missing_or_partial_stock_evidence_cannot_advance_second_rate(scoped_rate_service):
    repository, service = scoped_rate_service
    first = _preview(service)
    committed = service.confirm_new_cost(
        preview_id=first["preview_id"],
        active_preview_id=first["preview_id"],
        idempotency_key="first-rate-change01",
    )
    assert committed["error"] is False

    missing = _preview(service, effective_date="2026-11-08", expected_revision=2)
    assert missing == {"error": True, "code": "FIFO_RATE_RECONCILIATION_REQUIRED"}
    incomplete = _preview(
        service,
        effective_date="2026-11-08",
        expected_revision=2,
        stock_snapshot=_stock_snapshot(status="PARTIAL"),
        owner_confirms_reconciliation_scope=True,
    )
    assert incomplete == {
        "error": True, "code": "FIFO_RATE_RECONCILIATION_SOURCE_INCOMPLETE",
    }
    connection = repository.get_connection()
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_rate_changes"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_rate_reconciliations"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT revision FROM fifo_cost_streams"
        ).fetchone()[0] == 2
    finally:
        connection.close()


def test_fc14_lower_total_is_conflict_and_does_not_shrink_older_layer(scoped_rate_service):
    repository, service = scoped_rate_service
    first = _preview(service)
    committed = service.confirm_new_cost(
        preview_id=first["preview_id"],
        active_preview_id=first["preview_id"],
        idempotency_key="first-rate-change01",
    )
    assert committed["error"] is False
    repository._now_provider = lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
    too_low = _preview(
        service,
        effective_date="2026-11-08",
        expected_revision=2,
        old_home_units=0,
        stock_snapshot=_stock_snapshot(
            date="2026-11-08", fbo=16, reserved=0, source_fingerprint="d" * 64,
        ),
        owner_confirms_reconciliation_scope=True,
    )
    assert too_low == {"error": True, "code": "FIFO_RATE_RECONCILIATION_CONFLICT"}
    connection = repository.get_connection()
    try:
        assert tuple(connection.execute(
            "SELECT quantity, unit_cost_rub FROM fifo_cost_layers ORDER BY layer_sequence"
        ).fetchone()) == (10, "5.00")
        assert connection.execute(
            "SELECT COUNT(*) FROM fifo_cost_rate_reconciliations"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT revision FROM fifo_cost_streams"
        ).fetchone()[0] == 2
    finally:
        connection.close()


def test_rate_before_opening_cutoff_is_rejected(scoped_rate_service):
    _repository, service = scoped_rate_service
    earlier = _preview(service, effective_date="2026-11-04")
    assert earlier == {"error": True, "code": "FIFO_RATE_DATE_ORDER_UNRESOLVED"}


def test_cost_revision_change_after_preview_rejects_rate_confirmation(scoped_rate_service):
    repository, service = scoped_rate_service
    rate_preview = _preview(service)
    receipt_preview = repository.preview_command(
        **IDENTITY,
        events=[{
            "kind": "COST_LAYER_RECEIPT",
            "quantity": 1,
            "unit_cost_rub": "25.00",
            "effective_date": "2026-11-07",
        }],
        source={
            "kind": "OWNER_CONFIRMATION",
            "method": "OWNER_CONFIRMED_TEST_RECEIPT",
            "status": "OWNER_CONFIRMED",
            "completeness": "OWNER_CONFIRMED",
            "provenance": "OWNER_CONFIRMED",
            "coverage_status": "OWNER_CONFIRMED",
            "captured_at": "2026-11-06T12:00:00Z",
            "references": [],
        },
        expected_revision=1,
    )
    assert receipt_preview["error"] is False
    receipt = repository.commit_command(
        preview_id=receipt_preview["preview_id"],
        active_preview_id=receipt_preview["preview_id"],
        idempotency_key="receipt-wins-race01",
    )
    assert receipt["error"] is False

    stale = service.confirm_new_cost(
        preview_id=rate_preview["preview_id"],
        active_preview_id=rate_preview["preview_id"],
        idempotency_key="rate-loses-race01",
    )
    assert stale == {"error": True, "code": "FIFO_REVISION_CONFLICT"}
    connection = repository.get_connection()
    try:
        assert connection.execute("SELECT COUNT(*) FROM fifo_cost_rate_changes").fetchone()[0] == 0
        assert connection.execute("SELECT revision FROM fifo_cost_streams").fetchone()[0] == 2
    finally:
        connection.close()


def test_cost_rate_preview_is_bound_to_store_and_active_revision(scoped_rate_service):
    repository, service = scoped_rate_service
    preview = _preview(service)
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-1", "store-b"))
    try:
        wrong_store = repository.commit_cost_rate_change(
            preview_id=preview["preview_id"],
            active_preview_id=preview["preview_id"],
            idempotency_key="wrong-store-rate01",
        )
        assert wrong_store == {"error": True, "code": "FIFO_STORE_SCOPE_MISMATCH"}
    finally:
        reset_current_tenant_user_id(token)

    replacement = _preview(service, expected_revision=1, old_home_units=3)
    assert replacement["error"] is False
    stale = service.confirm_new_cost(
        preview_id=preview["preview_id"],
        active_preview_id=preview["preview_id"],
        idempotency_key="stale-old-rate01",
    )
    assert stale == {"error": True, "code": "FIFO_PREVIEW_STALE"}


def test_n02_confirmed_zero_inventory_anchors_first_rate_without_fake_layer(tmp_path):
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-1", "store-a"))
    try:
        repository = FifoCostRepository(
            db_path=tmp_path / "fifo-zero-rate.sqlite",
            now_provider=lambda: datetime(2026, 11, 6, 12, tzinfo=timezone.utc),
        )
        service = FifoCostRateService(repository)
        snapshot = FifoCostSourceNormalizer().normalize_stock_snapshot(
            {
                "total_items": 1,
                "items": [{
                    "product_id": 101,
                    "stocks": [
                        {"type": "fbo", "present": 0, "reserved": 0},
                        {"type": "fbs", "present": 0, "reserved": 0},
                    ],
                }],
            },
            identity={"product_id": "101", "offer_id": "hook-2", "sku": "3921245627"},
            store_id="store-a",
            captured_at=datetime(2026, 11, 6, 12, tzinfo=timezone.utc),
            pagination_complete=True,
            pages_read=1,
            identity_mapping_confirmed=True,
            field_semantics_confirmed=True,
            transit_units=0,
            transit_complete=True,
            transit_overlap_confirmed=True,
        )
        assert snapshot.status == "CONFIRMED_ZERO", snapshot.issue_codes
        assert snapshot.transit_status == "DISJOINT_CONFIRMED"

        preview = service.preview_new_cost(
            store_id="store-a", product_id="101", offer_id="hook-2",
            sku="3921245627",
            effective_date="2026-11-06",
            purchase_cost_rub="18.00",
            delivery_cost_rub="2.00",
            packaging_cost_rub="1.00",
            old_home_units=0,
            expected_revision=0,
            zero_stock_snapshot=snapshot,
        )
        assert preview["error"] is False
        assert preview["zero_old_inventory_anchor"] is True
        assert preview["finite_units_at_anchor"] == 0
        assert preview["unit_cost_rub"] == "21.00"
        committed = service.confirm_new_cost(
            preview_id=preview["preview_id"],
            active_preview_id=preview["preview_id"],
            idempotency_key="zero-anchor-rate01",
        )
        assert committed["error"] is False
        connection = repository.get_connection()
        try:
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_events").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_layers").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_rate_changes").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_sources").fetchone()[0] == 2
            projection = connection.execute(
                "SELECT state, revision, known_quantity, known_cost_rub, "
                "next_unit_cost_rub, queue_complete, cutoff_status "
                "FROM fifo_cost_projections"
            ).fetchone()
            assert tuple(projection) == (
                "FIFO_PARTIAL", 1, 0, "0.00", "21.00", 0,
                "INVENTORY_CUTOFF_UNRECONCILED",
            )
        finally:
            connection.close()

        ambiguous = service.preview_new_cost(
            store_id="store-a", product_id="101", offer_id="hook-2",
            sku="3921245627",
            effective_date="2026-11-06",
            purchase_cost_rub="18.00",
            delivery_cost_rub="2.00",
            packaging_cost_rub="1.00",
            old_home_units=0,
            expected_revision=1,
            zero_stock_snapshot=replace(snapshot, transit_status="UNKNOWN"),
        )
        assert ambiguous == {"error": True, "code": "FIFO_ZERO_ANCHOR_SOURCE_UNCONFIRMED"}
    finally:
        reset_current_tenant_user_id(token)
