"""Build a bounded, privacy-safe export from persisted price experiment history."""

import hashlib
import json

from services.unit_economics_experiment_snapshot_view_service import (
    UnitEconomicsExperimentSnapshotViewService,
)
from services.planning_unit_economics_experiment_adapter import (
    PlanningUnitEconomicsExperimentAdapter,
)


class _HistoryQuotaExceeded(Exception):
    pass


class UnitEconomicsExperimentHistoryExportService:
    """Export one exact experiment and all bounded local history without source I/O."""

    PAGE_SIZE = 10
    MAX_EXPERIMENT_REVISIONS = 500
    MAX_PHASE_REVISIONS = 500
    MAX_PHASES = 10
    MAX_EVENTS = 100
    MAX_COLLECTIONS_PER_PHASE = 20
    MAX_RESULTS_PER_PHASE = 20
    MAX_DECISIONS = 100
    MAX_TOTAL_ROWS = 5000

    def __init__(self, *, repository, analytics_export_service):
        self.repository = repository
        self.analytics_export_service = analytics_export_service

    def export(self, experiment_id, file_format, *, owner_id, store_id):
        try:
            return self._export(
                experiment_id, file_format, owner_id=owner_id, store_id=store_id,
            )
        except _HistoryQuotaExceeded:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_QUOTA_EXCEEDED")
        except (KeyError, TypeError, ValueError, OverflowError):
            return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_HISTORY_INVALID")

    def _export(self, experiment_id, file_format, *, owner_id, store_id):
        if (not isinstance(owner_id, str) or not owner_id.strip()
                or not isinstance(store_id, str) or not store_id.strip()
                or file_format not in {"json", "csv"}):
            return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_INPUT_INVALID")
        initial = self.repository.get_price_experiment(
            experiment_id, owner_id=owner_id, store_id=store_id,
        )
        experiment = initial.get("experiment") if isinstance(initial, dict) else None
        if not isinstance(experiment, dict):
            return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_UNAVAILABLE")
        frozen = self.repository.get_price_experiment_frozen_snapshot(
            experiment_id, owner_id=owner_id, store_id=store_id,
        )
        if not isinstance(frozen, dict) or frozen.get("error") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_SNAPSHOT_UNAVAILABLE")
        projected = UnitEconomicsExperimentSnapshotViewService.project(frozen)
        if not isinstance(projected, dict) or projected.get("error") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_SNAPSHOT_INVALID")
        phases_result = self.repository.list_price_experiment_phases(
            experiment_id, limit=self.MAX_PHASES,
            owner_id=owner_id, store_id=store_id,
        )
        if not isinstance(phases_result, dict) or phases_result.get("error") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_PHASES_UNAVAILABLE")
        if phases_result.get("has_more") is True:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_QUOTA_EXCEEDED")
        phases = phases_result.get("items")
        if not isinstance(phases, list) or len(phases) > self.MAX_PHASES:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_PHASES_INVALID")

        rows = []
        counts = {}
        self._append(rows, counts, "EXPERIMENT_CURRENT", experiment["state_revision"],
                     experiment["status"], experiment.get("updated_at"), None,
                     self._experiment_config(experiment["config"]), None)

        revisions = self._pages(
            self.repository.list_price_experiment_revisions,
            (experiment_id,), {"owner_id": owner_id, "store_id": store_id},
            maximum=self.MAX_EXPERIMENT_REVISIONS,
        )
        if revisions.get("error"):
            return revisions
        for item in revisions["items"]:
            self._append(
                rows, counts, "EXPERIMENT_REVISION", item["revision"],
                item["status"], item["created_at"], None,
                self._experiment_config(item["config"]), None,
            )

        phase_identity = {}
        for phase in phases:
            phase_id = phase.get("phase_id")
            if not isinstance(phase_id, str):
                return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_PHASE_INVALID")
            config = phase.get("config") or {}
            phase_label = self._phase_label(config)
            phase_identity[phase_id] = {
                "label": phase_label, "segment_number": config.get("segment_number"),
                "planned_price_cents": config.get("planned_price_cents"),
            }
            phase_revisions = self._pages(
                self.repository.list_price_experiment_phase_revisions,
                (experiment_id, phase_id), {"owner_id": owner_id, "store_id": store_id},
                maximum=self.MAX_PHASE_REVISIONS,
            )
            if phase_revisions.get("error"):
                return phase_revisions
            for item in phase_revisions["items"]:
                payload = self._phase_revision(item)
                if payload is None:
                    return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_PHASE_REVISION_INVALID")
                self._append(
                    rows, counts, "PHASE_REVISION", item["revision"],
                    item["status"], item["created_at"], phase_label, payload, None,
                )

            collections = self._pages(
                self.repository.list_price_experiment_phase_collections,
                (experiment_id, phase_id), {"owner_id": owner_id, "store_id": store_id},
                maximum=self.MAX_COLLECTIONS_PER_PHASE,
            )
            if collections.get("error"):
                return collections
            for item in collections["items"]:
                payload = self._collection(item.get("payload"))
                if payload is None:
                    return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_COLLECTION_INVALID")
                self._append(
                    rows, counts, "PHASE_COLLECTION", item["collection_revision"],
                    payload["status"], item["created_at"], phase_label,
                    payload, item["collection_id"],
                )

            results = self._pages(
                self.repository.list_price_experiment_results,
                (experiment_id, phase_id), {"owner_id": owner_id, "store_id": store_id},
                maximum=self.MAX_RESULTS_PER_PHASE,
            )
            if results.get("error"):
                return results
            for item in results["items"]:
                payload = self._result(item.get("payload"))
                if payload is None:
                    return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_RESULT_INVALID")
                self._append(
                    rows, counts, "PHASE_RESULT", item["result_revision"],
                    payload["outcome"], item["created_at"], phase_label,
                    payload, item["content_hash"],
                )

        events = self._pages(
            self.repository.list_price_experiment_events, (experiment_id,),
            {"owner_id": owner_id, "store_id": store_id}, maximum=self.MAX_EVENTS,
        )
        if events.get("error"):
            return events
        for item in events["items"]:
            payload = self._event(item.get("payload"), phase_identity)
            if payload is None:
                return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_EVENT_INVALID")
            self._append(
                rows, counts, "CONTROL_EVENT", item["event_revision"],
                item["event_kind"], item["created_at"], payload.get("phase"),
                payload["payload"], None,
            )

        decisions = self._pages(
            self.repository.list_price_experiment_owner_decisions, (experiment_id,),
            {"owner_id": owner_id, "store_id": store_id}, maximum=self.MAX_DECISIONS,
        )
        if decisions.get("error"):
            return decisions
        for item in decisions["items"]:
            payload = self._decision(item.get("payload"), phase_identity)
            if payload is None:
                return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_DECISION_INVALID")
            self._append(
                rows, counts, "OWNER_DECISION", item["decision_revision"],
                payload["decision_type"], item["created_at"], None,
                payload, item["content_hash"],
            )

        if len(rows) > self.MAX_TOTAL_ROWS:
            return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_QUOTA_EXCEEDED")
        if not self._unchanged(
            experiment_id, experiment, phases, owner_id=owner_id, store_id=store_id,
        ):
            return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_CHANGED_RETRY")

        metadata = {
            "exported_scope": "all_persisted_experiment_phase_collection_result_event_and_decision_revisions",
            "source_reads": False,
            "recalculated_on_export": False,
            "phase_count": len(phases),
            "record_count": len(rows),
            "record_counts": counts,
            "frozen_economics_snapshot": projected["view"],
            "privacy": "tenant_and_product_identifiers_omitted",
        }
        output = self.analytics_export_service.export_unit_economics_experiment_history(
            rows, metadata, file_format,
        )
        if not isinstance(output, dict) or output.get("error") is True:
            return output if isinstance(output, dict) else self._error(
                "UNIT_ECONOMICS_EXPERIMENT_EXPORT_FAILED",
            )
        output["message"] = (
            f"Экспорт сохранённой истории эксперимента готов: {len(rows)} записей, "
            f"{len(phases)} фаз. Источники не перечитывались; расчёты не повторялись."
        )
        return output

    def _pages(self, method, args, kwargs, *, maximum):
        values = []
        offset = 0
        page_count = 0
        seen = set()
        while True:
            page_count += 1
            if page_count > maximum // self.PAGE_SIZE + 2:
                return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_QUOTA_EXCEEDED")
            result = method(
                *args, limit=self.PAGE_SIZE, offset=offset, **kwargs,
            )
            if not isinstance(result, dict) or result.get("error") is True:
                return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_HISTORY_UNAVAILABLE")
            items = result.get("items")
            if not isinstance(items, list) or len(items) > self.PAGE_SIZE:
                return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_HISTORY_INVALID")
            if len(values) + len(items) > maximum:
                return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_QUOTA_EXCEEDED")
            for item in items:
                key = self._row_identity(item)
                if key is None or key in seen:
                    return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_HISTORY_CHANGED")
                seen.add(key)
                values.append(item)
            if result.get("has_more") is not True:
                break
            next_offset = result.get("next_offset")
            if type(next_offset) is not int or next_offset <= offset:
                return self._error("UNIT_ECONOMICS_EXPERIMENT_EXPORT_HISTORY_INVALID")
            offset = next_offset
        return {"error": False, "items": values}

    @staticmethod
    def _row_identity(value):
        if not isinstance(value, dict):
            return None
        for key in ("revision", "decision_revision", "event_revision", "collection_revision",
                    "result_revision"):
            if type(value.get(key)) is int:
                return key, value[key]
        return None

    @staticmethod
    def _experiment_config(config):
        if not isinstance(config, dict):
            return None
        references = config.get("source_references") or {}
        plan = references.get("plan") or {}
        tariff = references.get("tariff")
        observation = references.get("observation")
        return {
            "metric": config.get("metric"),
            "calculation_mode": config.get("calculation_mode"),
            "candidate_prices_cents": list(config.get("candidate_prices_cents") or []),
            "decision_threshold_rub": config.get("decision_threshold_rub"),
            "planned_duration_days": config.get("planned_duration_days"),
            "currency": config.get("currency"),
            "control_flags": dict(config.get("control_flags") or {}),
            "source_revisions": {
                "plan_revision": plan.get("revision"),
                "tariff_revision": tariff.get("revision") if isinstance(tariff, dict) else None,
                "observation_result_revision": (
                    observation.get("result_revision") if isinstance(observation, dict) else None
                ),
            },
        }

    @classmethod
    def _phase_revision(cls, item):
        config = item.get("config")
        if not isinstance(config, dict):
            return None
        confirmation = item.get("confirmation")
        safe_confirmation = None
        if isinstance(confirmation, dict):
            safe_confirmation = {
                key: confirmation.get(key) for key in (
                    "schema_version", "seller_price_cents", "effective_from", "confirmed_at",
                    "timezone", "first_full_local_day", "owner_confirmed",
                    "price_evidence_kind", "price_history_verified",
                )
            }
        return {
            "kind": config.get("kind"), "segment_number": config.get("segment_number"),
            "planned_price_cents": config.get("planned_price_cents"),
            # Snapshot IDs are SHA-256 content references by repository contract.
            "expense_snapshot_fingerprint": config.get("expense_snapshot_id"),
            "planned_from_date": config.get("planned_from_date"),
            "planned_to_date": config.get("planned_to_date"),
            "timezone": config.get("timezone"),
            "control_flags": dict(config.get("control_flags") or {}),
            "confirmation": safe_confirmation,
            "observation_attached": isinstance(item.get("observation_id"), str),
        }

    @staticmethod
    def _phase_label(config):
        kind = {"BASELINE": "Базовая", "CANDIDATE": "Кандидат"}.get(config.get("kind"), "Фаза")
        return f"{kind} {config.get('segment_number', '—')}"

    @staticmethod
    def _collection(payload):
        if not isinstance(payload, dict):
            return None
        return {
            key: payload.get(key) for key in (
                "schema_version", "status", "collected_at", "window", "seller_price_cents",
                "source_statuses", "metrics", "price_history_verified", "limitations", "budget",
            )
        }

    @staticmethod
    def _result(payload):
        normalized = PlanningUnitEconomicsExperimentAdapter.normalize_result(payload)
        if normalized is None:
            return None
        # These references are validated SHA-256 content hashes, not database IDs.
        return dict(normalized)

    @staticmethod
    def _event(payload, phase_identity):
        if not isinstance(payload, dict):
            return None
        phase_id = payload.get("phase_id")
        phase = phase_identity.get(phase_id)
        kind = payload.get("event_kind")
        if phase is None:
            return None
        if kind == "CONTROL_UPDATE":
            safe = {
                "schema_version": payload.get("schema_version"), "event_kind": kind,
                "control_flags": payload.get("control_flags"),
                "source": payload.get("source"), "compatibility": payload.get("compatibility"),
            }
        elif kind == "PAUSE":
            safe = {
                "schema_version": payload.get("schema_version"), "event_kind": kind,
                "resume_target": payload.get("resume_target"), "source": payload.get("source"),
            }
        elif kind == "RESUME_SEGMENT_PREPARED":
            previous = phase_identity.get(payload.get("previous_phase_id"))
            safe = {
                "schema_version": payload.get("schema_version"), "event_kind": kind,
                "previous_phase": previous.get("label") if previous else None,
                "resume_target": payload.get("resume_target"), "source": payload.get("source"),
            }
        else:
            return None
        return {"phase": phase["label"], "payload": safe}

    @staticmethod
    def _decision(payload, phase_identity):
        if not isinstance(payload, dict):
            return None
        result_phase = phase_identity.get(payload.get("result_phase_id"))
        selected_phase = phase_identity.get(payload.get("selected_phase_id"))
        if result_phase is None:
            return None
        return {
            "decision_type": payload.get("decision_type"),
            "result_phase": result_phase["label"],
            "result_revision": payload.get("result_revision"),
            "selected_phase": selected_phase["label"] if selected_phase else None,
            "selected_price_cents": selected_phase.get("planned_price_cents") if selected_phase else None,
        }

    def _append(self, rows, counts, record_type, revision, state, created_at, phase, payload, content_hash):
        if payload is None or type(revision) is not int or revision < 1:
            raise ValueError("invalid history row")
        if len(rows) >= self.MAX_TOTAL_ROWS:
            raise _HistoryQuotaExceeded
        rows.append({
            "record_type": record_type, "revision": revision,
            "state": str(state), "created_at": str(created_at or ""),
            "phase": phase, "payload": payload, "content_hash": content_hash,
        })
        counts[record_type] = counts.get(record_type, 0) + 1

    def _unchanged(self, experiment_id, original, phases, *, owner_id, store_id):
        current = self.repository.get_price_experiment(
            experiment_id, owner_id=owner_id, store_id=store_id,
        )
        experiment = current.get("experiment") if isinstance(current, dict) else None
        if (not isinstance(experiment, dict)
                or experiment.get("state_revision") != original.get("state_revision")
                or experiment.get("result_revision") != original.get("result_revision")):
            return False
        latest = self.repository.list_price_experiment_phases(
            experiment_id, limit=self.MAX_PHASES,
            owner_id=owner_id, store_id=store_id,
        )
        if (not isinstance(latest, dict) or latest.get("error") is True
                or latest.get("has_more") is True or len(latest.get("items", [])) != len(phases)):
            return False
        initial_by_id = {item.get("phase_id"): item for item in phases}
        for item in latest.get("items", []):
            initial = initial_by_id.get(item.get("phase_id"))
            if (initial is None or item.get("state_revision") != initial.get("state_revision")
                    or item.get("result_revision") != initial.get("result_revision")):
                return False
        return True

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "read_only": True, "source_io": False}
