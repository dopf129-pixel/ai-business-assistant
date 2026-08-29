import json
import os
from copy import deepcopy
from datetime import datetime, timezone

from period_profit_mapping_integrity import verify_period_profit_mapping_integrity


SCOPES = {"RETURN", "ADVERTISING", "STORAGE"}
SCHEMA_VERSION = 1


class PeriodProfitMappingRegistryService:
    """Versioned local registry for reviewed mappings; fails closed on unsafe runtime data."""

    def __init__(self, storage_path, clock=None):
        self.storage_path = storage_path
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat())

    def save(self, scope, mapping, actor="USER", activate=False):
        normalized = str(scope or "").strip().upper()
        validation = self._validate_mapping(normalized, mapping)
        if validation is not None:
            return validation
        registry, health = self._read_registry()
        if health.get("writable") is not True:
            return self._health_error(health)

        scope_state = registry["scopes"].setdefault(
            normalized,
            {"active_revision_id": None, "revisions": [], "events": []},
        )
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
        registry, health = self._read_registry()
        if health.get("writable") is not True:
            return self._health_error(health)
        scope_state = registry["scopes"].get(normalized)
        revision = self._find_revision(scope_state, revision_id)
        if revision is None or not self._revision_integrity_valid(normalized, revision):
            return self._error("PERIOD_PROFIT_MAPPING_REVISION_NOT_SAFE")
        scope_state["active_revision_id"] = revision_id
        self._append_event(scope_state, "ACTIVATE", revision_id, actor)
        self._write_registry(registry)
        return self._activation_result(normalized, revision, "PERIOD_PROFIT_MAPPING_REVISION_ACTIVATED")

    def rollback(self, scope, target_revision_id, actor="USER"):
        normalized = str(scope or "").strip().upper()
        registry, health = self._read_registry()
        if health.get("writable") is not True:
            return self._health_error(health)
        scope_state = registry["scopes"].get(normalized)
        revision = self._find_revision(scope_state, target_revision_id)
        if revision is None or not self._revision_integrity_valid(normalized, revision):
            return self._error("PERIOD_PROFIT_MAPPING_REVISION_NOT_SAFE")
        previous = scope_state.get("active_revision_id")
        scope_state["active_revision_id"] = target_revision_id
        self._append_event(scope_state, "ROLLBACK", target_revision_id, actor, previous_revision_id=previous)
        self._write_registry(registry)
        result = self._activation_result(normalized, revision, "PERIOD_PROFIT_MAPPING_ROLLBACK_APPLIED")
        result["previous_revision_id"] = previous
        return result

    def load_active(self, scope):
        normalized = str(scope or "").strip().upper()
        registry, health = self._read_registry()
        if health.get("load_allowed") is not True:
            return None
        scope_state = registry["scopes"].get(normalized)
        if not scope_state or not scope_state.get("active_revision_id"):
            return None
        revision = self._find_revision(scope_state, scope_state["active_revision_id"])
        if revision is None or not self._revision_integrity_valid(normalized, revision):
            return None
        return deepcopy(revision.get("mapping"))

    def history(self, scope):
        normalized = str(scope or "").strip().upper()
        registry, health = self._read_registry()
        scope_state = registry["scopes"].get(normalized)
        if not isinstance(scope_state, dict):
            scope_state = {"active_revision_id": None, "revisions": [], "events": []}
        return {
            "error": False,
            "status": "PERIOD_PROFIT_MAPPING_HISTORY_READY",
            "scope": normalized,
            "active_revision_id": scope_state.get("active_revision_id"),
            "revisions": deepcopy(scope_state.get("revisions") or []),
            "events": deepcopy(scope_state.get("events") or []),
            "registry_health_status": health.get("health_status"),
            "read_only": True,
            "executed": False,
        }

    def health(self):
        registry, health = self._read_registry()
        scopes = {}
        for scope in sorted(SCOPES):
            state = registry["scopes"].get(scope)
            if not isinstance(state, dict):
                state = {}
            revisions = state.get("revisions") or []
            revisions = revisions if isinstance(revisions, list) else []
            active = state.get("active_revision_id")
            latest_row = revisions[-1] if revisions and isinstance(revisions[-1], dict) else {}
            latest = latest_row.get("revision_id")
            scopes[scope] = {
                "active_revision_id": active,
                "latest_revision_id": latest,
                "revision_count": len(revisions),
                "active_revision_stale": bool(active and latest and active != latest),
                "active_mapping_loadable": self.load_active(scope) is not None,
            }
        return {
            "error": health.get("health_status") == "CORRUPT",
            "status": "PERIOD_PROFIT_MAPPING_REGISTRY_HEALTH_READY",
            "health_status": health.get("health_status"),
            "schema_version": health.get("schema_version"),
            "load_allowed": health.get("load_allowed"),
            "writable": health.get("writable"),
            "issues": list(health.get("issues") or []),
            "scopes": scopes,
            "fail_closed": True,
            "ozon_mutation": False,
            "profit_adjustment_allowed": False,
            "executed": False,
        }

    def _validate_mapping(self, scope, mapping):
        if not isinstance(mapping, dict):
            return self._error("PERIOD_PROFIT_AUTHORIZED_MAPPING_REQUIRED")
        source = dict(mapping)
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
        integrity = verify_period_profit_mapping_integrity(scope, source)
        if not valid or not source.get("mapping_id") or integrity.get("integrity_valid") is not True:
            return self._error("PERIOD_PROFIT_AUTHORIZED_MAPPING_REQUIRED")
        return None

    def _read_registry(self):
        empty = {"schema_version": SCHEMA_VERSION, "scopes": {}}
        if not self.storage_path or not os.path.exists(self.storage_path):
            return empty, self._health("EMPTY", [], True, True, SCHEMA_VERSION)
        try:
            with open(self.storage_path, "r", encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, ValueError, TypeError) as exc:
            return empty, self._health("CORRUPT", [f"REGISTRY_READ_ERROR:{type(exc).__name__}"], False, False, None)

        issues = []
        if not isinstance(data, dict):
            issues.append("REGISTRY_ROOT_INVALID")
            return empty, self._health("CORRUPT", issues, False, False, None)
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            issues.append("REGISTRY_SCHEMA_VERSION_UNSUPPORTED")
        scopes = data.get("scopes")
        if not isinstance(scopes, dict):
            issues.append("REGISTRY_SCOPES_INVALID")
            scopes = {}
        normalized = {"schema_version": version, "scopes": scopes}
        issues.extend(self._validate_registry_structure(normalized))
        if issues:
            return normalized, self._health("CORRUPT", issues, False, False, version)
        return normalized, self._health("HEALTHY", [], True, True, version)

    def _validate_registry_structure(self, registry):
        issues = []
        for scope, state in registry.get("scopes", {}).items():
            if scope not in SCOPES or not isinstance(state, dict):
                issues.append(f"SCOPE_STATE_INVALID:{scope}")
                continue
            revisions = state.get("revisions")
            events = state.get("events")
            if not isinstance(revisions, list) or not isinstance(events, list):
                issues.append(f"SCOPE_COLLECTION_INVALID:{scope}")
                continue
            ids = []
            for index, revision in enumerate(revisions, start=1):
                if not isinstance(revision, dict):
                    issues.append(f"REVISION_INVALID:{scope}:{index}")
                    continue
                revision_id = revision.get("revision_id")
                ids.append(revision_id)
                if revision.get("scope") != scope or revision.get("revision_number") != index:
                    issues.append(f"REVISION_LINEAGE_INVALID:{scope}:{revision_id}")
                if revision.get("immutable_revision") is not True:
                    issues.append(f"REVISION_MUTABILITY_INVALID:{scope}:{revision_id}")
                if not self._revision_integrity_valid(scope, revision):
                    issues.append(f"REVISION_MAPPING_INTEGRITY_INVALID:{scope}:{revision_id}")
            if len(ids) != len(set(ids)):
                issues.append(f"REVISION_ID_DUPLICATE:{scope}")
            active = state.get("active_revision_id")
            if active is not None and active not in ids:
                issues.append(f"ACTIVE_REVISION_NOT_FOUND:{scope}")
        return issues

    def _revision_integrity_valid(self, scope, revision):
        if not isinstance(revision, dict):
            return False
        mapping = revision.get("mapping")
        if not isinstance(mapping, dict) or revision.get("mapping_id") != mapping.get("mapping_id"):
            return False
        return verify_period_profit_mapping_integrity(scope, mapping).get("integrity_valid") is True

    def _health(self, status, issues, load_allowed, writable, schema_version):
        return {
            "health_status": status,
            "issues": issues,
            "load_allowed": load_allowed,
            "writable": writable,
            "schema_version": schema_version,
        }

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

    def _health_error(self, health):
        result = self._error("PERIOD_PROFIT_MAPPING_REGISTRY_HEALTH_BLOCKED")
        result["registry_health_status"] = health.get("health_status")
        result["registry_issues"] = list(health.get("issues") or [])
        return result

    def _error(self, code):
        return {
            "error": True,
            "code": code,
            "status": "PERIOD_PROFIT_MAPPING_REGISTRY_UNAVAILABLE",
            "ozon_mutation": False,
            "profit_adjustment_allowed": False,
            "executed": False,
        }
