from threading import Event, Thread

import pytest

from services.scoped_transient_snapshot_store import (
    ScopedTransientSnapshotStore,
)
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


class _Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def active_tenant():
    token = set_current_tenant_user_id("user-1::ozon::store-1")
    try:
        yield
    finally:
        reset_current_tenant_user_id(token)


def _begin(store, kind="product_overview", owner="user-1", store_id="store-1"):
    result = store.begin_generation(owner, store_id, kind)
    assert result["error"] is False
    return result["generation"]


def _put(
    store,
    generation,
    rows=None,
    version=1,
    kind="product_overview",
    owner="user-1",
    store_id="store-1",
):
    return store.put_snapshot(
        owner_id=owner,
        store_id=store_id,
        kind=kind,
        generation=generation,
        version=version,
        source_freshness={"catalog": {"status": "fresh", "age_seconds": 0}},
        coverage={"selected": 1, "processed": 1},
        rows=rows if rows is not None else [{"row_id": "sku-1", "value": 10}],
    )


def _get(store, snapshot, generation, version=1, kind="product_overview"):
    return store.get_snapshot(
        snapshot_id=snapshot["snapshot"]["snapshot_id"],
        owner_id="user-1",
        store_id="store-1",
        kind=kind,
        generation=generation,
        version=version,
    )


def test_snapshot_requires_active_exact_owner_and_store_scope(active_tenant):
    store = ScopedTransientSnapshotStore()
    generation = _begin(store)
    created = _put(store, generation)
    assert created["error"] is False

    assert store.begin_generation("user-2", "store-1", "product_overview")["code"] == (
        "TRANSIENT_SNAPSHOT_SCOPE_MISMATCH"
    )
    assert store.begin_generation("user-1", "store-2", "product_overview")["code"] == (
        "TRANSIENT_SNAPSHOT_SCOPE_MISMATCH"
    )

    other_tenant = set_current_tenant_user_id("user-2::ozon::store-1")
    try:
        result = _get(store, created, generation)
    finally:
        reset_current_tenant_user_id(other_tenant)
    assert result["error"] is True
    assert result["code"] == "TRANSIENT_SNAPSHOT_SCOPE_MISMATCH"

    missing_tenant = set_current_tenant_user_id(None)
    try:
        result = store.begin_generation("user-1", "store-1", "product_overview")
    finally:
        reset_current_tenant_user_id(missing_tenant)
    assert result["code"] == "TRANSIENT_SNAPSHOT_TENANT_REQUIRED"


def test_snapshot_supports_default_owner_scope_without_store_but_keeps_store_isolation():
    store = ScopedTransientSnapshotStore()
    default_tenant = set_current_tenant_user_id("user-1")
    try:
        generation_result = store.begin_generation("user-1", "", "plan_comparison")
        assert generation_result["error"] is False
        generation = generation_result["generation"]
        created = _put(
            store, generation, kind="plan_comparison", store_id="",
            rows=[{"row_id": "comparison", "value": 1}],
        )
        assert created["error"] is False
        loaded = store.get_snapshot(
            created["snapshot"]["snapshot_id"], "user-1", "", "plan_comparison",
            generation, 1,
        )
        assert loaded["error"] is False
    finally:
        reset_current_tenant_user_id(default_tenant)

    other_store = set_current_tenant_user_id("user-1::ozon::store-1")
    try:
        rejected = store.get_snapshot(
            created["snapshot"]["snapshot_id"], "user-1", "", "plan_comparison",
            generation, 1,
        )
        assert rejected["error"] is True
        assert rejected["code"] == "TRANSIENT_SNAPSHOT_SCOPE_MISMATCH"
        assert store.begin_generation("user-1", "", "plan_comparison")["code"] == (
            "TRANSIENT_SNAPSHOT_SCOPE_MISMATCH"
        )
    finally:
        reset_current_tenant_user_id(other_store)


def test_new_generation_rejects_late_old_write_and_old_callback(active_tenant):
    store = ScopedTransientSnapshotStore()
    old_generation = _begin(store)
    old_snapshot = _put(store, old_generation)
    new_generation = _begin(store)

    late_old_write = _put(store, old_generation)
    assert late_old_write["error"] is True
    assert late_old_write["code"] == "TRANSIENT_SNAPSHOT_GENERATION_STALE"
    assert _get(store, old_snapshot, old_generation)["code"] == (
        "TRANSIENT_SNAPSHOT_STALE"
    )

    current = _put(store, new_generation)
    assert current["error"] is False
    assert _get(store, current, new_generation)["error"] is False


def test_snapshot_uses_fixed_ttl_and_read_does_not_extend_it(active_tenant):
    clock = _Clock()
    store = ScopedTransientSnapshotStore(clock=clock)
    generation = _begin(store)
    created = _put(store, generation)
    snapshot = created["snapshot"]
    assert snapshot["created_at"] == 0
    assert snapshot["expires_at"] == store.TTL_SECONDS

    clock.now = store.TTL_SECONDS - 1
    assert _get(store, created, generation)["error"] is False
    assert created["snapshot"]["expires_at"] == store.TTL_SECONDS

    clock.now = store.TTL_SECONDS
    expired = _get(store, created, generation)
    assert expired["error"] is True
    assert expired["code"] == "TRANSIENT_SNAPSHOT_EXPIRED"


def test_snapshot_copy_isolation_and_stable_row_identity(active_tenant):
    store = ScopedTransientSnapshotStore()
    generation = _begin(store)
    rows = [{"row_id": "product-1", "value": 10}]
    freshness = {"sales": {"as_of": "2026-10-17"}}
    coverage = {"selected": 1, "processed": 1}
    created = store.put_snapshot(
        "user-1", "store-1", "product_overview", generation, 1,
        freshness, coverage, rows,
    )
    assert created["error"] is False

    rows[0]["value"] = 100
    freshness["sales"]["as_of"] = "changed"
    returned = created["snapshot"]
    returned["rows"][0]["value"] = 200
    returned["coverage"]["selected"] = 200

    loaded = _get(store, created, generation)
    assert loaded["snapshot"]["rows"] == [
        {"row_id": "product-1", "value": 10}
    ]
    assert loaded["snapshot"]["rows"][0]["row_id"] == "product-1"
    assert loaded["snapshot"]["source_freshness"]["sales"]["as_of"] == (
        "2026-10-17"
    )
    assert loaded["snapshot"]["coverage"]["selected"] == 1


@pytest.mark.parametrize(
    "rows, freshness, coverage, version",
    [
        ([{"row_id": "same"}, {"row_id": "same"}], {}, {}, 1),
        ([{"value": 1}], {}, {}, 1),
        ([{"row_id": "ok", "value": float("nan")}], {}, {}, 1),
        ([{"row_id": "ok"}], [], {}, 1),
        ([{"row_id": "ok"}], {}, {}, True),
        ([{"row_id": "ok"}], {}, {}, 1.0),
    ],
)
def test_invalid_snapshot_payload_is_rejected(
    active_tenant, rows, freshness, coverage, version
):
    store = ScopedTransientSnapshotStore()
    generation = _begin(store)
    result = store.put_snapshot(
        "user-1", "store-1", "product_overview", generation,
        version, freshness, coverage, rows,
    )
    assert result["error"] is True
    assert result["code"] == "TRANSIENT_SNAPSHOT_PAYLOAD_INVALID"
    assert store.size == 0


def test_snapshot_lru_is_bounded_to_64_entries(active_tenant):
    store = ScopedTransientSnapshotStore()
    generation = _begin(store)
    first = _put(store, generation, rows=[{"row_id": "row-0"}])
    snapshots = [first]
    for index in range(1, store.MAX_ENTRIES + 1):
        snapshots.append(
            _put(store, generation, rows=[{"row_id": f"row-{index}"}])
        )

    assert store.size == store.MAX_ENTRIES
    assert store.generation_count == 1
    assert _get(store, first, generation)["code"] == "TRANSIENT_SNAPSHOT_STALE"
    assert _get(store, snapshots[-1], generation)["error"] is False


def test_snapshot_payload_is_bounded_by_rows_and_encoded_size(active_tenant):
    store = ScopedTransientSnapshotStore()
    generation = _begin(store)
    too_many_rows = _put(
        store,
        generation,
        rows=[{"row_id": f"row-{index}"} for index in range(store.MAX_ROWS + 1)],
    )
    too_large = _put(
        store,
        generation,
        rows=[{"row_id": "large-row", "value": "x" * store.MAX_SNAPSHOT_BYTES}],
    )

    assert too_many_rows["code"] == "TRANSIENT_SNAPSHOT_PAYLOAD_INVALID"
    assert too_large["code"] == "TRANSIENT_SNAPSHOT_PAYLOAD_INVALID"
    assert store.size == 0


def test_lru_eviction_during_snapshot_copy_returns_complete_copy(active_tenant):
    copy_started = Event()
    allow_copy = Event()

    class _PausingStore(ScopedTransientSnapshotStore):
        paused_snapshot_id = None

        def _copy_snapshot(self, snapshot):
            if snapshot.snapshot_id == self.paused_snapshot_id:
                self.paused_snapshot_id = None
                copy_started.set()
                assert allow_copy.wait(timeout=3)
            return super()._copy_snapshot(snapshot)

    store = _PausingStore()
    generation = _begin(store)
    first = _put(store, generation, rows=[{"row_id": "row-0", "value": 0}])
    store.paused_snapshot_id = first["snapshot"]["snapshot_id"]
    read_results = []
    errors = []

    def reader():
        token = set_current_tenant_user_id("user-1::ozon::store-1")
        try:
            read_results.append(_get(store, first, generation))
        except Exception as exc:  # pragma: no cover - asserted as empty below
            errors.append(exc)
        finally:
            reset_current_tenant_user_id(token)

    reader_thread = Thread(target=reader)
    reader_thread.start()
    assert copy_started.wait(timeout=3)

    def writer():
        token = set_current_tenant_user_id("user-1::ozon::store-1")
        try:
            for index in range(1, store.MAX_ENTRIES + 1):
                result = _put(
                    store,
                    generation,
                    rows=[{"row_id": f"row-{index}", "value": index}],
                )
                assert result["error"] is False
        except Exception as exc:  # pragma: no cover - asserted as empty below
            errors.append(exc)
        finally:
            reset_current_tenant_user_id(token)

    writer_thread = Thread(target=writer)
    writer_thread.start()
    allow_copy.set()
    reader_thread.join(timeout=3)
    writer_thread.join(timeout=3)

    assert not reader_thread.is_alive()
    assert not writer_thread.is_alive()
    assert errors == []
    assert read_results[0]["snapshot"]["rows"] == [
        {"row_id": "row-0", "value": 0}
    ]
    assert store.size == store.MAX_ENTRIES
