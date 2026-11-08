"""SQL-only helpers for transition cases inside FifoCostRepository transactions.

This module never opens a database connection, commits, calls Ozon, or owns
tenant storage. The caller supplies the current repository connection and its
already-validated tenant scope.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from decimal import Decimal
from enum import Enum
import hashlib
import json
import sqlite3
from typing import Mapping

from services.fifo_cost_transition_contracts import (
    ReportEvidence,
    SupplyDeclaration,
    SupplyObservation,
    TransitionCase,
)


class FifoCostTransitionStore:
    MAX_OPEN_CASES_PER_STORE = 20
    MAX_DECLARATIONS_PER_CASE = 100
    MAX_OBSERVATIONS_PER_CASE = 2000
    MAX_CASE_PAYLOAD_BYTES = 262_144
    MAX_EVIDENCE_PAYLOAD_BYTES = 262_144

    @classmethod
    def case_payload(cls, case: TransitionCase) -> dict:
        metadata = cls._metadata_payload(case.metadata)
        payload = {
            "metadata": metadata,
            **{
                item.name: cls._json_value(getattr(case, item.name))
                for item in fields(case)
                if item.name not in {"metadata", "unknown_values"}
            },
            "unknown_values": cls._unknown_payload(case.unknown_values),
        }
        return payload

    @classmethod
    def save_case(
        cls, connection, case: TransitionCase, scope: dict, *,
        expected_revision: int, idempotency_key: str, recorded_at: str,
    ) -> dict:
        cls._require_transaction(connection)
        payload = cls.case_payload(case)
        payload_json = cls._json(payload, cls.MAX_CASE_PAYLOAD_BYTES)
        fingerprint = cls._digest(payload_json)
        revision_json = cls._json(
            {**payload, "_command_fingerprint": fingerprint},
            cls.MAX_CASE_PAYLOAD_BYTES,
        )
        case_id = case.case_id
        row = connection.execute(
            """SELECT store_id, product_id, offer_id, sku, current_revision,
                      current_state, created_at, updated_at
               FROM fifo_cost_transition_cases
               WHERE case_id=? AND owner_fingerprint=? AND tenant_fingerprint=?
                 AND store_id=? AND sku=?""",
            (case_id, scope["owner_fingerprint"], scope["tenant_fingerprint"],
             case.metadata.scope.store_id, case.metadata.scope.sku),
        ).fetchone()
        if row is not None and (
            row["product_id"] != case.metadata.scope.product_id
            or row["offer_id"] != case.metadata.scope.offer_id
        ):
            return {"error": True, "code": "FIFO_TRANSITION_CASE_IDENTITY_CONFLICT"}
        if row is not None:
            prior = cls._idempotent_revision(
                connection, case_id, idempotency_key, fingerprint,
            )
            if prior is not None:
                return prior

        if expected_revision == 0:
            if case.case_revision != 1 or row is not None:
                return {"error": True, "code": "FIFO_TRANSITION_REVISION_CONFLICT"}
            if case.state.value == "CANCELLED":
                return {"error": True, "code": "FIFO_TRANSITION_CASE_NOT_READY"}
            active_sku_case = connection.execute(
                """SELECT case_id FROM fifo_cost_transition_cases
                   WHERE owner_fingerprint=? AND tenant_fingerprint=?
                     AND store_id=? AND sku=?
                     AND current_state IN ('DRAFT', 'AWAITING_EVIDENCE', 'READY_TO_CONFIRM')
                   LIMIT 1""",
                (scope["owner_fingerprint"], scope["tenant_fingerprint"],
                 case.metadata.scope.store_id, case.metadata.scope.sku),
            ).fetchone()
            if active_sku_case is not None:
                return {"error": True, "code": "FIFO_TRANSITION_ACTIVE_CASE_CONFLICT"}
            active_count = connection.execute(
                """SELECT COUNT(*) FROM fifo_cost_transition_cases
                   WHERE owner_fingerprint=? AND tenant_fingerprint=? AND store_id=?
                     AND current_state IN ('DRAFT', 'AWAITING_EVIDENCE', 'READY_TO_CONFIRM')""",
                (scope["owner_fingerprint"], scope["tenant_fingerprint"],
                 case.metadata.scope.store_id),
            ).fetchone()[0]
            if active_count >= cls.MAX_OPEN_CASES_PER_STORE:
                return {"error": True, "code": "FIFO_TRANSITION_CASE_LIMIT_REACHED"}
            connection.execute(
                """INSERT INTO fifo_cost_transition_cases (
                    case_id, schema_version, owner_fingerprint, tenant_fingerprint,
                    store_id, product_id, offer_id, sku, current_revision,
                    current_state, created_at, updated_at
                ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
                (case_id, scope["owner_fingerprint"], scope["tenant_fingerprint"],
                 case.metadata.scope.store_id, case.metadata.scope.product_id,
                 case.metadata.scope.offer_id, case.metadata.scope.sku,
                 case.state.value, case.created_at, case.updated_at),
            )
        else:
            if row is None:
                return {"error": True, "code": "FIFO_TRANSITION_CASE_NOT_FOUND"}
            if row["current_revision"] != expected_revision:
                return {"error": True, "code": "FIFO_TRANSITION_REVISION_CONFLICT"}
            if row["current_state"] in {"APPLIED", "CANCELLED"}:
                return {"error": True, "code": "FIFO_TRANSITION_CASE_NOT_READY"}
            if case.case_revision != expected_revision + 1:
                return {"error": True, "code": "FIFO_TRANSITION_REVISION_CONFLICT"}
            if (
                row["store_id"] != case.metadata.scope.store_id
                or row["product_id"] != case.metadata.scope.product_id
                or row["offer_id"] != case.metadata.scope.offer_id
                or row["sku"] != case.metadata.scope.sku
                or row["created_at"] != case.created_at
                or case.updated_at < row["updated_at"]
                or (row["current_state"] == "AWAITING_EVIDENCE" and case.state.value == "DRAFT")
            ):
                return {"error": True, "code": "FIFO_TRANSITION_CASE_IDENTITY_CONFLICT"}

        cls._insert_case_revision(
            connection, case_id=case_id, case_revision=case.case_revision,
            state=case.state.value, payload_json=revision_json,
            fingerprint=cls._digest(revision_json), idempotency_key=idempotency_key,
            created_at=recorded_at, updated_at=recorded_at,
        )
        if expected_revision > 0:
            result = connection.execute(
                """UPDATE fifo_cost_transition_cases
                   SET current_revision=?, current_state=?, updated_at=?
                   WHERE case_id=? AND owner_fingerprint=? AND tenant_fingerprint=?
                     AND store_id=? AND sku=? AND current_revision=?""",
                (case.case_revision, case.state.value, case.updated_at, case_id,
                 scope["owner_fingerprint"], scope["tenant_fingerprint"],
                 case.metadata.scope.store_id, case.metadata.scope.sku,
                 expected_revision),
            )
            if result.rowcount != 1:
                return {"error": True, "code": "FIFO_TRANSITION_REVISION_CONFLICT"}
        return {
            "error": False,
            "code": "FIFO_TRANSITION_CASE_SAVED",
            "case_id": case_id,
            "case_revision": case.case_revision,
            "state": case.state.value,
            "replayed": False,
        }

    @classmethod
    def append_declaration(
        cls, connection, declaration: SupplyDeclaration, scope: dict, *,
        expected_case_revision: int, idempotency_key: str, recorded_at: str,
    ) -> dict:
        payload = cls._evidence_payload(declaration)
        payload_json = cls._json(payload, cls.MAX_EVIDENCE_PAYLOAD_BYTES)
        fingerprint = cls._digest(payload_json)

        def insert(case_row):
            existing = connection.execute(
                """SELECT MAX(declaration_revision) FROM fifo_cost_supply_declarations
                   WHERE case_id=? AND declaration_id=?""",
                (declaration.case_id, declaration.declaration_id),
            ).fetchone()[0]
            if existing is not None and declaration.revision != existing + 1:
                return {"error": True, "code": "FIFO_TRANSITION_DECLARATION_REVISION_CONFLICT"}
            if existing is None and declaration.revision != 1:
                return {"error": True, "code": "FIFO_TRANSITION_DECLARATION_REVISION_CONFLICT"}
            duplicate_rows = connection.execute(
                """SELECT c.case_id, c.sku, c.current_state, d.declaration_id
                   FROM fifo_cost_supply_declarations AS d
                   JOIN fifo_cost_transition_cases AS c ON c.case_id=d.case_id
                   WHERE c.owner_fingerprint=? AND c.tenant_fingerprint=?
                     AND c.store_id=? AND d.reference_kind=? AND d.reference_digest=?
                     AND c.current_state<>'CANCELLED'""",
                (scope["owner_fingerprint"], scope["tenant_fingerprint"],
                 declaration.metadata.scope.store_id,
                 declaration.reference_kind.value, declaration.reference_digest),
            ).fetchall()
            for duplicate in duplicate_rows:
                if (
                    duplicate["case_id"] == declaration.case_id
                    and duplicate["declaration_id"] == declaration.declaration_id
                ):
                    continue
                if duplicate["sku"] != declaration.metadata.scope.sku:
                    return {"error": True, "code": "FIFO_TRANSITION_SUPPLY_SKU_CONFLICT"}
                return {"error": True, "code": "FIFO_TRANSITION_SUPPLY_REFERENCE_DUPLICATE"}

            current_case = connection.execute(
                """SELECT payload_json FROM fifo_cost_transition_case_revisions
                   WHERE case_id=? AND case_revision=?""",
                (declaration.case_id, case_row["current_revision"]),
            ).fetchone()
            if current_case is None:
                return {"error": True, "code": "FIFO_TRANSITION_CASE_CORRUPT"}
            try:
                owner_total = json.loads(current_case["payload_json"]).get(
                    "declared_shipped_units",
                )
            except (TypeError, ValueError):
                return {"error": True, "code": "FIFO_TRANSITION_CASE_CORRUPT"}
            if owner_total is not None and declaration.declared_shipped_units is not None:
                latest_rows = connection.execute(
                    """SELECT d.declaration_id, d.declared_shipped_units
                       FROM fifo_cost_supply_declarations AS d
                       JOIN (
                           SELECT declaration_id, MAX(declaration_revision) AS revision
                           FROM fifo_cost_supply_declarations WHERE case_id=?
                           GROUP BY declaration_id
                       ) AS latest
                         ON latest.declaration_id=d.declaration_id
                        AND latest.revision=d.declaration_revision
                       WHERE d.case_id=?""",
                    (declaration.case_id, declaration.case_id),
                ).fetchall()
                other_known_units = sum(
                    row["declared_shipped_units"] or 0
                    for row in latest_rows
                    if row["declaration_id"] != declaration.declaration_id
                )
                if other_known_units + declaration.declared_shipped_units > owner_total:
                    return {"error": True, "code": "FIFO_TRANSITION_SUPPLY_TOTAL_CONFLICT"}
            if existing is None:
                count = connection.execute(
                    "SELECT COUNT(DISTINCT declaration_id) FROM fifo_cost_supply_declarations "
                    "WHERE case_id=?", (declaration.case_id,),
                ).fetchone()[0]
                if count >= cls.MAX_DECLARATIONS_PER_CASE:
                    return {"error": True, "code": "FIFO_TRANSITION_DECLARATION_LIMIT_REACHED"}
            row_id = "declrow_" + cls._digest(
                f"{declaration.case_id}:{declaration.declaration_id}:{declaration.revision}:{fingerprint}"
            )[:40]
            connection.execute(
                """INSERT INTO fifo_cost_supply_declarations (
                    declaration_row_id, case_id, declaration_id, declaration_revision,
                    reference_kind, reference_digest, encrypted_lookup_reference,
                    declared_shipped_units, dispatch_date, provenance, payload_json,
                    payload_fingerprint, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OWNER_INPUT', ?, ?, ?)""",
                (row_id, declaration.case_id, declaration.declaration_id,
                 declaration.revision, declaration.reference_kind.value,
                 declaration.reference_digest, declaration.encrypted_lookup_reference,
                 declaration.declared_shipped_units, declaration.dispatch_date,
                 payload_json, fingerprint, recorded_at),
            )
            return {"evidence_id": row_id}

        return cls._append_evidence_revision(
            connection, case_id=declaration.case_id, metadata=declaration.metadata,
            scope=scope, expected_case_revision=expected_case_revision,
            idempotency_key=idempotency_key, payload_json=payload_json,
            payload_fingerprint=fingerprint, evidence_kind="SUPPLY_DECLARATION",
            insert=insert, recorded_at=recorded_at,
        )

    @classmethod
    def append_observation(
        cls, connection, case_id: str, observation: SupplyObservation, scope: dict, *,
        expected_case_revision: int, idempotency_key: str, recorded_at: str,
    ) -> dict:
        payload = cls._evidence_payload(observation)
        payload_json = cls._json(payload, cls.MAX_EVIDENCE_PAYLOAD_BYTES)
        fingerprint = cls._digest(payload_json)

        def insert(case_row):
            declaration = connection.execute(
                """SELECT MAX(declaration_revision) FROM fifo_cost_supply_declarations
                   WHERE case_id=? AND declaration_id=?""",
                (case_id, observation.declaration_id),
            ).fetchone()
            if declaration is None or declaration[0] is None:
                return {"error": True, "code": "FIFO_TRANSITION_DECLARATION_NOT_FOUND"}
            declaration_revision = declaration[0]
            observation_id = "obs_" + cls._digest(
                f"{case_id}:{observation.declaration_id}:{fingerprint}"
            )[:40]
            connection.execute(
                """INSERT INTO fifo_cost_supply_observations (
                    observation_id, case_id, declaration_id, declaration_revision,
                    captured_at, source_as_of, raw_status, normalized_status,
                    declared_quantity, accepted_quantity, accepted_quantity_kind,
                    act_reference_digest, act_version_digest, presence, completeness,
                    scope_complete, pagination_complete, source_kind,
                    source_fingerprint, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          'OZON_API', ?, ?)""",
                (observation_id, case_id, observation.declaration_id,
                 declaration_revision, observation.captured_at,
                 observation.source_as_of, observation.raw_status,
                 observation.normalized_status.value, observation.declared_quantity,
                 observation.accepted_quantity,
                 None if observation.accepted_quantity_kind is None
                 else observation.accepted_quantity_kind.value,
                 observation.act_reference_digest, observation.act_version_digest,
                 observation.presence.value, observation.metadata.completeness.value,
                 int(observation.scope_complete), int(observation.pagination_complete),
                 observation.metadata.source_fingerprint, payload_json),
            )
            return {"evidence_id": observation_id}

        return cls._append_evidence_revision(
            connection, case_id=case_id, metadata=observation.metadata,
            scope=scope, expected_case_revision=expected_case_revision,
            idempotency_key=idempotency_key, payload_json=payload_json,
            payload_fingerprint=fingerprint, evidence_kind="SUPPLY_OBSERVATION",
            insert=insert, recorded_at=recorded_at,
        )

    @classmethod
    def append_report(
        cls, connection, case_id: str, report: ReportEvidence, scope: dict, *,
        expected_case_revision: int, idempotency_key: str, recorded_at: str,
    ) -> dict:
        payload = cls._evidence_payload(report)
        payload_json = cls._json(payload, cls.MAX_EVIDENCE_PAYLOAD_BYTES)
        fingerprint = cls._digest(payload_json)

        def insert(case_row):
            report_id = "report_" + cls._digest(
                f"{case_id}:{report.report_type.value}:{report.file_sha256}"
            )[:40]
            connection.execute(
                """INSERT INTO fifo_cost_report_evidence (
                    report_evidence_id, case_id, report_type, period_from, period_to,
                    period_provenance, captured_at, file_sha256, parser_version,
                    source_kind, completeness, source_fingerprint,
                    cell_references_json, normalized_fields_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (report_id, case_id, report.report_type.value, report.period_from,
                 report.period_to, report.period_provenance.value, report.captured_at,
                 report.file_sha256, report.parser_version, report.metadata.source_kind.value,
                 report.metadata.completeness.value, report.metadata.source_fingerprint,
                 cls._json(list(report.cell_references), cls.MAX_EVIDENCE_PAYLOAD_BYTES),
                 cls._json(cls._json_value(report.normalized_fields), cls.MAX_EVIDENCE_PAYLOAD_BYTES)),
            )
            return {"evidence_id": report_id}

        return cls._append_evidence_revision(
            connection, case_id=case_id, metadata=report.metadata,
            scope=scope, expected_case_revision=expected_case_revision,
            idempotency_key=idempotency_key, payload_json=payload_json,
            payload_fingerprint=fingerprint, evidence_kind="REPORT_EVIDENCE",
            insert=insert, recorded_at=recorded_at,
        )

    @classmethod
    def read_case(cls, connection, case_id: str, scope: dict, identity: dict) -> dict:
        row = cls._load_case(connection, case_id, scope, identity)
        if row is None:
            return {"error": True, "code": "FIFO_TRANSITION_CASE_NOT_FOUND"}
        revision = connection.execute(
            """SELECT payload_json FROM fifo_cost_transition_case_revisions
               WHERE case_id=? AND case_revision=?""",
            (case_id, row["current_revision"]),
        ).fetchone()
        if revision is None:
            return {"error": True, "code": "FIFO_TRANSITION_CASE_CORRUPT"}
        try:
            payload = json.loads(revision["payload_json"])
        except (TypeError, ValueError):
            return {"error": True, "code": "FIFO_TRANSITION_CASE_CORRUPT"}
        payload.pop("_command_fingerprint", None)
        return {
            "error": False,
            "code": "FIFO_TRANSITION_CASE_FOUND",
            "case_id": case_id,
            "case_revision": row["current_revision"],
            "state": row["current_state"],
            "case": payload,
        }

    @classmethod
    def prepare_case_preview(
        cls, connection, *, case_id, scope, identity, expected_case_revision,
        preview_id, preview_payload, preview_fingerprint, fifo_revision,
        allocation_revision, evidence_set_fingerprint,
        tax_policy_fingerprint, idempotency_key, created_at, expires_at,
    ):
        """Persist a sealed preview and move its case to READY atomically."""
        cls._require_transaction(connection)
        case_row = cls._load_case(connection, case_id, scope, identity)
        if case_row is None:
            return {"error": True, "code": "FIFO_TRANSITION_CASE_NOT_FOUND"}
        existing = connection.execute(
            """SELECT preview_id, case_revision, preview_fingerprint, expires_at
               FROM fifo_cost_transition_previews
               WHERE case_id=? AND preview_fingerprint=?""",
            (case_id, preview_fingerprint),
        ).fetchone()
        if existing is not None:
            if existing["expires_at"] <= created_at:
                return {"error": True, "code": "FIFO_TRANSITION_PREVIEW_EXPIRED"}
            return {
                "error": False, "code": "FIFO_TRANSITION_PREVIEW_READY",
                "preview_id": existing["preview_id"],
                "case_revision": existing["case_revision"],
                "preview_fingerprint": existing["preview_fingerprint"],
                "expires_at": existing["expires_at"], "replayed": True,
            }
        current_revision = connection.execute(
            """SELECT payload_json FROM fifo_cost_transition_case_revisions
               WHERE case_id=? AND case_revision=?""",
            (case_id, case_row["current_revision"]),
        ).fetchone()
        if current_revision is None:
            return {"error": True, "code": "FIFO_TRANSITION_CASE_CORRUPT"}
        try:
            current_payload = json.loads(current_revision["payload_json"])
        except (TypeError, ValueError):
            return {"error": True, "code": "FIFO_TRANSITION_CASE_CORRUPT"}
        last_preview = current_payload.get("last_preview")
        if isinstance(last_preview, dict) and last_preview.get("idempotency_key") == idempotency_key:
            return {"error": True, "code": "FIFO_TRANSITION_IDEMPOTENCY_CONFLICT"}
        if (
            case_row["current_revision"] != expected_case_revision
            or case_row["current_state"] not in {"DRAFT", "AWAITING_EVIDENCE"}
        ):
            return {"error": True, "code": "FIFO_TRANSITION_REVISION_CONFLICT"}
        prior_revision = connection.execute(
            """SELECT payload_json FROM fifo_cost_transition_case_revisions
               WHERE case_id=? AND case_revision=?""",
            (case_id, expected_case_revision),
        ).fetchone()
        if prior_revision is None:
            return {"error": True, "code": "FIFO_TRANSITION_CASE_CORRUPT"}
        try:
            case_payload = json.loads(prior_revision["payload_json"])
        except (TypeError, ValueError):
            return {"error": True, "code": "FIFO_TRANSITION_CASE_CORRUPT"}
        ready_revision = expected_case_revision + 1
        case_payload["case_revision"] = ready_revision
        case_payload["state"] = "READY_TO_CONFIRM"
        case_payload["updated_at"] = created_at
        case_payload["_command_fingerprint"] = preview_fingerprint
        case_payload["last_preview"] = {
            "preview_id": preview_id,
            "preview_fingerprint": preview_fingerprint,
            "idempotency_key": idempotency_key,
        }
        revision_json = cls._json(case_payload, cls.MAX_CASE_PAYLOAD_BYTES)
        update = connection.execute(
            """UPDATE fifo_cost_transition_cases
               SET current_revision=?, current_state='READY_TO_CONFIRM', updated_at=?
               WHERE case_id=? AND owner_fingerprint=? AND tenant_fingerprint=?
                 AND store_id=? AND sku=? AND current_revision=?""",
            (ready_revision, created_at, case_id, scope["owner_fingerprint"],
             scope["tenant_fingerprint"], identity["store_id"], identity["sku"],
             expected_case_revision),
        )
        if update.rowcount != 1:
            return {"error": True, "code": "FIFO_TRANSITION_REVISION_CONFLICT"}
        cls._insert_case_revision(
            connection, case_id=case_id, case_revision=ready_revision,
            state="READY_TO_CONFIRM", payload_json=revision_json,
            fingerprint=cls._digest(revision_json),
            idempotency_key="preview-" + preview_fingerprint[:64],
            created_at=created_at, updated_at=created_at,
        )
        connection.execute(
            """INSERT INTO fifo_cost_transition_previews (
                preview_id, case_id, case_revision, fifo_revision,
                allocation_revision, evidence_set_fingerprint,
                tax_policy_fingerprint, preview_fingerprint, created_at,
                expires_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (preview_id, case_id, ready_revision, fifo_revision,
             allocation_revision, evidence_set_fingerprint,
             tax_policy_fingerprint, preview_fingerprint, created_at,
             expires_at, cls._json(preview_payload, cls.MAX_EVIDENCE_PAYLOAD_BYTES)),
        )
        return {
            "error": False, "code": "FIFO_TRANSITION_PREVIEW_READY",
            "preview_id": preview_id, "case_revision": ready_revision,
            "preview_fingerprint": preview_fingerprint,
            "expires_at": expires_at, "replayed": False,
        }

    @classmethod
    def apply_case_preview(
        cls, connection, *, case_id, scope, identity, expected_case_revision,
        preview_id, idempotency_key, payload_fingerprint, complete_through,
        committed_at,
    ):
        """Append the commit audit and APPLIED case revision in caller txn."""
        cls._require_transaction(connection)
        prior = connection.execute(
            """SELECT commit_id, case_revision, preview_id, payload_fingerprint,
                      complete_through, committed_at
               FROM fifo_cost_transition_commits
               WHERE case_id=? AND idempotency_key=?""",
            (case_id, idempotency_key),
        ).fetchone()
        if prior is not None:
            if (
                prior["payload_fingerprint"] != payload_fingerprint
                or prior["preview_id"] != preview_id
            ):
                return {"error": True, "code": "FIFO_TRANSITION_IDEMPOTENCY_CONFLICT"}
            return {
                "error": False, "code": "FIFO_TRANSITION_APPLIED",
                "commit_id": prior["commit_id"],
                "case_revision": prior["case_revision"],
                "preview_id": prior["preview_id"],
                "complete_through": prior["complete_through"],
                "committed_at": prior["committed_at"], "replayed": True,
            }
        case_row = cls._load_case(connection, case_id, scope, identity)
        if case_row is None:
            return {"error": True, "code": "FIFO_TRANSITION_CASE_NOT_FOUND"}
        if (
            case_row["current_revision"] != expected_case_revision
            or case_row["current_state"] != "READY_TO_CONFIRM"
        ):
            return {"error": True, "code": "FIFO_TRANSITION_REVISION_CONFLICT"}
        preview = connection.execute(
            """SELECT preview_id, case_revision, preview_fingerprint, expires_at
               FROM fifo_cost_transition_previews
               WHERE preview_id=? AND case_id=?""",
            (preview_id, case_id),
        ).fetchone()
        if preview is None or preview["case_revision"] != expected_case_revision:
            return {"error": True, "code": "FIFO_TRANSITION_PREVIEW_STALE"}
        if preview["expires_at"] <= committed_at:
            return {"error": True, "code": "FIFO_TRANSITION_PREVIEW_EXPIRED"}
        current_revision = connection.execute(
            """SELECT payload_json FROM fifo_cost_transition_case_revisions
               WHERE case_id=? AND case_revision=?""",
            (case_id, expected_case_revision),
        ).fetchone()
        if current_revision is None:
            return {"error": True, "code": "FIFO_TRANSITION_CASE_CORRUPT"}
        try:
            case_payload = json.loads(current_revision["payload_json"])
        except (TypeError, ValueError):
            return {"error": True, "code": "FIFO_TRANSITION_CASE_CORRUPT"}
        applied_revision = expected_case_revision + 1
        case_payload["case_revision"] = applied_revision
        case_payload["state"] = "APPLIED"
        case_payload["updated_at"] = committed_at
        case_payload.pop("_command_fingerprint", None)
        case_payload["last_commit"] = {
            "preview_id": preview_id,
            "commit_payload_fingerprint": payload_fingerprint,
        }
        revision_json = cls._json(case_payload, cls.MAX_CASE_PAYLOAD_BYTES)
        commit_id = "transcommit_" + cls._digest({
            "case_id": case_id,
            "preview_id": preview_id,
            "idempotency_key": idempotency_key,
            "payload_fingerprint": payload_fingerprint,
        })[:40]
        connection.execute(
            """INSERT INTO fifo_cost_transition_commits (
                commit_id, case_id, case_revision, preview_id, idempotency_key,
                payload_fingerprint, complete_through, committed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (commit_id, case_id, applied_revision, preview_id, idempotency_key,
             payload_fingerprint, complete_through, committed_at),
        )
        update = connection.execute(
            """UPDATE fifo_cost_transition_cases
               SET current_revision=?, current_state='APPLIED', updated_at=?
               WHERE case_id=? AND owner_fingerprint=? AND tenant_fingerprint=?
                 AND store_id=? AND sku=? AND current_revision=?
                 AND current_state='READY_TO_CONFIRM'""",
            (applied_revision, committed_at, case_id,
             scope["owner_fingerprint"], scope["tenant_fingerprint"],
             identity["store_id"], identity["sku"], expected_case_revision),
        )
        if update.rowcount != 1:
            return {"error": True, "code": "FIFO_TRANSITION_REVISION_CONFLICT"}
        cls._insert_case_revision(
            connection, case_id=case_id, case_revision=applied_revision,
            state="APPLIED", payload_json=revision_json,
            fingerprint=cls._digest(revision_json),
            idempotency_key="apply-" + payload_fingerprint[:64],
            created_at=committed_at, updated_at=committed_at,
        )
        return {
            "error": False, "code": "FIFO_TRANSITION_APPLIED",
            "commit_id": commit_id, "case_revision": applied_revision,
            "preview_id": preview_id, "complete_through": complete_through,
            "committed_at": committed_at, "replayed": False,
        }

    @classmethod
    def list_cases(
        cls, connection, scope: dict, *, store_id: str, sku: str | None = None,
        states: tuple[str, ...] = ("DRAFT", "AWAITING_EVIDENCE", "READY_TO_CONFIRM"),
        limit: int = 100,
    ) -> dict:
        if type(limit) is not int or not 1 <= limit <= 100:
            return {"error": True, "code": "FIFO_TRANSITION_LIMIT_INVALID"}
        allowed_states = {
            "DRAFT", "AWAITING_EVIDENCE", "READY_TO_CONFIRM", "APPLIED", "CANCELLED",
        }
        if (
            not isinstance(states, (tuple, list)) or not states
            or any(not isinstance(state, str) or state not in allowed_states for state in states)
            or len(set(states)) != len(states)
        ):
            return {"error": True, "code": "FIFO_TRANSITION_STATE_FILTER_INVALID"}
        where = [
            "owner_fingerprint=?", "tenant_fingerprint=?", "store_id=?",
            f"current_state IN ({','.join('?' for _ in states)})",
        ]
        params = [
            scope["owner_fingerprint"], scope["tenant_fingerprint"], store_id,
            *states,
        ]
        if sku is not None:
            where.append("sku=?")
            params.append(sku)
        params.append(limit)
        rows = connection.execute(
            """SELECT case_id, product_id, offer_id, sku FROM fifo_cost_transition_cases
               WHERE """ + " AND ".join(where) + " ORDER BY updated_at DESC, case_id LIMIT ?",
            params,
        ).fetchall()
        cases = []
        for row in rows:
            item = cls.read_case(
                connection, row["case_id"], scope,
                {
                    "store_id": store_id,
                    "product_id": row["product_id"],
                    "offer_id": row["offer_id"],
                    "sku": row["sku"],
                },
            )
            if item.get("error"):
                return item
            cases.append(item)
        return {
            "error": False,
            "code": "FIFO_TRANSITION_CASES_FOUND",
            "store_id": store_id,
            "cases": cases,
            "count": len(cases),
            "limit": limit,
        }

    @classmethod
    def read_evidence(
        cls, connection, case_id: str, scope: dict, identity: dict, *,
        kind: str, limit: int = 100, include_encrypted_lookup_reference: bool = False,
    ) -> dict:
        if type(limit) is not int or not 1 <= limit <= 2000:
            return {"error": True, "code": "FIFO_TRANSITION_LIMIT_INVALID"}
        case_row = cls._load_case(connection, case_id, scope, identity)
        if case_row is None:
            return {"error": True, "code": "FIFO_TRANSITION_CASE_NOT_FOUND"}
        if kind == "SUPPLY_DECLARATION":
            sql = """SELECT declaration_row_id AS evidence_id, declaration_id,
                            declaration_revision AS evidence_revision,
                            reference_kind, reference_digest, declared_shipped_units,
                            dispatch_date, payload_json, recorded_at,
                            encrypted_lookup_reference
                     FROM fifo_cost_supply_declarations
                     WHERE case_id=? ORDER BY recorded_at, declaration_id,
                     declaration_revision LIMIT ?"""
        elif kind == "SUPPLY_OBSERVATION":
            sql = """SELECT observation_id AS evidence_id, declaration_id,
                            captured_at, source_as_of, normalized_status, presence,
                            declared_quantity, accepted_quantity, payload_json
                     FROM fifo_cost_supply_observations
                     WHERE case_id=? ORDER BY captured_at, observation_id LIMIT ?"""
        elif kind == "REPORT_EVIDENCE":
            sql = """SELECT report_evidence_id AS evidence_id, report_type,
                            period_from, period_to, period_provenance, captured_at,
                            file_sha256, parser_version, source_kind, completeness,
                            cell_references_json, normalized_fields_json
                     FROM fifo_cost_report_evidence
                     WHERE case_id=? ORDER BY captured_at, report_evidence_id LIMIT ?"""
        else:
            return {"error": True, "code": "FIFO_TRANSITION_EVIDENCE_KIND_INVALID"}
        rows = connection.execute(sql, (case_id, limit)).fetchall()
        items = []
        for row in rows:
            item = {key: row[key] for key in row.keys() if key != "payload_json"}
            if kind == "SUPPLY_DECLARATION":
                item["lookup_reference_available"] = bool(
                    item.get("encrypted_lookup_reference")
                )
                if not include_encrypted_lookup_reference:
                    item.pop("encrypted_lookup_reference", None)
            if kind == "REPORT_EVIDENCE":
                item["payload"] = {
                    "cell_references": json.loads(item.pop("cell_references_json")),
                    "normalized_fields": json.loads(item.pop("normalized_fields_json")),
                }
            else:
                item["payload"] = json.loads(row["payload_json"])
            items.append(item)
        return {
            "error": False, "code": "FIFO_TRANSITION_EVIDENCE_FOUND",
            "case_id": case_id, "case_revision": case_row["current_revision"],
            "kind": kind, "items": items,
        }

    @classmethod
    def _append_evidence_revision(
        cls, connection, *, case_id, metadata, scope, expected_case_revision,
        idempotency_key, payload_json, payload_fingerprint, evidence_kind,
        insert, recorded_at,
    ):
        cls._require_transaction(connection)
        identity = cls._metadata_identity(metadata)
        case_row = cls._load_case(connection, case_id, scope, identity)
        if case_row is None:
            return {"error": True, "code": "FIFO_TRANSITION_CASE_NOT_FOUND"}
        prior = cls._idempotent_revision(
            connection, case_id, idempotency_key, payload_fingerprint,
        )
        if prior is not None:
            return prior
        if case_row["current_state"] in {"APPLIED", "CANCELLED"}:
            return {"error": True, "code": "FIFO_TRANSITION_CASE_NOT_READY"}
        if case_row["current_revision"] != expected_case_revision:
            return {"error": True, "code": "FIFO_TRANSITION_REVISION_CONFLICT"}
        if evidence_kind == "SUPPLY_OBSERVATION":
            count = connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_supply_observations WHERE case_id=?",
                (case_id,),
            ).fetchone()[0]
            if count >= cls.MAX_OBSERVATIONS_PER_CASE:
                return {"error": True, "code": "FIFO_TRANSITION_OBSERVATION_LIMIT_REACHED"}

        inserted = insert(case_row)
        if inserted.get("error"):
            return inserted
        new_revision = expected_case_revision + 1
        current = connection.execute(
            """SELECT payload_json FROM fifo_cost_transition_case_revisions
               WHERE case_id=? AND case_revision=?""",
            (case_id, expected_case_revision),
        ).fetchone()
        if current is None:
            return {"error": True, "code": "FIFO_TRANSITION_CASE_CORRUPT"}
        try:
            case_snapshot = json.loads(current["payload_json"])
        except (TypeError, ValueError):
            return {"error": True, "code": "FIFO_TRANSITION_CASE_CORRUPT"}
        case_snapshot["case_revision"] = new_revision
        case_snapshot["state"] = "AWAITING_EVIDENCE"
        case_snapshot["updated_at"] = recorded_at
        case_snapshot["_command_fingerprint"] = payload_fingerprint
        case_snapshot["last_evidence"] = {
            "kind": evidence_kind,
            "evidence_id": inserted["evidence_id"],
            "payload_fingerprint": payload_fingerprint,
        }
        revision_json = cls._json(case_snapshot, cls.MAX_CASE_PAYLOAD_BYTES)
        revision_fingerprint = cls._digest(revision_json)
        update = connection.execute(
            """UPDATE fifo_cost_transition_cases
               SET current_revision=?, current_state='AWAITING_EVIDENCE', updated_at=?
               WHERE case_id=? AND owner_fingerprint=? AND tenant_fingerprint=?
                 AND store_id=? AND sku=? AND current_revision=?""",
            (new_revision, recorded_at, case_id, scope["owner_fingerprint"],
             scope["tenant_fingerprint"], identity["store_id"], identity["sku"],
             expected_case_revision),
        )
        if update.rowcount != 1:
            return {"error": True, "code": "FIFO_TRANSITION_REVISION_CONFLICT"}
        cls._insert_case_revision(
            connection, case_id=case_id, case_revision=new_revision,
            state="AWAITING_EVIDENCE", payload_json=revision_json,
            fingerprint=revision_fingerprint, idempotency_key=idempotency_key,
            created_at=recorded_at, updated_at=recorded_at,
        )
        return {
            "error": False,
            "code": "FIFO_TRANSITION_EVIDENCE_SAVED",
            "case_id": case_id,
            "case_revision": new_revision,
            "state": "AWAITING_EVIDENCE",
            "evidence_id": inserted["evidence_id"],
            "replayed": False,
        }

    @classmethod
    def _idempotent_revision(cls, connection, case_id, idempotency_key, fingerprint):
        row = connection.execute(
            """SELECT case_revision, payload_fingerprint, payload_json, state
               FROM fifo_cost_transition_case_revisions
               WHERE case_id=? AND idempotency_key=?""",
            (case_id, idempotency_key),
        ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError):
            return {"error": True, "code": "FIFO_TRANSITION_CASE_CORRUPT"}
        if payload.get("_command_fingerprint", row["payload_fingerprint"]) != fingerprint:
            return {"error": True, "code": "FIFO_TRANSITION_IDEMPOTENCY_CONFLICT"}
        return {
            "error": False,
            "code": "FIFO_TRANSITION_REPLAYED",
            "case_id": case_id,
            "case_revision": row["case_revision"],
            "state": row["state"],
            "result": payload.get("last_evidence"),
            "replayed": True,
        }

    @staticmethod
    def _insert_case_revision(
        connection, *, case_id, case_revision, state, payload_json,
        fingerprint, idempotency_key, created_at, updated_at,
    ):
        revision_id = "caserev_" + hashlib.sha256(
            f"{case_id}:{case_revision}:{fingerprint}".encode("utf-8")
        ).hexdigest()[:40]
        connection.execute(
            """INSERT INTO fifo_cost_transition_case_revisions (
                revision_id, case_id, case_revision, schema_version, state,
                payload_json, payload_fingerprint, idempotency_key, created_at, updated_at
            ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?)""",
            (revision_id, case_id, case_revision, state, payload_json,
             fingerprint, idempotency_key, created_at, updated_at),
        )

    @classmethod
    def _load_case(cls, connection, case_id, scope, identity):
        return connection.execute(
            """SELECT * FROM fifo_cost_transition_cases
               WHERE case_id=? AND owner_fingerprint=? AND tenant_fingerprint=?
                 AND store_id=? AND sku=? AND product_id IS ? AND offer_id IS ?""",
            (case_id, scope["owner_fingerprint"], scope["tenant_fingerprint"],
             identity["store_id"], identity["sku"], identity["product_id"],
             identity["offer_id"]),
        ).fetchone()

    @staticmethod
    def _metadata_identity(metadata):
        identity = metadata.scope
        return {
            "store_id": identity.store_id,
            "product_id": identity.product_id,
            "offer_id": identity.offer_id,
            "sku": identity.sku,
        }

    @staticmethod
    def _metadata_payload(metadata):
        scope = metadata.scope
        return {
            "schema_version": metadata.schema_version,
            "scope": {
                "store_id": scope.store_id,
                "product_id": scope.product_id,
                "offer_id": scope.offer_id,
                "sku": scope.sku,
            },
            "source_kind": metadata.source_kind.value,
            "completeness": metadata.completeness.value,
            "source_fingerprint": metadata.source_fingerprint,
            "store_timezone": metadata.store_timezone,
        }

    @classmethod
    def _evidence_payload(cls, evidence):
        if isinstance(evidence, SupplyDeclaration):
            excluded = {"metadata", "unknown_values", "encrypted_lookup_reference"}
        else:
            excluded = {"metadata", "unknown_values"}
        payload = {
            "metadata": cls._metadata_payload(evidence.metadata),
            **{
                item.name: cls._json_value(getattr(evidence, item.name))
                for item in fields(evidence)
                if item.name not in excluded
            },
            "unknown_values": cls._unknown_payload(
                getattr(evidence, "unknown_values", {})
            ),
        }
        return payload

    @staticmethod
    def _unknown_payload(unknown_values):
        return {
            name: {
                "reason_code": value.reason_code.value,
                "source_kind": value.source_kind.value,
            }
            for name, value in sorted(unknown_values.items())
        }

    @classmethod
    def _json_value(cls, value):
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, Decimal):
            return format(value, "f")
        if isinstance(value, Mapping):
            return {str(key.value if isinstance(key, Enum) else key): cls._json_value(item)
                    for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [cls._json_value(item) for item in value]
        if is_dataclass(value):
            return {item.name: cls._json_value(getattr(value, item.name))
                    for item in fields(value)}
        return value

    @classmethod
    def _json(cls, value, max_bytes):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(text.encode("utf-8")) > max_bytes:
            raise ValueError("FIFO_TRANSITION_PAYLOAD_TOO_LARGE")
        return text

    @staticmethod
    def _digest(value):
        return hashlib.sha256(str(value).encode("utf-8")).hexdigest()

    @staticmethod
    def _require_transaction(connection):
        if not connection.in_transaction:
            raise sqlite3.ProgrammingError("FIFO transition store requires caller transaction")
