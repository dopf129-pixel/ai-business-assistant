"""Bounded, case-bound refresh of FIFO declared-supply source evidence."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import threading
from time import monotonic
from uuid import uuid4

from services.fifo_cost_source_collection_service import FifoCostSourceCollectionService
from services.fifo_cost_source_normalizer import FifoCostSourceNormalizer
from services.fifo_cost_transition_service import FifoCostTransitionService
from services.ozon_account_repository import split_store_tenant_scope
from services.period_profit_operation_diagnostics import (
    PeriodProfitOperationTrace,
    current_period_profit_trace,
)
from services.tenant_context import get_current_tenant_user_id


@dataclass(frozen=True, slots=True)
class FifoTransitionSupplyRefreshResult:
    status: str
    source_status: str
    read_only: bool
    actual_http_attempts: int
    http_attempt_cap: int
    elapsed_seconds: float
    case_revision: int | None
    source_fingerprint: str | None
    issue_codes: tuple[str, ...]
    status_snapshot: object = None
    act_snapshot: object = None
    continuation_token: str | None = None


@dataclass(frozen=True, slots=True)
class _RefreshCheckpoint:
    scope_fingerprint: str
    phase: str
    inner_token: str | None
    active_snapshot: object
    expires_at: float


class FifoCostTransitionSupplyRefreshService:
    """Refresh one declared supply under a single 20-second/10-attempt budget.

    Continuations are opaque and process-local. Every token is bound to the
    exact transition case revision and declaration. After process restart an
    old token fails closed; the durable case/declarations/observations remain
    available and the caller can start a fresh bounded read.
    """

    TIME_BUDGET_SECONDS = 20.0
    HTTP_ATTEMPT_BUDGET = 10
    CHECKPOINT_TTL_SECONDS = 600.0
    MAX_CHECKPOINTS = 128

    def __init__(
        self,
        *,
        transition_service: FifoCostTransitionService,
        source_collection: FifoCostSourceCollectionService,
        monotonic_clock=monotonic,
    ):
        self.transition_service = transition_service
        self.source_collection = source_collection
        self.monotonic_clock = monotonic_clock
        self._checkpoints: dict[str, _RefreshCheckpoint] = {}
        self._lock = threading.RLock()

    def refresh(
        self, *, case_id, declaration_id, reference_id, store_id,
        product_id=None, offer_id=None, sku, expected_case_revision,
        continuation_token=None, operation_trace=None,
    ) -> FifoTransitionSupplyRefreshResult:
        started = self.monotonic_clock()
        identity = {
            "product_id": product_id,
            "offer_id": offer_id,
            "sku": sku,
        }
        current = self.transition_service.get_case(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku,
        )
        if current.get("error"):
            return self._result(
                started=started, status="CONFLICT", source_status="CONFLICT",
                case_revision=None, issues=(current.get("code", "FIFO_TRANSITION_CASE_NOT_FOUND"),),
            )
        if type(expected_case_revision) is not int or expected_case_revision < 1:
            return self._result(
                started=started, status="INVALID", source_status="CONFLICT",
                case_revision=current["case_revision"],
                issues=("FIFO_TRANSITION_REVISION_INVALID",),
            )
        if current["case_revision"] != expected_case_revision:
            return self._result(
                started=started, status="CONFLICT", source_status="CONFLICT",
                case_revision=current["case_revision"],
                issues=("FIFO_TRANSITION_REVISION_CONFLICT",),
            )
        scope = current.get("case", {}).get("metadata", {}).get("scope", {})
        if any((
            scope.get("store_id") != store_id,
            scope.get("product_id") != product_id,
            scope.get("offer_id") != offer_id,
            scope.get("sku") != sku,
        )):
            return self._result(
                started=started, status="CONFLICT", source_status="CONFLICT",
                case_revision=current["case_revision"],
                issues=("FIFO_TRANSITION_SCOPE_MISMATCH",),
            )
        tenant_scope = str(get_current_tenant_user_id() or "").strip()
        owner_id, scoped_store = split_store_tenant_scope(tenant_scope)
        if not owner_id or scoped_store != store_id:
            return self._result(
                started=started, status="CONFLICT", source_status="CONFLICT",
                case_revision=current["case_revision"],
                issues=("FIFO_TRANSITION_SCOPE_MISMATCH",),
            )
        manifest = self.transition_service.get_supply_manifest(
            case_id=case_id, store_id=store_id, product_id=product_id,
            offer_id=offer_id, sku=sku,
        )
        if manifest.get("error"):
            return self._result(
                started=started, status="CONFLICT", source_status="CONFLICT",
                case_revision=current["case_revision"],
                issues=(manifest.get("code", "FIFO_TRANSITION_MANIFEST_UNAVAILABLE"),),
            )
        declaration = next((
            item for item in manifest["declarations"]
            if item["declaration_id"] == declaration_id
        ), None)
        normalized_reference_digest = self.transition_service.reference_digest_for_supply(
            owner_id=owner_id, store_id=store_id, reference_id=reference_id,
        )
        declaration_matches_reference = self.transition_service.supply_declaration_matches_reference(
            case_id=case_id, declaration_id=declaration_id, owner_id=owner_id,
            store_id=store_id, product_id=product_id, offer_id=offer_id,
            sku=sku, reference_id=reference_id,
        )
        if (
            declaration is None
            or declaration.get("reference_kind") != "SUPPLY"
            or declaration.get("lookup_status") != "AVAILABLE"
            or normalized_reference_digest is None
            or not declaration_matches_reference
        ):
            return self._result(
                started=started, status="CONFLICT", source_status="CONFLICT",
                case_revision=current["case_revision"],
                issues=("FIFO_TRANSITION_SUPPLY_REFERENCE_MISMATCH",),
            )

        scope_fingerprint = self._fingerprint({
            "owner": owner_id,
            "store": store_id,
            "sku": sku,
            "product_id": product_id,
            "offer_id": offer_id,
            "case_id": case_id,
            "case_revision": expected_case_revision,
            "declaration_id": declaration_id,
            "reference_digest": normalized_reference_digest,
        })
        checkpoint, checkpoint_error = self._take_checkpoint(
            continuation_token, scope_fingerprint=scope_fingerprint,
        )
        if checkpoint_error:
            return self._result(
                started=started, status="CONFLICT", source_status="CONFLICT",
                case_revision=current["case_revision"], issues=(checkpoint_error,),
            )

        parent_trace = PeriodProfitOperationTrace(
            operation="fifo_transition_supply_refresh",
            time_budget_seconds=max(
                0.0,
                self.TIME_BUDGET_SECONDS
                - max(0.0, self.monotonic_clock() - started),
            ),
            ozon_request_budget=self.HTTP_ATTEMPT_BUDGET,
            clock=self.monotonic_clock,
            parent=operation_trace or current_period_profit_trace(),
        )
        status_snapshot = checkpoint.active_snapshot if checkpoint else None
        act_snapshot = None
        issues: list[str] = []
        result_status = "PARTIAL"
        source_status = "PARTIAL"
        continuation = None
        phase = checkpoint.phase if checkpoint else "ACTIVE"

        if phase == "ACTIVE":
            remaining = self._remaining_attempts(parent_trace)
            if remaining <= 0 or parent_trace.remaining_seconds() <= 0:
                return self._partial_from_checkpoint(
                    started=started, scope_fingerprint=scope_fingerprint,
                    phase="ACTIVE", inner_token=checkpoint.inner_token if checkpoint else None,
                    active_snapshot=None, trace=parent_trace,
                    case_revision=current["case_revision"],
                    issues=(
                        "FIFO_SOURCE_TIME_BUDGET_EXHAUSTED"
                        if parent_trace.remaining_seconds() <= 0
                        else "FIFO_SOURCE_HTTP_BUDGET_EXHAUSTED",
                    ),
                )
            active = self.source_collection.observe_active_supply_by_id(
                reference_id,
                owner_id=owner_id,
                identity=identity,
                store_id=store_id,
                tenant_scope=tenant_scope,
                operation_trace=parent_trace,
                checkpoint_token=checkpoint.inner_token if checkpoint else None,
                transition_case_id=case_id,
                transition_case_revision=expected_case_revision,
                http_attempt_budget=remaining,
                time_budget_seconds=parent_trace.remaining_seconds(),
            )
            issues.extend(active.issue_codes)
            status_snapshot = active.supply_snapshot
            if active.source_status == "PARTIAL" and active.continuation_token:
                return self._partial_from_checkpoint(
                    started=started, scope_fingerprint=scope_fingerprint,
                    phase="ACTIVE", inner_token=active.continuation_token,
                    active_snapshot=active.supply_snapshot, trace=parent_trace,
                    case_revision=current["case_revision"], issues=issues,
                )
            if active.status not in {"PRESENT", "MISSING"} or status_snapshot is None:
                return self._result(
                    started=started, status=active.status,
                    source_status=active.source_status,
                    case_revision=current["case_revision"],
                    source_fingerprint=active.source_fingerprint,
                    issues=issues, status_snapshot=status_snapshot,
                    actual_attempts=parent_trace.ozon_requests_reserved,
                    elapsed=self.monotonic_clock() - started,
                )
            if active.source_status != "COMPLETE":
                return self._result(
                    started=started, status="PARTIAL", source_status="PARTIAL",
                    case_revision=current["case_revision"],
                    source_fingerprint=active.source_fingerprint,
                    issues=issues or ["FIFO_ACTIVE_SUPPLY_SOURCE_INCOMPLETE"],
                    status_snapshot=status_snapshot,
                    actual_attempts=parent_trace.ozon_requests_reserved,
                    elapsed=self.monotonic_clock() - started,
                )
            if (
                status_snapshot.presence == "PRESENT"
                and status_snapshot.normalized_status == "ACCEPTED"
            ):
                phase = "ACTS"
            else:
                result_status = "COMPLETE"
                source_status = "COMPLETE"

        if phase == "ACTS":
            remaining = self._remaining_attempts(parent_trace)
            if remaining <= 0 or parent_trace.remaining_seconds() <= 0:
                return self._partial_from_checkpoint(
                    started=started, scope_fingerprint=scope_fingerprint,
                    phase="ACTS", inner_token=checkpoint.inner_token if checkpoint else None,
                    active_snapshot=status_snapshot, trace=parent_trace,
                    case_revision=current["case_revision"],
                    issues=(
                        "FIFO_SOURCE_TIME_BUDGET_EXHAUSTED"
                        if parent_trace.remaining_seconds() <= 0
                        else "FIFO_SOURCE_HTTP_BUDGET_EXHAUSTED",
                    ),
                )
            acts = self.source_collection.find_supply_by_id(
                reference_id,
                identity=identity,
                store_id=store_id,
                tenant_scope=tenant_scope,
                operation_trace=parent_trace,
                checkpoint_token=(
                    checkpoint.inner_token
                    if checkpoint is not None and checkpoint.phase == "ACTS"
                    else None
                ),
                transition_case_id=case_id,
                transition_case_revision=expected_case_revision,
                http_attempt_budget=remaining,
                time_budget_seconds=parent_trace.remaining_seconds(),
            )
            issues.extend(acts.issue_codes)
            act_snapshot = acts.supply_snapshot
            if acts.status == "PARTIAL":
                return self._partial_from_checkpoint(
                    started=started, scope_fingerprint=scope_fingerprint,
                    phase="ACTS", inner_token=acts.continuation_token,
                    active_snapshot=status_snapshot, trace=parent_trace,
                    case_revision=current["case_revision"], issues=issues,
                    act_snapshot=act_snapshot,
                )
            if acts.status not in {"COMPLETE", "CONFIRMED_ZERO"} or act_snapshot is None:
                return self._result(
                    started=started, status="CONFLICT", source_status="CONFLICT",
                    case_revision=current["case_revision"],
                    source_fingerprint=acts.source_fingerprint,
                    issues=issues or ["FIFO_ACCEPTED_ACT_SOURCE_UNAVAILABLE"],
                    status_snapshot=status_snapshot, act_snapshot=act_snapshot,
                    actual_attempts=parent_trace.ozon_requests_reserved,
                    elapsed=self.monotonic_clock() - started,
                )
            if act_snapshot.units_by_sku is None or tuple(
                act_sku for act_sku, _ in act_snapshot.units_by_sku
            ) != (str(sku),):
                return self._result(
                    started=started, status="CONFLICT", source_status="CONFLICT",
                    case_revision=current["case_revision"],
                    source_fingerprint=acts.source_fingerprint,
                    issues=("FIFO_SUPPLY_SKU_IDENTITY_MISMATCH",),
                    status_snapshot=status_snapshot, act_snapshot=act_snapshot,
                    actual_attempts=parent_trace.ozon_requests_reserved,
                    elapsed=self.monotonic_clock() - started,
                )
            result_status = "COMPLETE"
            source_status = "COMPLETE"

        if status_snapshot is not None:
            update = self.transition_service.record_supply_observation(
                case_id=case_id, store_id=store_id, product_id=product_id,
                offer_id=offer_id, sku=sku, declaration_id=declaration_id,
                reference_id=reference_id, snapshot=status_snapshot,
                act_snapshot=act_snapshot,
                expected_case_revision=expected_case_revision,
                idempotency_key=self._observation_idempotency_key(
                    case_id,
                    declaration_id,
                    (
                        FifoCostSourceNormalizer._fingerprint({
                            "status": status_snapshot.source_fingerprint,
                            "acts": act_snapshot.source_fingerprint,
                        })
                        if act_snapshot is not None
                        else status_snapshot.source_fingerprint
                    ),
                ),
            )
            if update.get("error"):
                return self._result(
                    started=started, status="CONFLICT", source_status="CONFLICT",
                    case_revision=update.get("case_revision", expected_case_revision),
                    source_fingerprint=status_snapshot.source_fingerprint,
                    issues=(update.get("code", "FIFO_TRANSITION_OBSERVATION_UPDATE_FAILED"),),
                    status_snapshot=status_snapshot, act_snapshot=act_snapshot,
                    actual_attempts=parent_trace.ozon_requests_reserved,
                    elapsed=self.monotonic_clock() - started,
                )
            current_revision = update.get("case_revision", expected_case_revision + 1)
        else:
            current_revision = expected_case_revision

        source_fingerprint = self._fingerprint({
            "status": status_snapshot.source_fingerprint if status_snapshot else None,
            "acts": act_snapshot.source_fingerprint if act_snapshot else None,
        })
        return self._result(
            started=started, status=result_status, source_status=source_status,
            case_revision=current_revision, source_fingerprint=source_fingerprint,
            issues=issues, status_snapshot=status_snapshot, act_snapshot=act_snapshot,
            actual_attempts=parent_trace.ozon_requests_reserved,
            elapsed=self.monotonic_clock() - started,
        )

    def _partial_from_checkpoint(
        self, *, started, scope_fingerprint, phase, inner_token,
        active_snapshot, trace, case_revision, issues, act_snapshot=None,
    ):
        token = self._save_checkpoint(_RefreshCheckpoint(
            scope_fingerprint=scope_fingerprint,
            phase=phase,
            inner_token=inner_token,
            active_snapshot=active_snapshot,
            expires_at=self.monotonic_clock() + self.CHECKPOINT_TTL_SECONDS,
        ))
        if token is None:
            issues = tuple(issues) + ("FIFO_TRANSITION_CHECKPOINT_UNAVAILABLE",)
        return self._result(
            started=started, status="PARTIAL", source_status="PARTIAL",
            case_revision=case_revision,
            source_fingerprint=(
                active_snapshot.source_fingerprint if active_snapshot is not None else None
            ),
            issues=issues, status_snapshot=active_snapshot,
            act_snapshot=act_snapshot, continuation_token=token,
            actual_attempts=trace.ozon_requests_reserved,
            elapsed=self.monotonic_clock() - started,
        )

    def _take_checkpoint(self, token, *, scope_fingerprint):
        if token is None:
            return None, None
        if not isinstance(token, str) or len(token) != 32:
            return None, "FIFO_TRANSITION_CHECKPOINT_INVALID"
        with self._lock:
            checkpoint = self._checkpoints.get(token)
            if checkpoint is None:
                return None, "FIFO_TRANSITION_CHECKPOINT_STALE"
            if checkpoint.expires_at <= self.monotonic_clock():
                self._checkpoints.pop(token, None)
                return None, "FIFO_TRANSITION_CHECKPOINT_EXPIRED"
            if checkpoint.scope_fingerprint != scope_fingerprint:
                return None, "FIFO_TRANSITION_CHECKPOINT_SCOPE_MISMATCH"
            self._checkpoints.pop(token, None)
        return checkpoint, None

    def _save_checkpoint(self, checkpoint):
        token = uuid4().hex
        with self._lock:
            for key in [
                key for key, value in self._checkpoints.items()
                if value.expires_at <= self.monotonic_clock()
            ]:
                self._checkpoints.pop(key, None)
            if len(self._checkpoints) >= self.MAX_CHECKPOINTS:
                return None
            self._checkpoints[token] = checkpoint
        return token

    def _result(
        self, *, started, status, source_status, case_revision, issues,
        source_fingerprint=None, status_snapshot=None, act_snapshot=None,
        continuation_token=None, actual_attempts=0, elapsed=None,
    ):
        return FifoTransitionSupplyRefreshResult(
            status=status,
            source_status=source_status,
            read_only=True,
            actual_http_attempts=max(0, int(actual_attempts)),
            http_attempt_cap=self.HTTP_ATTEMPT_BUDGET,
            elapsed_seconds=round(max(0.0, float(
                self.monotonic_clock() - started if elapsed is None else elapsed
            )), 3),
            case_revision=case_revision,
            source_fingerprint=source_fingerprint,
            issue_codes=tuple(dict.fromkeys(
                code for code in issues if isinstance(code, str)
            )),
            status_snapshot=status_snapshot,
            act_snapshot=act_snapshot,
            continuation_token=continuation_token,
        )

    @classmethod
    def _fingerprint(cls, value):
        try:
            encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError):
            return None
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @classmethod
    def _observation_idempotency_key(cls, case_id, declaration_id, source_fingerprint):
        fingerprint = cls._fingerprint({
            "case_id": case_id,
            "declaration_id": declaration_id,
            "source_fingerprint": source_fingerprint,
        })
        return "refresh_" + (fingerprint or uuid4().hex)[:40]

    @staticmethod
    def _remaining_attempts(trace):
        return max(0, FifoCostTransitionSupplyRefreshService.HTTP_ATTEMPT_BUDGET
                   - trace.ozon_requests_reserved)
