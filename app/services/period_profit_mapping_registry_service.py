import json
import os
from copy import deepcopy
from datetime import datetime, timezone


SCOPES = {"RETURN", "ADVERTISING", "STORAGE"}


class PeriodProfitMappingRegistryService:
    """Local registry for reviewed mapping artifacts; never mutates Ozon or profit data."""

    def __init__(self, storage_path, clock=None):
        self.storage_path = storage_path
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat())

    def save(self, scope, mapping, actor="USER", activate=False):
        normalized = str(scope or "").strip().upper()
        validation = self._validate_mapping(normalized, mapping)
        if validation is not None:
            return validation

        registry = self._load_registry()
        scope_state = registry["scopes"].setdefault(normalized, {"active_revision_id": None, "revisions": [], "events": []})
        revision_number = len(scope_state["revisions"]) + 1
        revision_id = f"{normalized.lower()}-mapping-r{revision_number}"
        revision = {
            "revision_id": revision_id,
            "revision_number": revision_number,
            "scope": normalized,
            "mapping_id": mapping.get("mapping_id"),
            "mapping": deepcopy(dict(mapping)),
            "created_at": self.clock(),
            "created_by": str(actor or "USER"),
            "supersedes_revision_id": scope_state.get("active_revision_id"),
            "immutable_revision": True,
        }
        scope_state["revisions"].append(revision)
        if activate:
            scope_state["active_revision_id"] = revision_id
            self._append_event(scope_state, "ACTIVATE", revision_id, actor)
        else:
            self._append_event(scope_state, "SAVE", revision_id, actor)
        self._write_registry(registry)
        return {
            "error": False,
            "status": "PERIOD_PROFIT_MAPPING_REVISION_SAVED",
            "scope": normalized,
            "revision_id": revision_id,
            "active": bool(activate),
            "mapping_id": mapping.get("mapping_id"),
            "read_only_business_data": True,
            "ozon_mutation": False,
            "profit_adjustment_allowed": False,
            "executed": False,
        }

    def activate(self, scope, revision_id, actor="USER"):
        normalized = str(scope or "").strip().upper()
        registry = self._load_registry()
        scope_state = registry["scopes"].get(normalized)
        revision = self._find_revision(scope_state, revision_id)
        if revision is None:
            return self._error("PERIOD_PROFIT_MAPPING_REVISION_NOT_FOUND")
        scope_state["active_revision_id"] = revision_id
        self._append_event(scope_state, "ACTIVATE", revision_id, actor)
        self._write_registry(registry)
        return self._activation_result(normalized, revision, "PERIOD_PROFIT_MAPPING_REVISION_ACTIVATED")

    def rollback(self, scope, target_revision_id, actor="USER"):
        normalized = str(scope or "").strip().upper()
        registry = self._load_registry()
        scope_state = registry["scopes"].get(normalized)
        revision = self._find_revision(scope_state, target_revision_id)
        if revision is None:
            return self._error("PERIOD_PROFIT_MAPPING_REVISION_NOT_FOUND")
        previous = scope_state.get("active_revision_id")
        scope_state["active_revision_id"] = target_revision_id
        self._append_event(scope_state, "ROLLBACK", target_revision_id, actor, previous_revision_id=previous)
        self._write_registry(registry)
        result = self._activation_result(normalized, revision, "PERIOD_PROFIT_MAPPING_ROLLBACK_APPLIED")
        result["previous_revision_id"] = previous
        return result

    def load_active(self, scope):
        normalized = str(scope or "").strip().upper()
        registry = self._load_registry()
        scope_state = registry["scopes"].get(normalized)
        if not scope_state or not scope_state.get("active_revision_id"):
            return None
        revision = self._find_revision(scope_state, scope_state["active_revision_id"])
        return deepcopy(revision.get("mapping")) if revision else None

    def history(self, scope):
        normalized = str(scope or "").strip().upper()
        registry = self._load_registry()
        scope_state = registry["scopes"].get(normalized) or {"active_revision_id": None, "revisions": [], "events": []}
        return {
            "error": False,
            "status": "PERIOD_PROFIT_MAPPING_HISTORY_READY",
            "scope": normalized,
            "active_revision_id": scope_state.get("active_revision_id"),
            "revisions": deepcopy(scope_state.get("revisions") or []),
            "events": deepcopy(scope_state.get("events") or []),
            "read_only": True,
            "executed": False,
        }

    def _validate_mapping(self, scope, mapping):
        source = dict(mapping or {})
        if scope not in SCOPES:
            return self._error("PERIOD_PROFIT_MAPPING_SCOPE_INVALID")
        if scope == "RETURN":
            valid = (
                source.get("status") == "RETURN_FINANCIAL_OPERATION_AUTHORIZED_MAPPING_READY"
                and source.get("mapping_authorized") is True
                and source.get("financial_evidence_mapping_allowed") is True
                and source.get("returns_profit_adjustment_allowed") is False
                and source.get("automatic_activation_allowed") is False
                and source.get("immutable_artifact") is True
            )
        else:
            valid = (
                source.get("status") == "PERIOD_PROFIT_EXPENSE_OPERATION_AUTHORIZED_MAPPING_READY"
                and source.get("scope") == scope
                and source.get("mapping_authorized") is True
                and source.get("financial_evidence_mapping_allowed") is True
                and source.get("profit_adjustment_allowed") is False
                and source.get("automatic_activation_allowed") is False
                and source.get("immutable_artifact") is True
            )
        if not valid or not source.get("mapping_id"):
            return self._error("PERIOD_PROFIT_AUTHORIZED_MAPPING_REQUIRED")
        return None

    def _load_registry(self):
        if not self.storage_path or not os.path.exists(self.storage_path):
            return {"schema_version": 1, "scopes": {}}
        with open(self.storage_path, "r", encoding="utf-8") as stream:
            data = json.load(stream)
        if not isinstance(data, dict):
            return {"schema_version": 1, "scopes": {}}
        data.setdefault("schema_version", 1)
        data.setdefault("scopes", {})
        return data

    def _write_registry(self, registry):
        directory = os.path.dirname(self.storage_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        temporary = self.storage_path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(registry, stream, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temporary, self.storage_path)

    def _find_revision(self, scope_state, revision_id):
        if not scope_state:
            return None
        for revision in scope_state.get("revisions") or []:
            if revision.get("revision_id") == revision_id:
                return revision
        return None

    def _append_event(self, scope_state, event, revision_id, actor, previous_revision_id=None):
        scope_state.setdefault("events", []).append({
            "event": event,
            "revision_id": revision_id,
            "previous_revision_id": previous_revision_id,
            "at": self.clock(),
            "actor": str(actor or "USER"),
        })

    def _activation_result(self, scope, revision, status):
        return {
            "error": False,
            "status": status,
            "scope": scope,
            "revision_id": revision.get("revision_id"),
            "mapping_id": revision.get("mapping_id"),
            "active": True,
            "ozon_mutation": False,
            "profit_adjustment_allowed": False,
            "executed": False,
        }

    def _error(self, code):
        return {
            "error": True,
            "code": code,
            "status": "PERIOD_PROFIT_MAPPING_REGISTRY_UNAVAILABLE",
            "ozon_mutation": False,
            "profit_adjustment_allowed": False,
            "executed": False,
        }
