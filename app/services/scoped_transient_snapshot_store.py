"""Bounded in-memory snapshots for explicitly scoped seller workbenches."""

import json
import re
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from time import monotonic
from threading import RLock
from uuid import uuid4

from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id


@dataclass(frozen=True)
class ScopedTransientSnapshot:
    snapshot_id: str
    kind: str
    owner_id: str
    store_id: str
    generation: str
    version: int
    created_at: float
    expires_at: float
    source_freshness: dict
    coverage: dict
    rows: tuple

    def to_dict(self):
        return {
            "snapshot_id": self.snapshot_id,
            "kind": self.kind,
            "owner_id": self.owner_id,
            "store_id": self.store_id,
            "generation": self.generation,
            "version": self.version,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "source_freshness": deepcopy(self.source_freshness),
            "coverage": deepcopy(self.coverage),
            "rows": deepcopy(list(self.rows)),
        }


@dataclass(frozen=True)
class _GenerationState:
    generation: str
    version: int
    expires_at: float


class ScopedTransientSnapshotStore:
    """Store small report projections under the active owner/store tenant."""

    TTL_SECONDS = 600
    MAX_ENTRIES = 64
    MAX_GENERATIONS = 64
    MAX_ROWS = 256
    MAX_SNAPSHOT_BYTES = 1024 * 1024
    _KIND_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,47}\Z")
    _ROW_ID_MAX_LENGTH = 96

    def __init__(self, clock=None, tenant_scope_provider=None):
        self.clock = clock or monotonic
        self.tenant_scope_provider = (
            tenant_scope_provider or get_current_tenant_user_id
        )
        self._snapshots = OrderedDict()
        self._generations = OrderedDict()
        self._lock = RLock()

    def begin_generation(self, owner_id, store_id, kind):
        scope, error = self._scope(owner_id, store_id, kind)
        if error:
            return self._error(error)
        now = self.clock()
        generation = uuid4().hex
        with self._lock:
            self._expire_locked(now)
            self._remove_scope_snapshots_locked(scope)
            self._generations[scope] = _GenerationState(
                generation=generation,
                version=0,
                expires_at=now + self.TTL_SECONDS,
            )
            self._generations.move_to_end(scope)
            self._evict_locked()
        return {
            "error": False,
            "generation": generation,
            "read_only": True,
            "executed": False,
        }

    def put_snapshot(
        self,
        owner_id,
        store_id,
        kind,
        generation,
        version,
        source_freshness,
        coverage,
        rows,
    ):
        scope, error = self._scope(owner_id, store_id, kind)
        if error:
            return self._error(error)
        _tenant_scope, owner_id, store_id, kind = scope
        normalized = self._normalize_payload(
            owner_id,
            store_id,
            kind,
            generation,
            version,
            source_freshness,
            coverage,
            rows,
        )
        if normalized is None:
            return self._error("TRANSIENT_SNAPSHOT_PAYLOAD_INVALID")

        now = self.clock()
        snapshot = ScopedTransientSnapshot(
            snapshot_id=uuid4().hex,
            kind=kind,
            owner_id=str(owner_id),
            store_id=str(store_id),
            generation=generation,
            version=version,
            created_at=now,
            expires_at=now + self.TTL_SECONDS,
            source_freshness=normalized[0],
            coverage=normalized[1],
            rows=tuple(normalized[2]),
        )
        with self._lock:
            self._expire_locked(now)
            state = self._generations.get(scope)
            if (
                state is None
                or state.generation != generation
                or now >= state.expires_at
                or version < state.version
            ):
                return self._error("TRANSIENT_SNAPSHOT_GENERATION_STALE")
            if version > state.version:
                self._remove_scope_snapshots_locked(scope)
            self._generations[scope] = _GenerationState(
                generation=generation,
                version=version,
                expires_at=snapshot.expires_at,
            )
            self._generations.move_to_end(scope)
            key = (scope, snapshot.snapshot_id)
            self._snapshots[key] = snapshot
            self._snapshots.move_to_end(key)
            self._evict_locked()
            result = self._copy_snapshot(snapshot)
        return {
            "error": False,
            "snapshot": result.to_dict(),
            "read_only": True,
            "executed": False,
        }

    def get_snapshot(
        self,
        snapshot_id,
        owner_id,
        store_id,
        kind,
        generation,
        version,
    ):
        scope, error = self._scope(owner_id, store_id, kind)
        if error:
            return self._error(error)
        _tenant_scope, owner_id, store_id, kind = scope
        if not self._valid_generation(generation) or not self._valid_version(version):
            return self._error("TRANSIENT_SNAPSHOT_IDENTITY_INVALID")
        snapshot_id = str(snapshot_id or "").strip()
        if not snapshot_id:
            return self._error("TRANSIENT_SNAPSHOT_IDENTITY_INVALID")
        key = (scope, snapshot_id)
        now = self.clock()
        with self._lock:
            state = self._generations.get(scope)
            snapshot = self._snapshots.get(key)
            if snapshot is not None and now >= snapshot.expires_at:
                self._snapshots.pop(key, None)
                return self._error("TRANSIENT_SNAPSHOT_EXPIRED")
            if state is not None and now >= state.expires_at:
                self._remove_scope_locked(scope)
                return self._error("TRANSIENT_SNAPSHOT_EXPIRED")
            self._expire_locked(now)
            state = self._generations.get(scope)
            snapshot = self._snapshots.get(key)
            if (
                state is None
                or state.generation != generation
                or state.version != version
                or snapshot is None
                or snapshot.generation != generation
                or snapshot.version != version
                or snapshot.kind != kind
                or snapshot.owner_id != str(owner_id)
                or snapshot.store_id != str(store_id)
            ):
                return self._error("TRANSIENT_SNAPSHOT_STALE")
            self._snapshots.move_to_end(key)
            self._generations.move_to_end(scope)
            result = self._copy_snapshot(snapshot)
        return {
            "error": False,
            "snapshot": result.to_dict(),
            "read_only": True,
            "executed": False,
        }

    @property
    def size(self):
        with self._lock:
            return len(self._snapshots)

    @property
    def generation_count(self):
        with self._lock:
            return len(self._generations)

    def clear_owner(self, owner_id, kind=None):
        """Invalidate ephemeral snapshots and generations for one owner."""
        owner = str(owner_id or "").strip()
        kind_value = str(kind or "").strip() or None
        if not owner:
            return 0
        removed = 0
        with self._lock:
            scopes = [
                scope for scope in self._generations
                if scope[1] == owner and (kind_value is None or scope[3] == kind_value)
            ]
            for scope in scopes:
                removed += int(scope in self._generations)
                removed += sum(1 for key in self._snapshots if key[0] == scope)
                self._remove_scope_locked(scope)
        return removed

    def _scope(self, owner_id, store_id, kind):
        owner = str(owner_id or "").strip()
        store = str(store_id or "").strip()
        kind_value = str(kind or "").strip()
        if not owner or not self._valid_kind(kind_value):
            return None, "TRANSIENT_SNAPSHOT_IDENTITY_REQUIRED"
        try:
            tenant_scope = str(self.tenant_scope_provider() or "").strip()
        except Exception:
            tenant_scope = ""
        if not tenant_scope:
            return None, "TRANSIENT_SNAPSHOT_TENANT_REQUIRED"
        scoped_owner, scoped_store = split_store_tenant_scope(tenant_scope)
        if not scoped_owner:
            return None, "TRANSIENT_SNAPSHOT_TENANT_REQUIRED"
        if scoped_owner != owner or str(scoped_store or "").strip() != store:
            return None, "TRANSIENT_SNAPSHOT_SCOPE_MISMATCH"
        return (tenant_scope, owner, store, kind_value), None

    def _normalize_payload(
        self,
        owner_id,
        store_id,
        kind,
        generation,
        version,
        source_freshness,
        coverage,
        rows,
    ):
        if (
            not self._valid_generation(generation)
            or not self._valid_version(version)
            or type(source_freshness) is not dict
            or type(coverage) is not dict
            or not isinstance(rows, (list, tuple))
            or len(rows) > self.MAX_ROWS
        ):
            return None
        copied_rows = []
        row_ids = set()
        for row in rows:
            if type(row) is not dict:
                return None
            row_id = row.get("row_id")
            if (
                not isinstance(row_id, str)
                or not row_id.strip()
                or len(row_id) > self._ROW_ID_MAX_LENGTH
                or row_id in row_ids
            ):
                return None
            row_ids.add(row_id)
            copied_rows.append(deepcopy(row))
        try:
            encoded = json.dumps(
                {
                    "owner_id": str(owner_id),
                    "store_id": str(store_id),
                    "kind": kind,
                    "generation": generation,
                    "version": version,
                    "source_freshness": source_freshness,
                    "coverage": coverage,
                    "rows": copied_rows,
                },
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError, OverflowError):
            return None
        if len(encoded) > self.MAX_SNAPSHOT_BYTES:
            return None
        return deepcopy(source_freshness), deepcopy(coverage), copied_rows

    @classmethod
    def _valid_kind(cls, value):
        return isinstance(value, str) and bool(cls._KIND_PATTERN.fullmatch(value))

    @staticmethod
    def _valid_generation(value):
        return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{32}", value))

    @staticmethod
    def _valid_version(value):
        return type(value) is int and value >= 0

    def _expire_locked(self, now):
        expired_scopes = [
            scope
            for scope, state in self._generations.items()
            if now >= state.expires_at
        ]
        for scope in expired_scopes:
            self._remove_scope_locked(scope)
        expired_snapshots = [
            key
            for key, snapshot in self._snapshots.items()
            if now >= snapshot.expires_at
        ]
        for key in expired_snapshots:
            self._snapshots.pop(key, None)

    def _remove_scope_snapshots_locked(self, scope):
        for key in [key for key in self._snapshots if key[0] == scope]:
            self._snapshots.pop(key, None)

    def _remove_scope_locked(self, scope):
        self._generations.pop(scope, None)
        self._remove_scope_snapshots_locked(scope)

    def _evict_locked(self):
        while len(self._generations) > self.MAX_GENERATIONS:
            scope, _state = self._generations.popitem(last=False)
            self._remove_scope_snapshots_locked(scope)
        while len(self._snapshots) > self.MAX_ENTRIES:
            self._snapshots.popitem(last=False)

    @staticmethod
    def _copy_snapshot(snapshot):
        return ScopedTransientSnapshot(
            snapshot_id=snapshot.snapshot_id,
            kind=snapshot.kind,
            owner_id=snapshot.owner_id,
            store_id=snapshot.store_id,
            generation=snapshot.generation,
            version=snapshot.version,
            created_at=snapshot.created_at,
            expires_at=snapshot.expires_at,
            source_freshness=deepcopy(snapshot.source_freshness),
            coverage=deepcopy(snapshot.coverage),
            rows=tuple(deepcopy(list(snapshot.rows))),
        )

    @staticmethod
    def _error(code):
        return {
            "error": True,
            "code": code,
            "read_only": True,
            "executed": False,
        }
