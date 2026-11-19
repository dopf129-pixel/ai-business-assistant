"""Bounded, read-only source entry point for automatic FIFO supply evidence.

Order-list/details scans use the local wrapper contracts and remain partial
until raw state/cursor/date coverage is verified. Documented bundle pages are
parsed strictly, and their quantities remain declared composition only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import sqlite3
import threading
from time import monotonic
from uuid import uuid4

from services.fifo_cost_batch_bundle_normalizer import (
    FifoCostBatchBundleNormalizer,
    FifoCostBatchSupplyCompositionResult,
)
from services.fifo_cost_batch_rule_contracts import (
    DispatchTimeStatus,
    SupplyMembership,
    SupplyScanCoverage,
    SupplySkuObservation,
)
from services.fifo_cost_batch_scan_checkpoint_service import FifoCostBatchScanCheckpointService
from services.fifo_cost_batch_supply_deduplicator import FifoCostBatchSupplyDeduplicator
from services.fifo_cost_batch_supply_store import FifoCostBatchSupplyStore
from services.fifo_cost_batch_rule_service import FifoCostBatchRuleService
from services.fifo_cost_source_collection_service import FifoCostSourceCollectionService
from services.fifo_cost_source_normalizer import FifoCostSourceNormalizer
from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    EvidenceSourceKind,
    NormalizedSupplyStatus,
    ScopeIdentity,
    SupplyReferenceKind,
    supply_reference_digest,
)
from services.period_profit_operation_diagnostics import (
    PeriodProfitOperationTrace,
    activate_period_profit_trace,
    current_period_profit_trace,
    reset_period_profit_trace,
)
from services.tenant_cipher_provider import decrypt_tenant_value, encrypt_tenant_value


@dataclass(frozen=True, slots=True)
class FifoCostBatchSupplyCollectionResult:
    status: str
    source_status: str
    read_only: bool
    actual_http_attempts: int
    http_attempt_cap: int
    elapsed_seconds: float
    case_revision: int | None
    rule_revision: int | None
    issue_codes: tuple[str, ...]
    continuation_token: str | None = None
    orders_observed: int = 0
    supplies_observed: int = 0
    pagination_complete: bool = False
    details_complete: bool = False
    scan_id: str | None = None
    scan_revision: int | None = None
    candidates_observed: int = 0
    sku_composition_complete: bool = False


@dataclass(frozen=True, slots=True)
class _BatchScanCheckpoint:
    scope_fingerprint: str
    cursor: str | None
    seen_cursors: tuple[str, ...]
    seen_order_ids: tuple[str, ...]
    seen_supply_ids: tuple[str, ...]
    pages_scanned: int
    expires_at: float


class FifoCostBatchSupplySourceService:
    """Validate scope and collect bounded order-list/details evidence.

    Raw source responses are never returned or persisted. Bundle composition
    is read through its documented page shape but is not dispatch/acceptance
    evidence. Durable checkpoints and publication are handled by later stages.
    Durable checkpoints and publication are handled by later stages.
    """

    TIME_BUDGET_SECONDS = 20.0
    HTTP_ATTEMPT_BUDGET = 10
    REQUEST_TIMEOUT_SECONDS = 8.0
    PAGE_SIZE = 100
    SUPPLY_LIST_PAGE_SIZE = 10
    DETAILS_BATCH_SIZE = 50
    MAX_SCAN_ORDERS = 2_000
    MAX_SCAN_SUPPLIES = 5_000
    MAX_SCAN_PAGES = 100
    CHECKPOINT_TTL_SECONDS = 30 * 60
    MAX_CHECKPOINTS = 64
    SUPPLY_LIST_SORT_BY = "ORDER_CREATION"
    SUPPLY_LIST_SORT_DIR = "DESC"
    SOURCE_CONTRACT_VERSION = "OZON_SUPPLY_BUNDLE_V1_ORDER_LIST_DESC_V2"
    MAX_PENDING_SUPPLIES = 64
    REQUEST_ALLOWLIST = {
        "get_supply_orders_list": "SUPPLY_ORDER_LIST_V3",
        "get_supply_orders_details": "SUPPLY_ORDER_DETAILS_V3",
        "get_supply_order_bundle": "SUPPLY_ORDER_BUNDLE_V1",
    }
    _ID = re.compile(r"^[0-9]{1,19}$")
    _CURSOR = re.compile(r"(?s)^.{1,256}$")

    def __init__(
        self, *, rule_service: FifoCostBatchRuleService, ozon_client,
        monotonic_clock=monotonic, scan_checkpoint_service=None, utc_clock=None,
    ):
        if not isinstance(rule_service, FifoCostBatchRuleService):
            raise TypeError("FIFO_BATCH_RULE_SERVICE_INVALID")
        self.rule_service = rule_service
        self.ozon_client = ozon_client
        self.monotonic_clock = monotonic_clock
        if scan_checkpoint_service is not None and not isinstance(
            scan_checkpoint_service, FifoCostBatchScanCheckpointService,
        ):
            raise TypeError("FIFO_BATCH_SCAN_CHECKPOINT_SERVICE_INVALID")
        self.scan_checkpoint_service = scan_checkpoint_service
        self.utc_clock = utc_clock or rule_service._now_provider
        self._checkpoints: dict[str, _BatchScanCheckpoint] = {}
        self._checkpoint_lock = threading.RLock()

    def get_supply_composition(
        self, scope: ScopeIdentity, case_id: str, expected_case_revision: int,
        rule_revision: int, supply_ref_digest: str, *, bundle_id: str | None = None,
        operation_trace=None,
    ) -> FifoCostBatchSupplyCompositionResult:
        """Read one nested supply's exact bundle; expose declared quantity only.

        The caller passes the bundle ID from the exact nested supply. Since
        response rows do not echo that ID, this method requests one bundle at a
        time. Raw identifiers and descriptions are never returned.
        """
        if (
            not isinstance(supply_ref_digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", supply_ref_digest)
        ):
            return FifoCostBatchBundleNormalizer.unknown(
                "FIFO_BATCH_BUNDLE_SUPPLY_REFERENCE_INVALID",
                status="CONFLICT", source_status="CONFLICT",
            )
        parent = operation_trace or current_period_profit_trace()
        if parent is not None and not isinstance(parent, PeriodProfitOperationTrace):
            return FifoCostBatchBundleNormalizer.unknown(
                "FIFO_BATCH_OPERATION_TRACE_INVALID", status="INVALID",
                source_status="CONFLICT",
            )
        basis = self.rule_service.read_collection_basis(
            scope, case_id, expected_case_revision, rule_revision,
        )
        if basis.get("error"):
            code = str(basis.get("code") or "")
            conflict = (
                "CONFLICT" if code.endswith("CONFLICT") or code.endswith("MISMATCH")
                else "BLOCKED"
            )
            return FifoCostBatchBundleNormalizer.unknown(
                code if code.startswith("FIFO_") else
                "FIFO_BATCH_BUNDLE_COLLECTION_BASIS_UNAVAILABLE",
                case_revision=(expected_case_revision
                               if type(expected_case_revision) is int else None),
                rule_revision=(rule_revision if type(rule_revision) is int else None),
                status=conflict, source_status=conflict,
            )
        if (
            not isinstance(bundle_id, str) or not bundle_id
            or len(bundle_id) > 256
        ):
            return FifoCostBatchBundleNormalizer.unknown(
                "FIFO_BATCH_BUNDLE_REFERENCE_UNAVAILABLE",
                case_revision=basis["case_revision"],
                rule_revision=basis["rule_revision"],
            )
        trace = PeriodProfitOperationTrace(
            operation="fifo_batch_supply_composition",
            time_budget_seconds=self.TIME_BUDGET_SECONDS,
            ozon_request_budget=self.HTTP_ATTEMPT_BUDGET,
            clock=self.monotonic_clock,
            parent=parent,
        )
        attempts = 0
        cursor = None
        seen_cursors = set()
        parsed_count = 0
        expected_total = None
        target_rows = []
        trace_token = activate_period_profit_trace(trace)
        issue = None
        status = "UNKNOWN"
        source_status = "NOT_VERIFIED"
        try:
            while True:
                if self._remaining_attempts(trace) < 1 or trace.remaining_seconds() <= 0:
                    issue = "FIFO_BATCH_BUNDLE_BUDGET_EXHAUSTED"
                    source_status = "PARTIAL"
                    break
                response, used = self._request(
                    trace, "get_supply_order_bundle", attempts,
                    [bundle_id], last_id=cursor, limit=self.PAGE_SIZE,
                )
                attempts += used
                if self._failed(response):
                    issue = "FIFO_BATCH_BUNDLE_UNAVAILABLE"
                    source_status = "UNAVAILABLE"
                    break
                page_result = FifoCostBatchBundleNormalizer.parse_documented_page(
                    response, requested_limit=self.PAGE_SIZE,
                    prior_item_count=parsed_count,
                )
                if page_result.page is None:
                    issue = page_result.issue_codes[0]
                    source_status = "CONFLICT"
                    break
                page = page_result.page
                if expected_total is None:
                    expected_total = page.total_count
                elif page.total_count != expected_total:
                    issue = "FIFO_BATCH_BUNDLE_TOTAL_COUNT_CHANGED"
                    source_status = "CONFLICT"
                    break
                parsed_count += len(page.items)
                for item in page.items:
                    if str(item.sku) != scope.sku:
                        continue
                    if (
                        item.product_id is None or item.offer_id is None
                        or (
                            scope.product_id is not None
                            and str(scope.product_id).isascii()
                            and str(scope.product_id).isdigit()
                            and str(item.product_id) != str(scope.product_id)
                        )
                        or (
                            scope.offer_id is not None
                            and str(item.offer_id) != scope.offer_id
                        )
                    ):
                        issue = "FIFO_BATCH_BUNDLE_SKU_MAPPING_CONFLICT"
                        source_status = "CONFLICT"
                        break
                    target_rows.append(item)
                if issue is not None:
                    break
                if not page.has_next:
                    if len(target_rows) == 1:
                        status = "COMPLETE"
                        source_status = "DOCUMENTED_BUNDLE_COMPOSITION"
                    elif len(target_rows) > 1:
                        issue = "FIFO_BATCH_BUNDLE_DUPLICATE_SKU_MAPPING"
                        source_status = "CONFLICT"
                    else:
                        issue = "FIFO_BATCH_BUNDLE_TARGET_SKU_NOT_FOUND"
                        source_status = "NOT_VERIFIED"
                    break
                if page.last_id in seen_cursors or page.last_id == cursor:
                    issue = "FIFO_BATCH_BUNDLE_CURSOR_NOT_ADVANCING"
                    source_status = "CONFLICT"
                    break
                seen_cursors.add(page.last_id)
                cursor = page.last_id
        finally:
            reset_period_profit_trace(trace_token)

        planned = target_rows[0].quantity if status == "COMPLETE" else None
        if issue is None and status != "COMPLETE":
            issue = "FIFO_BATCH_BUNDLE_COMPOSITION_INCOMPLETE"
        return FifoCostBatchSupplyCompositionResult(
            status=status, source_status=source_status, read_only=True,
            actual_http_attempts=attempts,
            case_revision=basis["case_revision"],
            rule_revision=basis["rule_revision"],
            planned_quantity=planned, shipped_quantity=None,
            planned_explicit_zero=planned == 0, shipped_explicit_zero=False,
            issue_codes=() if issue is None else (issue,),
        )

    def read_owner_candidate_labels(
        self, *, scope, case_id, tenant_fingerprint, scan_id, record_keys,
    ):
        """Return unique masked supply-ID suffixes; never return full IDs."""
        if (
            self.scan_checkpoint_service is None
            or not isinstance(scope, ScopeIdentity)
            or not isinstance(record_keys, tuple)
            or not 1 <= len(record_keys) <= 8
            or len(set(record_keys)) != len(record_keys)
        ):
            return {"error": True, "code": "FIFO_BATCH_DISPLAY_REFERENCE_UNAVAILABLE"}
        connection = None
        try:
            connection = self.scan_checkpoint_service.repository.get_connection()
            rows = FifoCostBatchSupplyStore.read_scan_observations(
                connection, scope=scope, case_id=case_id,
                tenant_fingerprint=tenant_fingerprint, scan_id=scan_id, limit=10_000,
            )
            latest = {}
            for row in rows:
                current = latest.get(row["record_key"])
                if current is None or row["observation_revision"] > current["observation_revision"]:
                    latest[row["record_key"]] = row
            identifiers = {}
            for key, row in latest.items():
                decrypted = decrypt_tenant_value(
                    bytes(row["encrypted_lookup_payload"]).decode("ascii"),
                )
                payload = json.loads(decrypted) if isinstance(decrypted, str) else None
                if not isinstance(payload, dict):
                    return {"error": True, "code": "FIFO_BATCH_DISPLAY_REFERENCE_UNAVAILABLE"}
                supply_id = payload.get("supply_id")
                order_id = payload.get("order_id")
                if (
                    not isinstance(supply_id, str) or not re.fullmatch(r"[0-9]{7,19}", supply_id)
                    or not isinstance(order_id, str) or not re.fullmatch(r"[0-9]{7,19}", order_id)
                ):
                    return {"error": True, "code": "FIFO_BATCH_DISPLAY_REFERENCE_UNAVAILABLE"}
                identifiers[key] = (supply_id, order_id)
            if any(key not in identifiers for key in record_keys):
                return {"error": True, "code": "FIFO_BATCH_DISPLAY_REFERENCE_UNAVAILABLE"}
            labels = self._unique_masked_reference_labels(identifiers)
            if labels is None:
                return {"error": True, "code": "FIFO_BATCH_DISPLAY_REFERENCE_AMBIGUOUS"}
            return {"error": False, "labels": {key: labels[key] for key in record_keys}}
        except (OSError, sqlite3.Error, TypeError, ValueError, KeyError, json.JSONDecodeError):
            return {"error": True, "code": "FIFO_BATCH_DISPLAY_REFERENCE_UNAVAILABLE"}
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _unique_masked_reference_labels(identifiers):
        values = tuple(identifiers.values())
        for length in range(6, 13):
            if any(len(supply_id) <= length for supply_id, _ in values):
                continue
            suffixes = [supply_id[-length:] for supply_id, _ in values]
            if len(set(suffixes)) == len(suffixes):
                return {
                    key: f"••••{supply_id[-length:]}"
                    for key, (supply_id, _order_id) in identifiers.items()
                }
        for supply_length in range(6, 13):
            for order_length in range(6, 13):
                if any(
                    len(supply_id) <= supply_length or len(order_id) <= order_length
                    for supply_id, order_id in values
                ):
                    continue
                suffixes = [
                    (supply_id[-supply_length:], order_id[-order_length:])
                    for supply_id, order_id in values
                ]
                if len(set(suffixes)) == len(suffixes):
                    return {
                        key: f"••••{supply[-supply_length:]} / заявка ••••{order[-order_length:]}"
                        for key, (supply, order) in identifiers.items()
                    }
        return None

    def collect_supplies(
        self, scope: ScopeIdentity, case_id: str, expected_case_revision: int,
        rule_revision: int, continuation_token=None, operation_trace=None,
    ) -> FifoCostBatchSupplyCollectionResult:
        if self.scan_checkpoint_service is not None:
            return self._collect_supplies_with_durable_checkpoint(
                scope, case_id, expected_case_revision, rule_revision,
                continuation_token=continuation_token,
                operation_trace=operation_trace,
            )
        started = self.monotonic_clock()
        parent = operation_trace or current_period_profit_trace()
        if parent is not None and not isinstance(parent, PeriodProfitOperationTrace):
            return self._result(
                started=started, status="INVALID", source_status="CONFLICT",
                issue_codes=("FIFO_BATCH_OPERATION_TRACE_INVALID",),
                case_revision=None, rule_revision=None,
            )
        trace = PeriodProfitOperationTrace(
            operation="fifo_batch_supply_collection",
            time_budget_seconds=self.TIME_BUDGET_SECONDS,
            ozon_request_budget=self.HTTP_ATTEMPT_BUDGET,
            clock=self.monotonic_clock,
            parent=parent,
        )

        # This tenant-scoped read verifies owner/store/SKU, case revision,
        # AUTO_FROM_SUPPLIES, and active rule revision before any HTTP attempt.
        basis = self.rule_service.read_collection_basis(
            scope, case_id, expected_case_revision, rule_revision,
        )
        if basis.get("error"):
            code = str(basis.get("code") or "")
            conflict_codes = {
                "FIFO_BATCH_CASE_REVISION_CONFLICT",
                "FIFO_BATCH_RULE_REVISION_CONFLICT",
                "FIFO_BATCH_RULE_SCOPE_MISMATCH",
            }
            return self._result(
                started=started,
                status="CONFLICT" if code in conflict_codes else "BLOCKED",
                source_status="CONFLICT" if code in conflict_codes else "UNAVAILABLE",
                issue_codes=(code if code.startswith("FIFO_") else
                             "FIFO_BATCH_COLLECTION_BASIS_UNAVAILABLE",),
                case_revision=(expected_case_revision
                               if type(expected_case_revision) is int else None),
                rule_revision=(rule_revision if type(rule_revision) is int else None),
            )

        scope_fingerprint = self._fingerprint({
            "owner": scope.owner_id,
            "store": scope.store_id,
            "product": scope.product_id,
            "offer": scope.offer_id,
            "sku": scope.sku,
            "case_id": case_id,
            "case_revision": basis["case_revision"],
            "rule_id": basis["rule_id"],
            "rule_revision": basis["rule_revision"],
            "rule_fingerprint": basis["rule_fingerprint"],
            "source_profile": self.SOURCE_CONTRACT_VERSION,
        })
        state, checkpoint_error = self._take_checkpoint(
            continuation_token, scope_fingerprint=scope_fingerprint,
        )
        if checkpoint_error:
            return self._result(
                started=started, status="CONFLICT", source_status="CONFLICT",
                issue_codes=(checkpoint_error,),
                case_revision=basis["case_revision"],
                rule_revision=basis["rule_revision"],
            )
        if state is None:
            state = {
                "cursor": None,
                "seen_cursors": [],
                "seen_order_ids": [],
                "seen_supply_ids": [],
                "pages_scanned": 0,
            }

        trace_token = activate_period_profit_trace(trace)
        actual_attempts = 0
        result_status = "PARTIAL"
        source_status = "PARTIAL"
        issues: list[str] = []
        pagination_complete = False
        details_complete = False
        resumable = False
        stop = False
        try:
            while not stop:
                if state["pages_scanned"] >= self.MAX_SCAN_PAGES:
                    issues.append("FIFO_BATCH_SUPPLY_PAGE_LIMIT_REACHED")
                    break
                if self._remaining_attempts(trace) < 3:
                    issues.append("FIFO_BATCH_SOURCE_BUDGET_EXHAUSTED")
                    resumable = True
                    break
                page, used = self._request(
                    trace, "get_supply_orders_list", actual_attempts,
                    list(FifoCostSourceCollectionService.ACTIVE_SUPPLY_STATES),
                    last_id=state["cursor"], limit=self.PAGE_SIZE,
                    sort_by=self.SUPPLY_LIST_SORT_BY,
                    sort_dir=self.SUPPLY_LIST_SORT_DIR,
                )
                actual_attempts += used
                if self._failed(page):
                    if self._is_rejected_supply_list_request(page):
                        issues.append("FIFO_BATCH_SUPPLY_LIST_REQUEST_REJECTED")
                    issues.append("FIFO_BATCH_SUPPLY_LIST_UNAVAILABLE")
                    resumable = bool(state["cursor"] is not None)
                    break
                order_ids = self._order_ids(page.get("order_ids"))
                cursor, cursor_valid = self._cursor(page.get("last_id"))
                if order_ids is None:
                    result_status = source_status = "CONFLICT"
                    issues.append("FIFO_BATCH_SUPPLY_LIST_INVALID")
                    break
                if not cursor_valid:
                    result_status = source_status = "CONFLICT"
                    issues.append("FIFO_BATCH_SUPPLY_CURSOR_INVALID")
                    break
                if not order_ids:
                    if cursor is not None:
                        result_status = source_status = "CONFLICT"
                        issues.append("FIFO_BATCH_SUPPLY_CURSOR_WITH_EMPTY_PAGE")
                    else:
                        pagination_complete = True
                        details_complete = True
                    break
                if cursor is not None and cursor in state["seen_cursors"]:
                    result_status = source_status = "CONFLICT"
                    issues.append("FIFO_BATCH_SUPPLY_CURSOR_NOT_ADVANCING")
                    break
                if cursor is None and len(order_ids) == self.PAGE_SIZE:
                    issues.append("FIFO_BATCH_SUPPLY_CURSOR_PROOF_MISSING")
                unique_order_ids = list(dict.fromkeys(order_ids))
                if len(unique_order_ids) != len(order_ids) or any(
                    item in state["seen_order_ids"] for item in unique_order_ids
                ):
                    issues.append("FIFO_BATCH_SUPPLY_LIST_MUTATED_DURING_SCAN")
                    unique_order_ids = [
                        item for item in unique_order_ids
                        if item not in state["seen_order_ids"]
                    ]
                if len(state["seen_order_ids"]) + len(unique_order_ids) > self.MAX_SCAN_ORDERS:
                    issues.append("FIFO_BATCH_SUPPLY_ORDER_LIMIT_REACHED")
                    break

                details, used, detail_issue = self._load_order_details(
                    trace, unique_order_ids, actual_attempts,
                )
                actual_attempts += used
                if detail_issue:
                    issues.append(detail_issue)
                    resumable = bool(state["cursor"] is not None or cursor is not None)
                    break
                supplies, state_issues, structure_issue = self._extract_supply_ids(details)
                issues.extend(state_issues)
                if structure_issue:
                    result_status = source_status = "CONFLICT"
                    issues.append(structure_issue)
                    break
                known_supply_ids = set(state["seen_supply_ids"])
                new_supply_ids = []
                for supply_id in supplies:
                    if supply_id not in known_supply_ids:
                        new_supply_ids.append(supply_id)
                        known_supply_ids.add(supply_id)
                if len(state["seen_supply_ids"]) + len(new_supply_ids) > self.MAX_SCAN_SUPPLIES:
                    issues.append("FIFO_BATCH_SUPPLY_ROW_LIMIT_REACHED")
                    break
                state["seen_order_ids"].extend(unique_order_ids)
                state["seen_supply_ids"].extend(new_supply_ids)
                state["pages_scanned"] += 1
                if cursor is None:
                    if len(order_ids) < self.PAGE_SIZE:
                        pagination_complete = True
                    details_complete = pagination_complete
                    stop = True
                else:
                    state["seen_cursors"].append(cursor)
                    state["cursor"] = cursor
                    if self._remaining_attempts(trace) < 3:
                        issues.append("FIFO_BATCH_SOURCE_BUDGET_EXHAUSTED")
                        resumable = True
                        break
        finally:
            reset_period_profit_trace(trace_token)

        if not result_status == "CONFLICT" and not result_status == "UNAVAILABLE":
            issues.append("FIFO_BATCH_SUPPLY_STATE_PROFILE_UNVERIFIED")
            if (
                actual_attempts == 0
                and not pagination_complete
                and "FIFO_BATCH_SOURCE_BUDGET_EXHAUSTED" not in issues
            ):
                result_status = "UNAVAILABLE"
                source_status = "UNAVAILABLE"
        continuation = None
        if resumable and not pagination_complete:
            continuation = self._save_checkpoint(
                _BatchScanCheckpoint(
                    scope_fingerprint=scope_fingerprint,
                    cursor=state["cursor"],
                    seen_cursors=tuple(state["seen_cursors"]),
                    seen_order_ids=tuple(state["seen_order_ids"]),
                    seen_supply_ids=tuple(state["seen_supply_ids"]),
                    pages_scanned=state["pages_scanned"],
                    expires_at=self.monotonic_clock() + self.CHECKPOINT_TTL_SECONDS,
                )
            )
            if continuation is None:
                issues.append("FIFO_BATCH_SUPPLY_CHECKPOINT_UNAVAILABLE")

        return self._result(
            started=started, status=result_status, source_status=source_status,
            issue_codes=issues, case_revision=basis["case_revision"],
            rule_revision=basis["rule_revision"], actual_attempts=actual_attempts,
            continuation_token=continuation,
            orders_observed=len(state["seen_order_ids"]),
            supplies_observed=len(state["seen_supply_ids"]),
            pagination_complete=pagination_complete,
            details_complete=details_complete,
        )

    def _collect_supplies_with_durable_checkpoint(
        self, scope, case_id, expected_case_revision, rule_revision, *,
        continuation_token=None, operation_trace=None,
    ):
        """Collect exact-SKU bundle rows into the existing encrypted scan ledger.

        Ozon bundle quantity is stored only as planned composition. The API has
        not supplied a dispatch or receipt date, so membership remains owner
        review and every coverage dimension requiring those facts stays false.
        """
        started = self.monotonic_clock()
        parent = operation_trace or current_period_profit_trace()
        if parent is not None and not isinstance(parent, PeriodProfitOperationTrace):
            return self._result(
                started=started, status="INVALID", source_status="CONFLICT",
                issue_codes=("FIFO_BATCH_OPERATION_TRACE_INVALID",),
                case_revision=None, rule_revision=None,
            )
        basis = self.rule_service.read_collection_basis(
            scope, case_id, expected_case_revision, rule_revision,
        )
        if basis.get("error"):
            code = str(basis.get("code") or "")
            conflict_codes = {
                "FIFO_BATCH_CASE_REVISION_CONFLICT",
                "FIFO_BATCH_RULE_REVISION_CONFLICT",
                "FIFO_BATCH_RULE_SCOPE_MISMATCH",
            }
            return self._result(
                started=started,
                status="CONFLICT" if code in conflict_codes else "BLOCKED",
                source_status="CONFLICT" if code in conflict_codes else "UNAVAILABLE",
                issue_codes=(code if code.startswith("FIFO_") else
                             "FIFO_BATCH_COLLECTION_BASIS_UNAVAILABLE",),
                case_revision=expected_case_revision
                if type(expected_case_revision) is int else None,
                rule_revision=rule_revision if type(rule_revision) is int else None,
            )

        checkpoint = self.scan_checkpoint_service
        repository = checkpoint.repository
        tenant = repository._tenant_scope(scope.store_id)
        if tenant.get("error") or not isinstance(tenant.get("tenant_fingerprint"), str):
            return self._result(
                started=started, status="BLOCKED", source_status="UNAVAILABLE",
                issue_codes=("FIFO_BATCH_SCAN_TENANT_SCOPE_UNAVAILABLE",),
                case_revision=basis["case_revision"], rule_revision=basis["rule_revision"],
            )
        tenant_fingerprint = tenant["tenant_fingerprint"]
        supported_states = tuple(sorted(FifoCostSourceCollectionService.ACTIVE_SUPPLY_STATES))
        scan_revision = 0
        if continuation_token is None:
            scan_id = "scan_" + uuid4().hex
            state = self._empty_durable_state()
            try:
                started_at = self._next_checkpoint_timestamp(
                    scope, case_id, tenant_fingerprint,
                )
            except Exception:
                return self._result(
                    started=started, status="UNAVAILABLE", source_status="UNAVAILABLE",
                    issue_codes=("FIFO_BATCH_SCAN_STORAGE_UNAVAILABLE",),
                    case_revision=basis["case_revision"],
                    rule_revision=basis["rule_revision"], scan_id=scan_id,
                )
            staging_coverage = self._scan_coverage(
                scan_id=scan_id, revision=1, scope=scope, case_id=case_id,
                rule_revision=basis["rule_revision"], captured_at=started_at,
                supported_states=supported_states, state=state,
                details_complete=False, issue_codes=(),
                continuation_token=f"{scan_id}_r1",
            )
            staging = checkpoint.commit_page(
                coverage=staging_coverage, tenant_fingerprint=tenant_fingerprint,
                rule_id=basis["rule_id"], rule_fingerprint=basis["rule_fingerprint"],
                expected_case_revision=basis["case_revision"],
                expected_scan_revision=0, observations=(), status="STAGING",
                expires_at=self._timestamp_plus(started_at, checkpoint.TTL_SECONDS),
                updated_at=started_at, continuation_state=state, now=started_at,
            )
            if staging.get("error"):
                return self._result(
                    started=started, status="UNAVAILABLE", source_status="UNAVAILABLE",
                    issue_codes=(staging.get("code", "FIFO_BATCH_SCAN_STORAGE_UNAVAILABLE"),),
                    case_revision=basis["case_revision"],
                    rule_revision=basis["rule_revision"], scan_id=scan_id,
                )
            scan_revision = 1
        else:
            resumed = checkpoint.load_continuation(
                scope=scope, case_id=case_id,
                tenant_fingerprint=tenant_fingerprint,
                rule_id=basis["rule_id"], rule_revision=basis["rule_revision"],
                rule_fingerprint=basis["rule_fingerprint"],
                expected_case_revision=basis["case_revision"],
                source_contract_version=self.SOURCE_CONTRACT_VERSION,
                supported_state_profile=supported_states,
                requested_from=None, requested_through=None,
                continuation_token=continuation_token,
            )
            if resumed.get("error"):
                return self._result(
                    started=started, status="CONFLICT", source_status="CONFLICT",
                    issue_codes=(resumed.get("code", "FIFO_BATCH_SCAN_TOKEN_INVALID"),),
                    case_revision=basis["case_revision"],
                    rule_revision=basis["rule_revision"],
                )
            scan_id = resumed["scan_id"]
            scan_revision = resumed["scan_revision"]
            state = self._upgrade_durable_state(resumed["continuation_state"])

        scan_refs_result = self._read_scan_ref_fingerprints(
            scope, case_id, tenant_fingerprint, scan_id,
        )
        if scan_refs_result.get("error"):
            code = scan_refs_result.get("code", "FIFO_BATCH_SCAN_STORAGE_UNAVAILABLE")
            return self._result(
                started=started,
                status="CONFLICT" if code == "FIFO_BATCH_SCAN_REFERENCE_CONFLICT" else "UNAVAILABLE",
                source_status="CONFLICT" if code == "FIFO_BATCH_SCAN_REFERENCE_CONFLICT" else "UNAVAILABLE",
                issue_codes=(code,), case_revision=basis["case_revision"],
                rule_revision=basis["rule_revision"], scan_id=scan_id,
                scan_revision=scan_revision,
            )
        scan_refs = scan_refs_result["items"]

        trace = PeriodProfitOperationTrace(
            operation="fifo_batch_supply_collection",
            time_budget_seconds=self.TIME_BUDGET_SECONDS,
            ozon_request_budget=self.HTTP_ATTEMPT_BUDGET,
            clock=self.monotonic_clock,
            parent=parent,
        )
        trace_token = activate_period_profit_trace(trace)
        actual_attempts = 0
        issues = []
        new_observations = []
        list_complete = state["list_complete"]
        details_complete = True
        source_conflict = False
        progress_made = False
        list_error_without_data = False
        try:
            while True:
                if not state["pending_supplies"]:
                    if state["list_complete"]:
                        break
                    if self._remaining_attempts(trace) < 2:
                        issues.append("FIFO_BATCH_SOURCE_BUDGET_EXHAUSTED")
                        break
                    page, used = self._request(
                        trace, "get_supply_orders_list", actual_attempts,
                        list(FifoCostSourceCollectionService.ACTIVE_SUPPLY_STATES),
                        last_id=state["cursor"], limit=self.SUPPLY_LIST_PAGE_SIZE,
                        sort_by=self.SUPPLY_LIST_SORT_BY,
                        sort_dir=self.SUPPLY_LIST_SORT_DIR,
                    )
                    actual_attempts += used
                    if self._failed(page):
                        if self._is_rejected_supply_list_request(page):
                            issues.append("FIFO_BATCH_SUPPLY_LIST_REQUEST_REJECTED")
                        issues.append("FIFO_BATCH_SUPPLY_LIST_UNAVAILABLE")
                        list_error_without_data = not progress_made
                        break
                    order_ids = self._order_ids(page.get("order_ids"))
                    cursor, cursor_valid = self._cursor(page.get("last_id"))
                    if order_ids is None or not cursor_valid:
                        source_conflict = True
                        issues.append("FIFO_BATCH_SUPPLY_LIST_INVALID")
                        break
                    if not order_ids:
                        if cursor is not None:
                            source_conflict = True
                            issues.append("FIFO_BATCH_SUPPLY_CURSOR_WITH_EMPTY_PAGE")
                        else:
                            state["list_complete"] = True
                            list_complete = True
                            progress_made = True
                        break
                    if cursor is not None:
                        cursor_digest = self._fingerprint(cursor)
                        if cursor_digest in state["seen_cursor_digests"]:
                            source_conflict = True
                            issues.append("FIFO_BATCH_SUPPLY_CURSOR_NOT_ADVANCING")
                            break
                    elif len(order_ids) == self.SUPPLY_LIST_PAGE_SIZE:
                        source_conflict = True
                        issues.append("FIFO_BATCH_SUPPLY_CURSOR_PROOF_MISSING")
                        break
                    if state["pages_scanned"] >= self.MAX_SCAN_PAGES:
                        issues.append("FIFO_BATCH_SUPPLY_PAGE_LIMIT_REACHED")
                        break
                    if len(set(order_ids)) != len(order_ids):
                        source_conflict = True
                        issues.append("FIFO_BATCH_SUPPLY_LIST_MUTATED_DURING_SCAN")
                        break
                    if state["orders_seen"] + len(order_ids) > self.MAX_SCAN_ORDERS:
                        issues.append("FIFO_BATCH_SUPPLY_ORDER_LIMIT_REACHED")
                        break
                    details, used, detail_issue = self._load_order_details(
                        trace, order_ids, actual_attempts,
                    )
                    actual_attempts += used
                    if detail_issue:
                        details_complete = False
                        issues.append(detail_issue)
                        list_error_without_data = not progress_made
                        break
                    refs, ref_issues, structure_issue = self._extract_supply_references(details)
                    issues.extend(ref_issues)
                    if structure_issue:
                        source_conflict = True
                        issues.append(structure_issue)
                        break
                    if state["supplies_seen"] + len(refs) > self.MAX_SCAN_SUPPLIES:
                        issues.append("FIFO_BATCH_SUPPLY_ROW_LIMIT_REACHED")
                        break
                    pending_seen = {
                        (item["order_id"], item["supply_id"])
                        for item in state["pending_supplies"]
                    }
                    page_seen = set()
                    for ref in refs:
                        pair = (ref["order_id"], ref["supply_id"])
                        if pair in pending_seen or pair in page_seen:
                            source_conflict = True
                            issues.append("FIFO_BATCH_SUPPLY_LIST_MUTATED_DURING_SCAN")
                            break
                        page_seen.add(pair)
                        state["pending_supplies"].append({
                            **ref,
                            "bundle_cursor": None,
                            "bundle_total": None,
                            "bundle_parsed": None,
                            "bundle_seen_cursor_digests": (),
                            "target_quantity": None,
                            "target_rows": 0,
                        })
                    if source_conflict:
                        break
                    if len(state["pending_supplies"]) > self.MAX_PENDING_SUPPLIES:
                        issues.append("FIFO_BATCH_PENDING_SUPPLY_LIMIT_REACHED")
                        source_conflict = True
                        break
                    state["orders_seen"] += len(order_ids)
                    state["supplies_seen"] += len(refs)
                    state["pages_scanned"] += 1
                    if cursor is None:
                        state["list_complete"] = True
                    else:
                        state["cursor"] = cursor
                        state["seen_cursor_digests"].append(cursor_digest)
                    list_complete = state["list_complete"]
                    progress_made = True
                    continue

                if self._remaining_attempts(trace) < 1 or trace.remaining_seconds() <= 0:
                    issues.append("FIFO_BATCH_SOURCE_BUDGET_EXHAUSTED")
                    break
                pending = dict(state["pending_supplies"][0])
                bundle_id = pending["bundle_id"]
                if bundle_id is None:
                    state["pending_supplies"].pop(0)
                    state["unknown_supply_count"] += 1
                    issues.append("FIFO_BATCH_BUNDLE_REFERENCE_UNAVAILABLE")
                    progress_made = True
                    continue
                bundle_response, used = self._request(
                    trace, "get_supply_order_bundle", actual_attempts,
                    [bundle_id], last_id=pending["bundle_cursor"],
                    limit=self.PAGE_SIZE,
                )
                actual_attempts += used
                if self._failed(bundle_response):
                    issues.append("FIFO_BATCH_BUNDLE_UNAVAILABLE")
                    break
                prior_count = pending["bundle_parsed"] or 0
                parsed = FifoCostBatchBundleNormalizer.parse_documented_page(
                    bundle_response, requested_limit=self.PAGE_SIZE,
                    prior_item_count=prior_count,
                )
                if parsed.page is None:
                    state["pending_supplies"].pop(0)
                    state["unknown_supply_count"] += 1
                    issues.extend(parsed.issue_codes)
                    progress_made = True
                    continue
                bundle_page = parsed.page
                if (
                    pending["bundle_total"] is not None
                    and pending["bundle_total"] != bundle_page.total_count
                ):
                    state["pending_supplies"].pop(0)
                    state["unknown_supply_count"] += 1
                    issues.append("FIFO_BATCH_BUNDLE_TOTAL_COUNT_CHANGED")
                    source_conflict = True
                    progress_made = True
                    continue
                target_quantity = pending["target_quantity"]
                target_rows = pending["target_rows"]
                mapping_conflict = False
                for item in bundle_page.items:
                    if str(item.sku) != scope.sku:
                        continue
                    if (
                        item.product_id is None or item.offer_id is None
                        or (
                            scope.product_id is not None
                            and str(scope.product_id).isascii()
                            and str(scope.product_id).isdigit()
                            and str(item.product_id) != str(scope.product_id)
                        )
                        or (
                            scope.offer_id is not None
                            and str(item.offer_id) != scope.offer_id
                        )
                    ):
                        mapping_conflict = True
                        break
                    target_rows += 1
                    if target_quantity is None:
                        target_quantity = item.quantity
                if mapping_conflict:
                    state["pending_supplies"].pop(0)
                    state["unknown_supply_count"] += 1
                    issues.append("FIFO_BATCH_BUNDLE_SKU_MAPPING_CONFLICT")
                    source_conflict = True
                    progress_made = True
                    continue
                pending["bundle_total"] = bundle_page.total_count
                pending["bundle_parsed"] = prior_count + len(bundle_page.items)
                pending["target_quantity"] = target_quantity
                pending["target_rows"] = target_rows
                if bundle_page.has_next:
                    cursor_digest = self._fingerprint(bundle_page.last_id)
                    seen_bundle_cursors = set(pending["bundle_seen_cursor_digests"])
                    if (
                        bundle_page.last_id == pending["bundle_cursor"]
                        or cursor_digest in seen_bundle_cursors
                        or len(seen_bundle_cursors) >= 100
                    ):
                        state["pending_supplies"].pop(0)
                        state["unknown_supply_count"] += 1
                        issues.append("FIFO_BATCH_BUNDLE_CURSOR_NOT_ADVANCING")
                        source_conflict = True
                    else:
                        pending["bundle_cursor"] = bundle_page.last_id
                        pending["bundle_seen_cursor_digests"] = tuple(
                            (*pending["bundle_seen_cursor_digests"], cursor_digest)
                        )
                        state["pending_supplies"][0] = pending
                else:
                    state["pending_supplies"].pop(0)
                    if target_rows == 1:
                        observation = self._make_bundle_observation(
                            scope=scope, ref=pending, planned_quantity=target_quantity,
                            captured_at=self._now_utc_text(),
                        )
                        prior_fingerprint = scan_refs.get(observation.record_key)
                        if prior_fingerprint is not None:
                            if prior_fingerprint != observation.source_fingerprint:
                                state["unknown_supply_count"] += 1
                                issues.append("FIFO_BATCH_SUPPLY_MUTATED_DURING_SCAN")
                                source_conflict = True
                            # The same exact immutable observation was already linked.
                        else:
                            new_observations.append(observation)
                            scan_refs[observation.record_key] = observation.source_fingerprint
                            state["candidate_count"] += 1
                    elif target_rows > 1:
                        state["unknown_supply_count"] += 1
                        issues.append("FIFO_BATCH_BUNDLE_DUPLICATE_SKU_MAPPING")
                        source_conflict = True
                    progress_made = True

        finally:
            reset_period_profit_trace(trace_token)

        if list_error_without_data and continuation_token is None:
            failed = self._fail_unstarted_scan(
                checkpoint=checkpoint, scope=scope, case_id=case_id,
                tenant_fingerprint=tenant_fingerprint, basis=basis,
                supported_states=supported_states, scan_id=scan_id,
                expected_scan_revision=scan_revision, state=state,
                issues=issues, observations=tuple(new_observations),
            )
            return self._result(
                started=started, status="UNAVAILABLE", source_status="UNAVAILABLE",
                issue_codes=issues, case_revision=basis["case_revision"],
                rule_revision=basis["rule_revision"], actual_attempts=actual_attempts,
                scan_id=scan_id,
                scan_revision=(scan_revision + 1 if not failed.get("error") else scan_revision),
            )
        if not progress_made and continuation_token is None:
            failure_issues = issues or ["FIFO_BATCH_SOURCE_NO_PROGRESS"]
            failed = self._fail_unstarted_scan(
                checkpoint=checkpoint, scope=scope, case_id=case_id,
                tenant_fingerprint=tenant_fingerprint, basis=basis,
                supported_states=supported_states, scan_id=scan_id,
                expected_scan_revision=scan_revision, state=state,
                issues=failure_issues, observations=tuple(new_observations),
            )
            return self._result(
                started=started, status="UNAVAILABLE", source_status="UNAVAILABLE",
                issue_codes=failure_issues,
                case_revision=basis["case_revision"],
                rule_revision=basis["rule_revision"], actual_attempts=actual_attempts,
                scan_id=scan_id,
                scan_revision=(scan_revision + 1 if not failed.get("error") else scan_revision),
            )

        state["pending_supplies"] = list(state["pending_supplies"])
        resumable = bool(state["pending_supplies"]) or not state["list_complete"]
        now_text = self._next_checkpoint_timestamp(
            scope, case_id, tenant_fingerprint, scan_id=scan_id,
        )
        expires_at = self._timestamp_plus(now_text, checkpoint.TTL_SECONDS)
        scan_status = "PARTIAL" if resumable else "PUBLISHED"
        next_revision = scan_revision + 1
        continuation_ref = f"{scan_id}_r{next_revision}" if resumable else None
        composition_complete = (
            state["list_complete"] and not state["pending_supplies"]
            and state["unknown_supply_count"] == 0
        )
        details_complete = details_complete and not state["pending_supplies"]
        if not list_complete or state["pending_supplies"]:
            issues.append("FIFO_BATCH_SUPPLY_STATE_PROFILE_UNVERIFIED")
        else:
            issues.append("FIFO_BATCH_SUPPLY_STATE_PROFILE_UNVERIFIED")
        coverage = SupplyScanCoverage(
            scan_id=scan_id, revision=next_revision, scope=scope, case_id=case_id,
            rule_revision=basis["rule_revision"], requested_from=None,
            requested_through=None, captured_at=now_text, source_as_of=None,
            supported_state_profile=supported_states,
            list_pagination_complete=state["list_complete"],
            details_complete=details_complete,
            sku_composition_complete=composition_complete,
            historical_window_proven=False, membership_complete=False,
            quantity_complete=False, physical_receipt_timing_complete=False,
            observation_set_fingerprint="0" * 64,
            source_contract_version=self.SOURCE_CONTRACT_VERSION,
            orders_seen=state["orders_seen"], supplies_seen=state["supplies_seen"],
            sku_rows_seen=state["candidate_count"], unknown_order_count=0,
            unknown_supply_count=state["unknown_supply_count"],
            unknown_quantity_supply_count=state["candidate_count"],
            issue_codes=tuple(dict.fromkeys(issues))[:32],
            resumable_token=continuation_ref,
        )
        committed = checkpoint.commit_page(
            coverage=coverage, tenant_fingerprint=tenant_fingerprint,
            rule_id=basis["rule_id"], rule_fingerprint=basis["rule_fingerprint"],
            expected_case_revision=basis["case_revision"],
            expected_scan_revision=scan_revision,
            observations=tuple(new_observations), status=scan_status,
            expires_at=expires_at, updated_at=now_text,
            continuation_state=state if resumable else None, now=now_text,
        )
        if committed.get("error"):
            commit_code = str(committed.get("code") or "")
            is_conflict = "CONFLICT" in commit_code or commit_code.endswith("_SUPERSEDED")
            return self._result(
                started=started,
                status="CONFLICT" if is_conflict else "UNAVAILABLE",
                source_status="CONFLICT" if is_conflict else "UNAVAILABLE",
                issue_codes=(committed.get("code", "FIFO_BATCH_SCAN_STORAGE_UNAVAILABLE"),),
                case_revision=basis["case_revision"], rule_revision=basis["rule_revision"],
                actual_attempts=actual_attempts, scan_id=scan_id,
                scan_revision=scan_revision,
            )
        status = "CONFLICT" if source_conflict else (
            "COMPLETE" if not resumable else "PARTIAL"
        )
        return self._result(
            started=started, status=status, source_status="PARTIAL",
            issue_codes=issues, case_revision=basis["case_revision"],
            rule_revision=basis["rule_revision"], actual_attempts=actual_attempts,
            continuation_token=committed.get("continuation_token"),
            orders_observed=state["orders_seen"],
            supplies_observed=state["supplies_seen"],
            pagination_complete=state["list_complete"],
            details_complete=details_complete, scan_id=scan_id,
            scan_revision=next_revision,
            candidates_observed=state["candidate_count"],
            sku_composition_complete=composition_complete,
        )

    @staticmethod
    def _empty_durable_state():
        return {
            "cursor": None,
            "seen_cursor_digests": [],
            "pages_scanned": 0,
            "pending_supplies": [],
            "orders_seen": 0,
            "supplies_seen": 0,
            "candidate_count": 0,
            "unknown_supply_count": 0,
            "list_complete": False,
        }

    def _next_checkpoint_timestamp(
        self, scope, case_id, tenant_fingerprint, *, scan_id=None,
    ):
        """Keep checkpoint ordering unambiguous even under a fixed test clock."""
        current = datetime.fromisoformat(self._now_utc_text().replace("Z", "+00:00"))
        connection = None
        try:
            connection = self.scan_checkpoint_service.repository.get_connection()
            scope_fingerprint = FifoCostBatchSupplyStore._scope_fingerprint(scope)
            rows = connection.execute(
                """SELECT MAX(updated_at) AS latest_updated_at
                   FROM fifo_cost_batch_supply_scans
                   WHERE case_id=? AND owner_fingerprint=? AND tenant_fingerprint=?
                     AND store_id=? AND sku=? AND scope_fingerprint=?""",
                (
                    case_id, FifoCostBatchSupplyStore._digest(scope.owner_id),
                    tenant_fingerprint, scope.store_id, scope.sku, scope_fingerprint,
                ),
            ).fetchone()
            prior_values = []
            if rows is not None and rows["latest_updated_at"]:
                prior_values.append(rows["latest_updated_at"])
            if scan_id is not None:
                prior = FifoCostBatchSupplyStore.read_scan_checkpoint(
                    connection, scope=scope, case_id=case_id,
                    tenant_fingerprint=tenant_fingerprint, scan_id=scan_id,
                )
                if prior is not None:
                    prior_values.append(prior["updated_at"])
            for value in prior_values:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if current <= parsed:
                    current = parsed + timedelta(microseconds=1)
        finally:
            if connection is not None:
                connection.close()
        return current.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z",
        )

    def _scan_coverage(
        self, *, scan_id, revision, scope, case_id, rule_revision, captured_at,
        supported_states, state, details_complete, issue_codes, continuation_token,
    ):
        composition_complete = (
            state["list_complete"] and not state["pending_supplies"]
            and state["unknown_supply_count"] == 0
        )
        return SupplyScanCoverage(
            scan_id=scan_id, revision=revision, scope=scope, case_id=case_id,
            rule_revision=rule_revision, requested_from=None, requested_through=None,
            captured_at=captured_at, source_as_of=None,
            supported_state_profile=supported_states,
            list_pagination_complete=state["list_complete"],
            details_complete=details_complete and not state["pending_supplies"],
            sku_composition_complete=composition_complete,
            historical_window_proven=False, membership_complete=False,
            quantity_complete=False, physical_receipt_timing_complete=False,
            observation_set_fingerprint="0" * 64,
            source_contract_version=self.SOURCE_CONTRACT_VERSION,
            orders_seen=state["orders_seen"], supplies_seen=state["supplies_seen"],
            sku_rows_seen=state["candidate_count"], unknown_order_count=0,
            unknown_supply_count=state["unknown_supply_count"],
            unknown_quantity_supply_count=state["candidate_count"],
            issue_codes=tuple(dict.fromkeys(issue_codes))[:32],
            resumable_token=continuation_token,
        )

    def _fail_unstarted_scan(
        self, *, checkpoint, scope, case_id, tenant_fingerprint, basis,
        supported_states, scan_id, expected_scan_revision, state, issues,
        observations,
    ):
        """Publish a terminal failure marker so an old scan cannot stay newest."""
        try:
            failed_at = self._next_checkpoint_timestamp(
                scope, case_id, tenant_fingerprint, scan_id=scan_id,
            )
            revision = expected_scan_revision + 1
            coverage = self._scan_coverage(
                scan_id=scan_id, revision=revision, scope=scope, case_id=case_id,
                rule_revision=basis["rule_revision"], captured_at=failed_at,
                supported_states=supported_states, state=state,
                details_complete=False, issue_codes=issues,
                continuation_token=None,
            )
            return checkpoint.commit_page(
                coverage=coverage, tenant_fingerprint=tenant_fingerprint,
                rule_id=basis["rule_id"], rule_fingerprint=basis["rule_fingerprint"],
                expected_case_revision=basis["case_revision"],
                expected_scan_revision=expected_scan_revision,
                observations=observations, status="FAILED",
                expires_at=self._timestamp_plus(failed_at, checkpoint.TTL_SECONDS),
                updated_at=failed_at, continuation_state=None, now=failed_at,
            )
        except Exception:
            return {"error": True, "code": "FIFO_BATCH_SCAN_STORAGE_UNAVAILABLE"}

    @classmethod
    def _upgrade_durable_state(cls, state):
        empty = cls._empty_durable_state()
        if not isinstance(state, dict):
            raise ValueError("FIFO_BATCH_SCAN_TOKEN_INVALID")
        empty.update(state)
        empty["seen_cursor_digests"] = list(empty["seen_cursor_digests"])
        empty["pending_supplies"] = [dict(item) for item in empty["pending_supplies"]]
        return empty

    def _read_scan_ref_fingerprints(
        self, scope, case_id, tenant_fingerprint, scan_id,
    ):
        connection = None
        try:
            connection = self.scan_checkpoint_service.repository.get_connection()
            refs = FifoCostBatchSupplyStore.read_scan_observation_refs(
                connection, scope=scope, case_id=case_id,
                tenant_fingerprint=tenant_fingerprint, scan_id=scan_id,
            )
            result = {}
            for row in refs:
                prior = result.get(row["record_key"])
                fingerprint = row["source_fingerprint"]
                if prior is not None and prior != fingerprint:
                    return {
                        "error": True,
                        "code": "FIFO_BATCH_SCAN_REFERENCE_CONFLICT",
                    }
                else:
                    result[row["record_key"]] = fingerprint
            return {"error": False, "items": result}
        except Exception:
            return {
                "error": True,
                "code": "FIFO_BATCH_SCAN_STORAGE_UNAVAILABLE",
            }
        finally:
            if connection is not None:
                connection.close()

    @classmethod
    def _extract_supply_references(cls, orders):
        refs = []
        issues = []
        if not isinstance(orders, list):
            return (), (), "FIFO_BATCH_SUPPLY_DETAILS_INVALID"
        for order in orders:
            order_id = cls._identifier(order.get("order_id"))
            if order_id is None:
                return (), tuple(issues), "FIFO_BATCH_SUPPLY_ORDER_ID_INVALID"
            order_state = order.get("state")
            normalized_order_state = (
                order_state.strip().upper() if isinstance(order_state, str) else ""
            )
            if (
                not cls._safe_enum(order_state)
                or normalized_order_state not in
                FifoCostSourceCollectionService.ACTIVE_SUPPLY_STATES
            ):
                issues.append("FIFO_BATCH_SUPPLY_ORDER_STATE_UNSUPPORTED")
            nested = order.get("supplies")
            if not isinstance(nested, list):
                return (), tuple(issues), "FIFO_BATCH_SUPPLY_NESTED_LIST_UNAVAILABLE"
            for supply in nested:
                if not isinstance(supply, dict):
                    return (), tuple(issues), "FIFO_BATCH_SUPPLY_NESTED_RECORD_INVALID"
                supply_id = cls._identifier(supply.get("supply_id"))
                if supply_id is None:
                    return (), tuple(issues), "FIFO_BATCH_SUPPLY_ID_INVALID"
                raw_state = supply.get("state")
                safe_state = raw_state.strip().upper() if cls._safe_enum(raw_state) else None
                if safe_state not in FifoCostSourceNormalizer._ACTIVE_SUPPLY_STATUS_MAP:
                    issues.append("FIFO_BATCH_SUPPLY_STATE_UNSUPPORTED")
                    safe_state = None
                is_crossdock = supply.get("is_crossdock")
                if is_crossdock is not None and type(is_crossdock) is not bool:
                    return (), tuple(issues), "FIFO_BATCH_SUPPLY_CROSSDOCK_FLAG_INVALID"
                raw_bundle_id = supply.get("bundle_id")
                bundle_id = None
                if isinstance(raw_bundle_id, str) and raw_bundle_id:
                    if len(raw_bundle_id) > 256:
                        return (), tuple(issues), "FIFO_BATCH_SUPPLY_BUNDLE_ID_INVALID"
                    bundle_id = raw_bundle_id
                else:
                    issues.append("FIFO_BATCH_BUNDLE_REFERENCE_UNAVAILABLE")
                refs.append({
                    "order_id": order_id,
                    "supply_id": supply_id,
                    "bundle_id": bundle_id,
                    "state": safe_state,
                    "is_crossdock": is_crossdock,
                })
        return tuple(refs), tuple(dict.fromkeys(issues)), None

    @staticmethod
    def _make_bundle_observation(*, scope, ref, planned_quantity, captured_at):
        transition_order_digest = supply_reference_digest(
            owner_id=scope.owner_id, store_id=scope.store_id,
            reference_kind=SupplyReferenceKind.ORDER, reference_id=ref["order_id"],
        )
        transition_supply_digest = supply_reference_digest(
            owner_id=scope.owner_id, store_id=scope.store_id,
            reference_kind=SupplyReferenceKind.SUPPLY, reference_id=ref["supply_id"],
        )
        if transition_order_digest is None or transition_supply_digest is None:
            raise ValueError("FIFO_BATCH_SUPPLY_REFERENCE_INVALID")
        identity = {
            "scope": {
                "owner_id": scope.owner_id, "store_id": scope.store_id,
                "product_id": scope.product_id, "offer_id": scope.offer_id,
                "sku": scope.sku,
            },
            "order_id": ref["order_id"],
        }
        order_digest = hashlib.sha256(json.dumps(
            {"version": 1, "kind": "order", **identity},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")).hexdigest()
        supply_digest = hashlib.sha256(json.dumps(
            {"version": 1, "kind": "supply", **identity,
             "supply_id": ref["supply_id"]},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")).hexdigest()
        record_key = FifoCostBatchSupplyDeduplicator.canonical_record_key(
            scope, supply_digest,
        )
        raw_lookup = json.dumps({
            "order_id": ref["order_id"], "supply_id": ref["supply_id"],
            "bundle_id": ref["bundle_id"],
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        encrypted_lookup = encrypt_tenant_value(raw_lookup)
        if encrypted_lookup is None or len(encrypted_lookup) > 4096:
            raise ValueError("FIFO_BATCH_SCAN_ENCRYPTION_UNAVAILABLE")
        source_fingerprint = hashlib.sha256(json.dumps({
            "version": 1, "order_ref_digest": order_digest,
            "supply_ref_digest": supply_digest,
            "source_status": ref["state"],
            "is_crossdock": ref["is_crossdock"],
            "planned_declared_quantity": planned_quantity,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()
        normalized_state = FifoCostSourceNormalizer._ACTIVE_SUPPLY_STATUS_MAP.get(
            ref["state"], "UNKNOWN",
        )
        explicit_zero = (
            ("planned_declared_quantity",) if planned_quantity == 0 else ()
        )
        return SupplySkuObservation(
            scope=scope, record_key=record_key,
            order_ref_digest=order_digest, supply_ref_digest=supply_digest,
            encrypted_lookup_payload=encrypted_lookup,
            source_profile_version="OZON_SUPPLY_BUNDLE_V1",
            source_fingerprint=source_fingerprint,
            captured_at=captured_at, source_as_of=None,
            source_status=ref["state"],
            normalized_status=NormalizedSupplyStatus(normalized_state),
            is_crossdock=ref["is_crossdock"],
            dispatch_local_date=None, dispatch_local_time=None,
            dispatch_time_status=DispatchTimeStatus.UNKNOWN,
            planned_declared_quantity=planned_quantity,
            shipped_composition_quantity=None, accepted_quantity=None,
            quantity_source_kind=EvidenceSourceKind.OZON_API,
            quantity_coverage=EvidenceCompleteness.PARTIAL,
            acceptance_fingerprint=None, acceptance_version=None,
            explicit_zero_fields=explicit_zero,
            membership=SupplyMembership.NEEDS_CONFIRMATION,
            issues=("FIFO_BATCH_SUPPLY_DISPATCH_DATE_UNAVAILABLE",),
            transition_order_reference_digest=transition_order_digest,
            transition_supply_reference_digest=transition_supply_digest,
        )

    def _now_utc_text(self):
        value = self.utc_clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("FIFO_BATCH_SCAN_TIMESTAMP_INVALID")
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z",
        )

    @staticmethod
    def _timestamp_plus(value, seconds):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (parsed + timedelta(seconds=seconds)).astimezone(timezone.utc).isoformat(
            timespec="microseconds",
        ).replace("+00:00", "Z")

    def _request(self, trace, method_name, actual_attempts_before, *args, **kwargs):
        if method_name not in self.REQUEST_ALLOWLIST:
            return None, 0
        method = getattr(self.ozon_client, method_name, None)
        remaining = trace.remaining_seconds()
        if not callable(method) or trace.is_budget_exhausted() or remaining <= 0:
            return None, 0
        if actual_attempts_before >= self.HTTP_ATTEMPT_BUDGET:
            return None, 0
        observed = 0

        def observe_attempt(_endpoint=None):
            nonlocal observed
            observed += 1

        timeout = min(self.REQUEST_TIMEOUT_SECONDS, remaining)
        try:
            response = method(
                *args, timeout=timeout, max_attempts=1,
                total_timeout=timeout,
                request_attempt_observer=observe_attempt,
                **kwargs,
            )
        except Exception:
            return None, observed
        return response, observed

    def _load_order_details(self, trace, order_ids, actual_attempts_before):
        orders_by_id = {}
        attempts = 0
        for offset in range(0, len(order_ids), self.DETAILS_BATCH_SIZE):
            if self._remaining_attempts(trace) < 1:
                return None, attempts, "FIFO_BATCH_SOURCE_BUDGET_EXHAUSTED"
            batch = order_ids[offset:offset + self.DETAILS_BATCH_SIZE]
            response, used = self._request(
                trace, "get_supply_orders_details", actual_attempts_before + attempts,
                batch,
            )
            attempts += used
            if self._failed(response):
                return None, attempts, "FIFO_BATCH_SUPPLY_DETAILS_UNAVAILABLE"
            records = response.get("orders")
            if not isinstance(records, list) or len(records) != len(batch):
                return None, attempts, "FIFO_BATCH_SUPPLY_DETAILS_COVERAGE_INVALID"
            expected = set(batch)
            for record in records:
                if not isinstance(record, dict):
                    return None, attempts, "FIFO_BATCH_SUPPLY_ORDER_INVALID"
                order_id = self._identifier(record.get("order_id"))
                if order_id not in expected or order_id in orders_by_id:
                    return None, attempts, "FIFO_BATCH_SUPPLY_DETAILS_IDENTITY_MISMATCH"
                orders_by_id[order_id] = record
        if set(orders_by_id) != set(order_ids):
            return None, attempts, "FIFO_BATCH_SUPPLY_DETAILS_COVERAGE_INVALID"
        return [orders_by_id[order_id] for order_id in order_ids], attempts, None

    def _take_checkpoint(self, token, *, scope_fingerprint):
        if token is None:
            return None, None
        if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token):
            return None, "FIFO_BATCH_SUPPLY_CONTINUATION_INVALID"
        with self._checkpoint_lock:
            now = self.monotonic_clock()
            for key, checkpoint in list(self._checkpoints.items()):
                if checkpoint.expires_at <= now:
                    self._checkpoints.pop(key, None)
            checkpoint = self._checkpoints.get(token)
            if checkpoint is None:
                return None, "FIFO_BATCH_SUPPLY_CONTINUATION_STALE"
            if checkpoint.scope_fingerprint != scope_fingerprint:
                return None, "FIFO_BATCH_SUPPLY_CONTINUATION_SCOPE_MISMATCH"
            self._checkpoints.pop(token, None)
        return {
            "cursor": checkpoint.cursor,
            "seen_cursors": list(checkpoint.seen_cursors),
            "seen_order_ids": list(checkpoint.seen_order_ids),
            "seen_supply_ids": list(checkpoint.seen_supply_ids),
            "pages_scanned": checkpoint.pages_scanned,
        }, None

    def _save_checkpoint(self, checkpoint):
        with self._checkpoint_lock:
            now = self.monotonic_clock()
            for key, existing in list(self._checkpoints.items()):
                if existing.expires_at <= now:
                    self._checkpoints.pop(key, None)
            if len(self._checkpoints) >= self.MAX_CHECKPOINTS:
                return None
            token = uuid4().hex
            self._checkpoints[token] = checkpoint
        return token

    @staticmethod
    def _remaining_attempts(trace):
        remaining = trace.ozon_request_budget
        current = trace
        while current is not None:
            remaining = min(
                remaining,
                max(0, current.ozon_request_budget - current.ozon_requests_reserved),
            )
            current = current.parent
        return remaining

    @classmethod
    def _order_ids(cls, value):
        if not isinstance(value, list) or len(value) > cls.PAGE_SIZE:
            return None
        ids = [cls._identifier(item) for item in value]
        return None if any(item is None for item in ids) else ids

    @classmethod
    def _cursor(cls, value):
        if value is None or value == "":
            return None, True
        if not isinstance(value, str):
            return None, False
        cursor = value
        if not cls._CURSOR.fullmatch(cursor):
            return None, False
        return cursor, True

    @classmethod
    def _extract_supply_ids(cls, orders):
        supply_ids = []
        issues = []
        for order in orders:
            state = order.get("state")
            normalized_order_state = (
                state.strip().upper() if isinstance(state, str) else ""
            )
            if (
                not cls._safe_enum(state)
                or normalized_order_state not in
                FifoCostSourceCollectionService.ACTIVE_SUPPLY_STATES
            ):
                issues.append("FIFO_BATCH_SUPPLY_ORDER_STATE_UNSUPPORTED")
            nested = order.get("supplies")
            if not isinstance(nested, list):
                return (), tuple(issues), "FIFO_BATCH_SUPPLY_NESTED_LIST_UNAVAILABLE"
            for supply in nested:
                if not isinstance(supply, dict):
                    return (), tuple(issues), "FIFO_BATCH_SUPPLY_NESTED_RECORD_INVALID"
                supply_id = cls._identifier(supply.get("supply_id"))
                if supply_id is None:
                    return (), tuple(issues), "FIFO_BATCH_SUPPLY_ID_INVALID"
                supply_state = supply.get("state")
                normalized_supply_state = (
                    supply_state.strip().upper()
                    if isinstance(supply_state, str) else ""
                )
                if (
                    not cls._safe_enum(supply_state)
                    or normalized_supply_state not in
                    FifoCostSourceNormalizer._ACTIVE_SUPPLY_STATUS_MAP
                ):
                    issues.append("FIFO_BATCH_SUPPLY_STATE_UNSUPPORTED")
                is_crossdock = supply.get("is_crossdock")
                if is_crossdock is not None and type(is_crossdock) is not bool:
                    return (), tuple(issues), "FIFO_BATCH_SUPPLY_CROSSDOCK_FLAG_INVALID"
                supply_ids.append(supply_id)
        return tuple(supply_ids), tuple(dict.fromkeys(issues)), None

    @classmethod
    def _identifier(cls, value):
        if isinstance(value, bool) or value is None:
            return None
        raw = str(value).strip()
        if not cls._ID.fullmatch(raw):
            return None
        parsed = int(raw)
        return str(parsed) if 0 < parsed <= 9_223_372_036_854_775_807 else None

    @staticmethod
    def _safe_enum(value):
        return isinstance(value, str) and bool(re.fullmatch(r"[A-Z0-9_]{1,48}", value.strip()))

    @staticmethod
    def _failed(response):
        return not isinstance(response, dict) or response.get("error") is True

    @staticmethod
    def _is_rejected_supply_list_request(response):
        return (
            isinstance(response, dict)
            and response.get("error") is True
            and response.get("code") == "OZON_HTTP_ERROR"
            and type(response.get("status_code")) is int
            and response["status_code"] == 400
        )

    @staticmethod
    def _fingerprint(value):
        payload = json.dumps(
            value, ensure_ascii=True, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _result(
        self, *, started, status, source_status, issue_codes, case_revision,
        rule_revision, actual_attempts=0, continuation_token=None,
        orders_observed=0, supplies_observed=0, pagination_complete=False,
        details_complete=False, scan_id=None, scan_revision=None,
        candidates_observed=0, sku_composition_complete=False,
    ) -> FifoCostBatchSupplyCollectionResult:
        return FifoCostBatchSupplyCollectionResult(
            status=status,
            source_status=source_status,
            read_only=True,
            actual_http_attempts=max(0, int(actual_attempts)),
            http_attempt_cap=self.HTTP_ATTEMPT_BUDGET,
            elapsed_seconds=round(max(0.0, self.monotonic_clock() - started), 3),
            case_revision=case_revision,
            rule_revision=rule_revision,
            issue_codes=tuple(dict.fromkeys(issue_codes)),
            continuation_token=continuation_token,
            orders_observed=orders_observed,
            supplies_observed=supplies_observed,
            pagination_complete=pagination_complete,
            details_complete=details_complete,
            scan_id=scan_id,
            scan_revision=scan_revision,
            candidates_observed=candidates_observed,
            sku_composition_complete=sku_composition_complete,
        )
