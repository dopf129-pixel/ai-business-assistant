import sqlite3
from datetime import datetime, timezone

import pytest

from services.fifo_cost_anchor_service import FifoCostAnchorService
from services.fifo_cost_repository import FifoCostRepository
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
        {
            "sequence": 1,
            "unit_cost_rub": "5.00",
            "ozon_units": 10,
            "transit_units": 0,
            "home_units": 0,
        },
        {
            "sequence": 2,
            "unit_cost_rub": "10.00",
            "ozon_units": 5,
            "transit_units": 2,
            "home_units": 0,
        },
    ]


def _service(tmp_path):
    repository = FifoCostRepository(
        db_path=tmp_path / "fifo-anchor.sqlite",
        now_provider=lambda: datetime(2026, 11, 6, 12, tzinfo=timezone.utc),
    )
    service = FifoCostAnchorService(
        repository,
        now_provider=lambda: datetime(2026, 11, 6, 12, tzinfo=timezone.utc),
    )
    return service, repository


def _preview(service, **overrides):
    payload = {
        **IDENTITY,
        "inventory_cutoff": "2026-11-05",
        "cost_layers": _layers(),
        "ozon_units_include_reserved_confirmed": True,
        "transit_not_in_ozon_confirmed": True,
    }
    payload.update(overrides)
    return service.preview_opening_anchor(**payload)


def test_owner_confirmed_initial_anchor_preserves_layers_and_cutoff_gate(tmp_path):
    service, repository = _service(tmp_path)
    tenant_token = set_current_tenant_user_id(
        make_store_tenant_scope("owner-1", "store-a"),
    )
    try:
        preview = _preview(service)

        assert preview["error"] is False
        assert preview["total_units"] == 17
        assert preview["event_count"] == 3
        assert preview["known_cost_rub"] == "120.00"
        assert preview["next_unit_cost_rub"] == "5.00"
        assert preview["zone_totals"] == {"OZON": 15, "TRANSIT": 2, "HOME": 0}
        assert preview["inventory_cutoff"] == "2026-11-05"
        assert preview["period_profit_cutoff_status"] == "INVENTORY_CUTOFF_UNRECONCILED"
        assert "3921245627" not in repr(preview)

        connection = sqlite3.connect(repository.db_path)
        try:
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_events").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_streams").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_projections").fetchone()[0] == 0
        finally:
            connection.close()

        committed = service.commit_opening_anchor(
            preview_id=preview["preview_id"],
            active_preview_id=preview["preview_id"],
            idempotency_key="owner-anchor-confirm1",
        )
        assert committed["error"] is False

        connection = sqlite3.connect(repository.db_path)
        try:
            stream = connection.execute(
                "SELECT state, revision FROM fifo_cost_streams",
            ).fetchone()
            assert stream == ("FIFO_READY", 1)
            layers = connection.execute(
                "SELECT quantity, unit_cost_rub FROM fifo_cost_layers "
                "ORDER BY layer_sequence",
            ).fetchall()
            assert layers == [(10, "5.00"), (5, "10.00"), (2, "10.00")]
            event_rows = connection.execute(
                "SELECT quantity, location_to, effective_at, effective_date, "
                "inventory_cutoff, provenance FROM fifo_cost_events ORDER BY rowid",
            ).fetchall()
            assert event_rows == [
                (10, "OZON", None, "2026-11-05", "2026-11-05", "OWNER_CONFIRMED"),
                (5, "OZON", None, "2026-11-05", "2026-11-05", "OWNER_CONFIRMED"),
                (2, "TRANSIT", None, "2026-11-05", "2026-11-05", "OWNER_CONFIRMED"),
            ]
            zero_reference_count = connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_source_refs WHERE reference_kind='OTHER'",
            ).fetchone()[0]
            assert zero_reference_count == 3
            projection = connection.execute(
                "SELECT state, known_quantity, known_cost_rub, next_unit_cost_rub, "
                "queue_complete, cutoff_status FROM fifo_cost_projections",
            ).fetchone()
            assert projection == (
                "FIFO_READY", 17, "120.00", "5.00", 1,
                "INVENTORY_CUTOFF_UNRECONCILED",
            )
        finally:
            connection.close()

        repeated_anchor = _preview(service)
        assert repeated_anchor == {"error": True, "code": "FIFO_ANCHOR_ALREADY_EXISTS"}
    finally:
        reset_current_tenant_user_id(tenant_token)


def test_explicit_zero_old_home_quantity_is_valid(tmp_path):
    service, _repository = _service(tmp_path)
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-1", "store-a"))
    try:
        result = _preview(service, cost_layers=[{
            "sequence": 1,
            "unit_cost_rub": "5.00",
            "ozon_units": 10,
            "transit_units": 0,
            "home_units": 0,
        }])
        assert result["error"] is False
        assert result["zone_totals"]["HOME"] == 0
    finally:
        reset_current_tenant_user_id(token)


@pytest.mark.parametrize(
    "identity_overrides",
    [
        {"store_id": True},
        {"sku": object()},
        {"product_id": "product" + chr(10) + "101"},
        {"product_id": None, "offer_id": None},
        {"store_id": "s" * 129},
        {"sku": "s" * 65},
    ],
)
def test_invalid_or_ambiguous_identity_is_rejected_before_preview(
    tmp_path, identity_overrides,
):
    service, repository = _service(tmp_path)
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-1", "store-a"))
    try:
        repository.get_connection().close()
        result = _preview(service, **identity_overrides)
        assert result == {"error": True, "code": "FIFO_IDENTITY_INVALID"}
        connection = repository.get_connection()
        try:
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_events").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_streams").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_commands").fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"transit_not_in_ozon_confirmed": False}, "TRANSIT_OVERLAP_UNRESOLVED"),
        ({"transit_not_in_ozon_confirmed": None}, "FIFO_ANCHOR_TRANSIT_CONFIRMATION_REQUIRED"),
        ({"ozon_units_include_reserved_confirmed": False}, "STOCK_SEMANTICS_UNCONFIRMED"),
        ({"ozon_units_include_reserved_confirmed": None}, "FIFO_ANCHOR_STOCK_CONFIRMATION_REQUIRED"),
        ({"inventory_cutoff": "2026-11-05T00:00:00"}, "FIFO_ANCHOR_CUTOFF_INVALID"),
        ({"cost_layers": []}, "FIFO_ANCHOR_LAYERS_INVALID"),
        ({"cost_layers": [{**_layers()[0], "home_units": True}]}, "FIFO_ANCHOR_QUANTITY_INVALID"),
        ({"cost_layers": [{**_layers()[0], "home_units": None}]}, "FIFO_ANCHOR_QUANTITY_INVALID"),
        ({"cost_layers": [{**_layers()[0], "unit_cost_rub": 1.25}]}, "FIFO_MONEY_INPUT_INVALID"),
        ({"cost_layers": [{**_layers()[0], "sequence": 2}]}, "FIFO_ANCHOR_LAYER_ORDER_INVALID"),
        ({"cost_layers": [{key: value for key, value in _layers()[0].items() if key != "home_units"}]}, "FIFO_ANCHOR_LAYER_FIELDS_INVALID"),
        ({"cost_layers": [{**_layers()[0], "ozon_units": -1}]}, "FIFO_ANCHOR_QUANTITY_INVALID"),
    ],
)
def test_unsafe_or_incomplete_anchor_inputs_are_rejected_without_preview(
    tmp_path, overrides, code,
):
    service, repository = _service(tmp_path)
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-1", "store-a"))
    try:
        connection = repository.get_connection()
        connection.close()
        result = _preview(service, **overrides)
        assert result == {"error": True, "code": code}
        connection = sqlite3.connect(repository.db_path)
        try:
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_events").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM fifo_cost_streams").fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_opening_anchor_command_must_not_mix_receipt_or_other_event(tmp_path):
    repository = FifoCostRepository(db_path=tmp_path / "mixed.sqlite")
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-1", "store-a"))
    try:
        source = {
            "kind": "OWNER_CONFIRMATION",
            "method": "OWNER_CONFIRMED_FIFO_CUTOFF",
            "status": "OWNER_CONFIRMED",
            "completeness": "OWNER_CONFIRMED",
            "provenance": "OWNER_CONFIRMED",
            "coverage_status": "OWNER_CONFIRMED",
            "inventory_cutoff": "2026-11-05",
        }
        events = [
            {
                "kind": "OPENING_FIFO_ANCHOR", "quantity": 1,
                "unit_cost_rub": "5.00", "effective_date": "2026-11-05",
                "location_to": "OZON",
            },
            {
                "kind": "COST_LAYER_RECEIPT", "quantity": 1,
                "unit_cost_rub": "10.00", "effective_date": "2026-11-06",
            },
        ]
        result = repository.preview_command(
            store_id="store-a", product_id="product-101", offer_id="hook-2",
            sku="3921245627", events=events, source=source,
        )
        assert result == {"error": True, "code": "FIFO_ANCHOR_COMMAND_MUST_BE_EXCLUSIVE"}
    finally:
        reset_current_tenant_user_id(token)
