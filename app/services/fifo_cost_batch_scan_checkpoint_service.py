"""Durable, tenant-scoped FIFO supply scan checkpoints.

Page observations and their scan membership are committed with the checkpoint
revision in one repository transaction. Continuation state is encrypted with
the existing tenant Fernet key; public continuation references contain only a
random scan identifier and revision.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import sqlite3

from services.fifo_cost_batch_rule_contracts import SupplyScanCoverage, SupplySkuObservation
from services.fifo_cost_batch_supply_store import FifoCostBatchSupplyStore
from services.tenant_cipher_provider import decrypt_tenant_value, encrypt_tenant_value


_SCAN_REF = re.compile(r"^([A-Za-z0-9_-]{8,96})_r([1-9][0-9]{0,5})$")
_CURSOR = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")
_HEX = re.compile(r"^[0-9a-f]{64}$")
_STATUSES = frozenset({"STAGING", "PARTIAL", "PUBLISHED", "FAILED", "EXPIRED"})
_RESUMABLE = frozenset({"STAGING", "PARTIAL"})
_MAX_TOKEN_BYTES = 8192


class FifoCostBatchScanCheckpointService:
    """Persist resumable source pages without publishing partial manifests."""

    TTL_SECONDS = 30 * 60
    MAX_SEEN_CURSORS = 100

    def __init__(self, repository, *, now_provider=None):
        self.repository = repository
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def commit_page(
        self, *, coverage: SupplyScanCoverage, tenant_fingerprint: str,
        rule_id: str, rule_fingerprint: str, expected_case_revision: int,
        expected_scan_revision: int, observations: tuple[SupplySkuObservation, ...],
        status: str, expires_at: str, updated_at: str,
        continuation_state: dict | None = None, now: str | None = None,
    ) -> dict:
        """Atomically append a page, link it to its scan, and CAS the checkpoint."""
        if not isinstance(coverage, SupplyScanCoverage):
            return self._error("FIFO_BATCH_SCAN_INVALID")
        if status not in _STATUSES:
            return self._error("FIFO_BATCH_SCAN_STATUS_INVALID")
        if type(expected_case_revision) is not int or expected_case_revision < 1:
            return self._error("FIFO_BATCH_CASE_REVISION_INVALID")
        if type(expected_scan_revision) is not int or expected_scan_revision < 0:
            return self._error("FIFO_BATCH_SCAN_REVISION_INVALID")
        if coverage.revision != expected_scan_revision + 1:
            return self._error("FIFO_BATCH_SCAN_REVISION_CONFLICT")
        if not isinstance(rule_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,96}", rule_id):
            return self._error("FIFO_BATCH_RULE_NOT_FOUND")
        if not self._is_digest(rule_fingerprint):
            return self._error("FIFO_BATCH_RULE_NOT_FOUND")
        if not isinstance(observations, tuple) or len(observations) > 10_000:
            return self._error("FIFO_BATCH_SCAN_OBSERVATION_LIMIT_REACHED")
        if any(not isinstance(item, SupplySkuObservation) or item.scope != coverage.scope
               for item in observations):
            return self._error("FIFO_BATCH_SCOPE_MISMATCH")
        if len({item.record_key for item in observations}) != len(observations):
            return self._error("FIFO_BATCH_SCAN_DUPLICATE_PAGE_ROW")
        if status in _RESUMABLE:
            state, state_error = self._normalize_continuation_state(continuation_state)
            if state_error:
                return self._error(state_error)
        elif continuation_state is not None:
            return self._error("FIFO_BATCH_SCAN_TOKEN_INVALID")
        else:
            state = None
        now_text = self._timestamp(now) if now is not None else self._timestamp(self.now_provider())
        expires_text = self._timestamp(expires_at)
        updated_text = self._timestamp(updated_at)
        if expires_text is None or updated_text is None or now_text is None:
            return self._error("FIFO_BATCH_SCAN_TIMESTAMP_INVALID")
        now_dt = self._parse_timestamp(now_text)
        expires_dt = self._parse_timestamp(expires_text)
        if status in _RESUMABLE and not (now_dt < expires_dt <= now_dt + timedelta(seconds=self.TTL_SECONDS)):
            return self._error("FIFO_BATCH_SCAN_TTL_INVALID")
        if status not in _RESUMABLE and expires_dt <= now_dt:
            return self._error("FIFO_BATCH_SCAN_TIMESTAMP_INVALID")

        def operation(connection):
            scope = coverage.scope
            owner_fingerprint = FifoCostBatchSupplyStore._digest(scope.owner_id)
            case = FifoCostBatchSupplyStore._case_row(
                connection, scope, coverage.case_id, owner_fingerprint, tenant_fingerprint,
            )
            if case is None:
                return self._error("FIFO_BATCH_SCOPE_MISMATCH")
            case_revision = connection.execute(
                """SELECT current_revision FROM fifo_cost_transition_cases
                   WHERE case_id=? AND owner_fingerprint=? AND tenant_fingerprint=?
                     AND store_id=? AND sku=? AND product_id IS ? AND offer_id IS ?""",
                (
                    coverage.case_id, owner_fingerprint, tenant_fingerprint,
                    scope.store_id, scope.sku, scope.product_id, scope.offer_id,
                ),
            ).fetchone()
            if case_revision is None:
                return self._error("FIFO_BATCH_SCOPE_MISMATCH")
            if case_revision["current_revision"] != expected_case_revision:
                return self._error("FIFO_BATCH_CASE_REVISION_CONFLICT")
            rules = connection.execute(
                """SELECT rule_fingerprint FROM fifo_cost_batch_rule_revisions
                   WHERE case_id=? AND rule_id=? AND rule_revision=?""",
                (coverage.case_id, rule_id, coverage.rule_revision),
            ).fetchall()
            if len(rules) != 1 or rules[0]["rule_fingerprint"] != rule_fingerprint:
                return self._error("FIFO_BATCH_RULE_REVISION_CONFLICT")

            previous_checkpoint = FifoCostBatchSupplyStore.read_scan_checkpoint(
                connection, scope=scope, case_id=coverage.case_id,
                tenant_fingerprint=tenant_fingerprint, scan_id=coverage.scan_id,
            )
            if expected_scan_revision == 0:
                if previous_checkpoint is not None:
                    return self._error("FIFO_BATCH_SCAN_REVISION_CONFLICT")
            else:
                if previous_checkpoint is None:
                    return self._error("FIFO_BATCH_SCAN_REVISION_CONFLICT")
                if previous_checkpoint["revision"] != expected_scan_revision:
                    return self._error("FIFO_BATCH_SCAN_REVISION_CONFLICT")
                if previous_checkpoint["status"] not in _RESUMABLE:
                    return self._error("FIFO_BATCH_SCAN_NOT_RESUMABLE")
                if self._parse_timestamp(previous_checkpoint["expires_at"]) <= now_dt:
                    return self._error("FIFO_BATCH_SCAN_EXPIRED")
                previous_payload = self._decode_payload(
                    previous_checkpoint["encrypted_resumable_token"],
                )
                if previous_payload is None:
                    return self._error("FIFO_BATCH_SCAN_TOKEN_INVALID")
                if not self._payload_matches(
                    previous_payload, scope=scope, case_id=coverage.case_id,
                    case_revision=expected_case_revision, rule_id=rule_id,
                    rule_revision=coverage.rule_revision,
                    rule_fingerprint=rule_fingerprint,
                    source_contract_version=coverage.source_contract_version,
                    supported_state_profile=coverage.supported_state_profile,
                    requested_from=coverage.requested_from,
                    requested_through=coverage.requested_through,
                    scan_id=coverage.scan_id, revision=expected_scan_revision,
                ):
                    return self._error("FIFO_BATCH_SCAN_BINDING_CONFLICT")

            previous_refs = FifoCostBatchSupplyStore.read_scan_observation_refs(
                connection, scope=scope, case_id=coverage.case_id,
                tenant_fingerprint=tenant_fingerprint, scan_id=coverage.scan_id,
            )
            latest = {}
            for row in previous_refs:
                current = latest.get(row["record_key"])
                candidate = (row["observation_revision"], row["source_fingerprint"])
                if current is None or candidate[0] > current[0]:
                    latest[row["record_key"]] = candidate
            predicted_revisions = []
            for observation in observations:
                revision = FifoCostBatchSupplyStore.read_observation_revision(
                    connection, scope=scope, case_id=coverage.case_id,
                    tenant_fingerprint=tenant_fingerprint,
                    record_key=observation.record_key,
                    source_fingerprint=observation.source_fingerprint,
                )
                if revision is None:
                    revision = FifoCostBatchSupplyStore.next_observation_revision(
                        connection, scope=scope, case_id=coverage.case_id,
                        tenant_fingerprint=tenant_fingerprint,
                        record_key=observation.record_key,
                    )
                if revision is None:
                    return self._error("FIFO_BATCH_SCOPE_MISMATCH")
                predicted_revisions.append(revision)
                current = latest.get(observation.record_key)
                if current is None or revision >= current[0]:
                    latest[observation.record_key] = (
                        revision, observation.source_fingerprint,
                    )

            set_fingerprint = self._fingerprint([
                (record_key, latest[record_key][1]) for record_key in sorted(latest)
            ])
            continuation_ref = (
                f"{coverage.scan_id}_r{coverage.revision}" if status in _RESUMABLE else None
            )
            saved_coverage = replace(
                coverage, observation_set_fingerprint=set_fingerprint,
                resumable_token=continuation_ref,
            )
            encrypted_token = None
            if state is not None:
                state_payload = self._continuation_payload(
                    coverage=saved_coverage, case_revision=expected_case_revision,
                    rule_id=rule_id, rule_fingerprint=rule_fingerprint, state=state,
                )
                encrypted = encrypt_tenant_value(self._canonical_json(state_payload))
                if encrypted is None:
                    return self._error("FIFO_BATCH_SCAN_ENCRYPTION_UNAVAILABLE")
                encrypted_token = encrypted.encode("ascii")
                if len(encrypted_token) > _MAX_TOKEN_BYTES:
                    return self._error("FIFO_BATCH_SCAN_TOKEN_LIMIT_REACHED")

            checkpoint = FifoCostBatchSupplyStore.write_scan_checkpoint(
                connection, saved_coverage, tenant_fingerprint=tenant_fingerprint,
                expected_revision=expected_scan_revision, status=status,
                expires_at=expires_text, updated_at=updated_text,
                encrypted_resumable_token=encrypted_token,
            )
            if checkpoint.get("error"):
                return checkpoint
            for observation, expected_revision_for_row in zip(observations, predicted_revisions):
                observation_id = "batchobs-" + self._fingerprint((
                    coverage.case_id, observation.record_key, observation.source_fingerprint,
                ))[:56]
                appended = FifoCostBatchSupplyStore.append_observation(
                    connection, observation, tenant_fingerprint=tenant_fingerprint,
                    observation_id=observation_id, recorded_at=updated_text,
                )
                if appended.get("error"):
                    return appended
                if appended.get("observation_revision") != expected_revision_for_row:
                    return self._error("FIFO_BATCH_OBSERVATION_REVISION_CONFLICT")
                linked = FifoCostBatchSupplyStore.append_scan_observation(
                    connection, scope=scope, case_id=coverage.case_id,
                    tenant_fingerprint=tenant_fingerprint, scan_id=coverage.scan_id,
                    record_key=observation.record_key,
                    source_fingerprint=observation.source_fingerprint,
                    linked_at=updated_text,
                    allow_finalizing=(status == "PUBLISHED"),
                )
                if linked.get("error"):
                    return linked
            return {
                "error": False, "code": "FIFO_BATCH_SCAN_PAGE_COMMITTED",
                "scan_id": coverage.scan_id, "scan_revision": coverage.revision,
                "case_revision": expected_case_revision,
                "observation_set_fingerprint": set_fingerprint,
                "continuation_token": continuation_ref,
                "status": status,
            }

        try:
            return self.repository._run_transition_write(operation)
        except (sqlite3.Error, OSError, TypeError, ValueError):
            return self._error("FIFO_BATCH_SCAN_STORAGE_UNAVAILABLE")

    def load_continuation(
        self, *, scope, case_id: str, tenant_fingerprint: str,
        rule_id: str, rule_revision: int, rule_fingerprint: str,
        expected_case_revision: int, source_contract_version: str,
        supported_state_profile: tuple[str, ...], requested_from: str | None,
        requested_through: str | None, continuation_token: str, now: str | None = None,
    ) -> dict:
        """Load the latest encrypted cursor after a restart, rejecting stale bindings."""
        match = _SCAN_REF.fullmatch(continuation_token or "")
        if match is None:
            return self._error("FIFO_BATCH_SCAN_TOKEN_INVALID")
        scan_id, token_revision = match.group(1), int(match.group(2))
        now_text = self._timestamp(now) if now is not None else self._timestamp(self.now_provider())
        if now_text is None:
            return self._error("FIFO_BATCH_SCAN_TIMESTAMP_INVALID")
        connection = None
        try:
            connection = self.repository.get_connection()
            row = FifoCostBatchSupplyStore.read_scan_checkpoint(
                connection, scope=scope, case_id=case_id,
                tenant_fingerprint=tenant_fingerprint, scan_id=scan_id,
            )
            if row is None:
                return self._error("FIFO_BATCH_SCAN_NOT_FOUND")
            if row["status"] not in _RESUMABLE or row["encrypted_resumable_token"] is None:
                return self._error("FIFO_BATCH_SCAN_NOT_RESUMABLE")
            if token_revision > row["revision"]:
                return self._error("FIFO_BATCH_SCAN_REVISION_CONFLICT")
            if self._parse_timestamp(row["expires_at"]) <= self._parse_timestamp(now_text):
                return self._error("FIFO_BATCH_SCAN_EXPIRED")
            if (
                row["rule_id"] != rule_id or row["rule_revision"] != rule_revision
                or row["rule_fingerprint"] != rule_fingerprint
                or row["requested_from"] != requested_from
                or row["requested_through"] != requested_through
            ):
                return self._error("FIFO_BATCH_SCAN_BINDING_CONFLICT")
            payload = self._decode_payload(row["encrypted_resumable_token"])
            if payload is not None and payload.get("case_revision") != expected_case_revision:
                return self._error("FIFO_BATCH_CASE_REVISION_CONFLICT")
            if payload is None or not self._payload_matches(
                payload, scope=scope, case_id=case_id,
                case_revision=expected_case_revision, rule_id=rule_id,
                rule_revision=rule_revision, rule_fingerprint=rule_fingerprint,
                source_contract_version=source_contract_version,
                supported_state_profile=supported_state_profile,
                requested_from=requested_from, requested_through=requested_through,
                scan_id=scan_id, revision=row["revision"],
            ):
                return self._error("FIFO_BATCH_SCAN_BINDING_CONFLICT")
            state, state_error = self._normalize_continuation_state(payload.get("state"))
            if state_error:
                return self._error("FIFO_BATCH_SCAN_TOKEN_INVALID")
            current_case = connection.execute(
                """SELECT current_revision FROM fifo_cost_transition_cases
                   WHERE case_id=? AND owner_fingerprint=? AND tenant_fingerprint=?
                     AND store_id=? AND sku=? AND product_id IS ? AND offer_id IS ?""",
                (
                    case_id, FifoCostBatchSupplyStore._digest(scope.owner_id),
                    tenant_fingerprint, scope.store_id, scope.sku,
                    scope.product_id, scope.offer_id,
                ),
            ).fetchone()
            if current_case is None or current_case["current_revision"] != expected_case_revision:
                return self._error("FIFO_BATCH_CASE_REVISION_CONFLICT")
            return {
                "error": False, "code": "FIFO_BATCH_SCAN_RESUMED",
                "scan_id": scan_id, "scan_revision": row["revision"],
                "continuation_state": state,
                "resumed_from_stale_token": token_revision < row["revision"],
                "expires_at": row["expires_at"],
            }
        except (OSError, sqlite3.Error, UnicodeError, TypeError, ValueError, json.JSONDecodeError):
            return self._error("FIFO_BATCH_SCAN_STORAGE_UNAVAILABLE")
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _continuation_payload(*, coverage, case_revision, rule_id, rule_fingerprint, state):
        return {
            "version": 1,
            "scan_id": coverage.scan_id,
            "revision": coverage.revision,
            "case_id": coverage.case_id,
            "case_revision": case_revision,
            "scope_fingerprint": FifoCostBatchSupplyStore._scope_fingerprint(coverage.scope),
            "rule_id": rule_id,
            "rule_revision": coverage.rule_revision,
            "rule_fingerprint": rule_fingerprint,
            "source_profile_fingerprint": FifoCostBatchScanCheckpointService._profile_fingerprint(
                coverage.source_contract_version, coverage.supported_state_profile,
            ),
            "requested_from": coverage.requested_from,
            "requested_through": coverage.requested_through,
            "state": state,
        }

    @classmethod
    def _decode_payload(cls, encrypted_token):
        if encrypted_token is None:
            return None
        try:
            decoded = decrypt_tenant_value(bytes(encrypted_token).decode("ascii"))
            if decoded is None or len(decoded.encode("utf-8")) > _MAX_TOKEN_BYTES:
                return None
            payload = json.loads(decoded)
            if not isinstance(payload, dict):
                return None
            return payload
        except (UnicodeError, TypeError, ValueError, json.JSONDecodeError):
            return None

    @classmethod
    def _payload_matches(
        cls, payload, *, scope, case_id, case_revision, rule_id, rule_revision,
        rule_fingerprint, source_contract_version, supported_state_profile,
        requested_from, requested_through, scan_id, revision,
    ):
        expected = {
            "version": 1,
            "scan_id": scan_id,
            "revision": revision,
            "case_id": case_id,
            "case_revision": case_revision,
            "scope_fingerprint": FifoCostBatchSupplyStore._scope_fingerprint(scope),
            "rule_id": rule_id,
            "rule_revision": rule_revision,
            "rule_fingerprint": rule_fingerprint,
            "source_profile_fingerprint": cls._profile_fingerprint(
                source_contract_version, supported_state_profile,
            ),
            "requested_from": requested_from,
            "requested_through": requested_through,
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            return False
        _state, error = cls._normalize_continuation_state(payload.get("state"))
        return error is None

    @classmethod
    def _normalize_continuation_state(cls, state):
        if not isinstance(state, dict) or set(state) != {
            "cursor", "seen_cursor_digests", "pages_scanned",
        }:
            return None, "FIFO_BATCH_SCAN_TOKEN_INVALID"
        cursor = state["cursor"]
        if cursor is not None and (
            not isinstance(cursor, str) or _CURSOR.fullmatch(cursor) is None
        ):
            return None, "FIFO_BATCH_SCAN_TOKEN_INVALID"
        digests = state["seen_cursor_digests"]
        if not isinstance(digests, (list, tuple)) or len(digests) > cls.MAX_SEEN_CURSORS:
            return None, "FIFO_BATCH_SCAN_TOKEN_INVALID"
        if any(not isinstance(value, str) or _HEX.fullmatch(value) is None for value in digests):
            return None, "FIFO_BATCH_SCAN_TOKEN_INVALID"
        normalized_digests = tuple(digests)
        if len(set(normalized_digests)) != len(normalized_digests):
            return None, "FIFO_BATCH_SCAN_TOKEN_INVALID"
        pages = state["pages_scanned"]
        if type(pages) is not int or not 0 <= pages <= 100:
            return None, "FIFO_BATCH_SCAN_TOKEN_INVALID"
        return {
            "cursor": cursor,
            "seen_cursor_digests": normalized_digests,
            "pages_scanned": pages,
        }, None

    @staticmethod
    def _profile_fingerprint(contract_version, state_profile):
        return FifoCostBatchScanCheckpointService._fingerprint({
            "contract_version": contract_version,
            "supported_state_profile": tuple(sorted(state_profile)),
        })

    @staticmethod
    def _fingerprint(value):
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _canonical_json(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def _timestamp(value):
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

    @classmethod
    def _parse_timestamp(cls, value):
        normalized = cls._timestamp(value)
        if normalized is None:
            raise ValueError("FIFO_BATCH_SCAN_TIMESTAMP_INVALID")
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))

    @staticmethod
    def _is_digest(value):
        return isinstance(value, str) and _HEX.fullmatch(value) is not None

    @staticmethod
    def _error(code):
        return {"error": True, "code": code}
