"""Application service for explicit, local seller-price planning documents."""

from copy import deepcopy
from uuid import uuid4

from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id


class SavedPlanningPlanService:
    MANUAL_OVERRIDE_FIELDS = frozenset({
        "price", "cost", "advertising_rate", "discount_points_rate",
        "logistics_per_unit", "last_mile_per_unit", "acquiring_per_unit",
        "commission_rate",
    })
    MANUAL_PROVENANCE = frozenset({
        "manual", "manual_seller_assumption", "manual_unit_economics_input",
    })

    def __init__(self, repository, scenario_service=None):
        self.repository = repository
        self.scenario_service = scenario_service

    def save_capture(self, title, capture, *, idempotency_key=None,
                     document_id=None, expected_revision=None):
        scope = self._scope()
        if scope is None or not isinstance(capture, dict) or capture.get("error") is not False:
            return self._error("PLANNING_CAPTURE_STALE")
        if capture.get("tenant_scope") != scope["tenant_scope"]:
            return self._error("PLANNING_CAPTURE_STALE")
        payload = capture.get("payload")
        if not isinstance(payload, dict):
            return self._error("PLANNING_CAPTURE_INVALID")
        result = self.repository.save_document(
            title=title,
            payload=payload,
            owner_id=scope["owner_id"],
            store_id=scope["store_id"],
            document_id=document_id,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key or uuid4().hex,
        )
        if result.get("error") is True:
            return result
        return {
            **result,
            "status": "PLANNING_DOCUMENT_SAVED",
            "message": "План сохранён локально. Данные Ozon, себестоимость и настройки магазина не изменялись.",
            "read_only": True,
            "executed": False,
        }

    def list_documents(self, *, include_archived=False, limit=10, offset=0):
        scope = self._scope()
        if scope is None:
            return self._error("PLANNING_TENANT_SCOPE_MISMATCH")
        return self.repository.list_documents(
            owner_id=scope["owner_id"], store_id=scope["store_id"],
            include_archived=include_archived, limit=limit, offset=offset,
        )

    def get_document(self, document_id, *, revision=None):
        scope = self._scope()
        if scope is None:
            return self._error("PLANNING_TENANT_SCOPE_MISMATCH")
        result = self.repository.get_document(
            document_id, revision=revision,
            owner_id=scope["owner_id"], store_id=scope["store_id"],
        )
        if result.get("error") is True:
            return result
        document = result["document"]
        payload = document["payload"]
        if payload.get("calculation_version") == getattr(self.scenario_service, "VERSION", None):
            document["historical_calculation_status"] = "SAME_CALCULATION_VERSION"
        else:
            document["historical_calculation_status"] = "HISTORICAL_VERSION_UNAVAILABLE"
        document["source_freshness"] = "HISTORICAL_ASSUMPTIONS"
        document["recalculated_on_read"] = False
        return result

    def list_revisions(self, document_id):
        scope = self._scope()
        if scope is None:
            return self._error("PLANNING_TENANT_SCOPE_MISMATCH")
        return self.repository.list_revisions(
            document_id, owner_id=scope["owner_id"], store_id=scope["store_id"],
        )

    def copy_document(self, document_id, *, title, idempotency_key=None, revision=None):
        current = self.get_document(document_id, revision=revision)
        if current.get("error") is True:
            return current
        return self.repository.save_document(
            title=title,
            payload=deepcopy(current["document"]["payload"]),
            owner_id=current["document"]["owner_id"],
            store_id=current["document"]["store_id"],
            idempotency_key=idempotency_key or uuid4().hex,
        )

    def capture_refreshed_copy(self, old_payload, fresh_capture):
        """Carry only explicitly manual values over an exact-identity refresh."""
        if not isinstance(old_payload, dict) or not isinstance(fresh_capture, dict):
            return self._error("PLANNING_CAPTURE_INVALID")
        if fresh_capture.get("error") is not False or not isinstance(fresh_capture.get("payload"), dict):
            return self._error("PLANNING_CAPTURE_STALE")
        scope = self._scope()
        if scope is None or fresh_capture.get("tenant_scope") != scope["tenant_scope"]:
            return self._error("PLANNING_CAPTURE_STALE")
        old_by_identity = {
            self._identity_key(item.get("identity")): item
            for item in old_payload.get("items", []) if isinstance(item, dict)
        }
        fresh_payload = deepcopy(fresh_capture["payload"])
        for item in fresh_payload.get("items", []):
            old = old_by_identity.get(self._identity_key(item.get("identity")))
            if old is None:
                continue
            old_inputs = old.get("inputs") or {}
            old_provenance = old.get("provenance") or {}
            for field in self.MANUAL_OVERRIDE_FIELDS:
                if (
                    field in old_inputs
                    and old_inputs.get(field) is not None
                    and old_provenance.get(field) in self.MANUAL_PROVENANCE
                ):
                    item.setdefault("inputs", {})[field] = old_inputs[field]
                    item.setdefault("provenance", {})[field] = "manual_seller_assumption"
        fresh_payload["sales_mix"] = None
        fresh_capture = deepcopy(fresh_capture)
        fresh_capture["payload"] = fresh_payload
        return fresh_capture

    def save_sales_mix_revision(self, document_id, sales_mix, *, expected_revision, idempotency_key=None):
        """Append a user-confirmed sales-mix projection by revision CAS."""
        scope = self._scope()
        if scope is None:
            return self._error("PLANNING_TENANT_SCOPE_MISMATCH")
        current = self.get_document(document_id)
        if current.get("error") is True:
            return current
        document = current.get("document") or {}
        if (document.get("owner_id") != scope["owner_id"]
                or document.get("store_id") != scope["store_id"]
                or document.get("current_revision") != expected_revision
                or document.get("status") != "ACTIVE"):
            return self._error("PLANNING_DOCUMENT_REVISION_CONFLICT")
        payload = deepcopy(document.get("payload") or {})
        payload["sales_mix"] = deepcopy(sales_mix)
        result = self.repository.save_document(
            title=document.get("title"), payload=payload,
            owner_id=scope["owner_id"], store_id=scope["store_id"],
            document_id=document_id, expected_revision=expected_revision,
            idempotency_key=idempotency_key or uuid4().hex,
        )
        if result.get("error") is True:
            return result
        return {
            **result,
            "status": "PLANNING_SALES_MIX_SAVED",
            "message": "Объём продаж и дополнительные расходы сохранены отдельной ревизией плана. Факты магазина не изменены.",
            "local_write": True,
            "read_only": True,
            "executed": False,
        }

    def rename(self, document_id, title, *, expected_revision, idempotency_key=None):
        return self._repo_mutation("rename_document", document_id, title,
                                   expected_revision=expected_revision,
                                   idempotency_key=idempotency_key)

    def archive(self, document_id, *, expected_revision, idempotency_key=None):
        return self._repo_mutation("set_archived", document_id, True,
                                   expected_revision=expected_revision,
                                   idempotency_key=idempotency_key)

    def restore(self, document_id, *, expected_revision, idempotency_key=None):
        return self._repo_mutation("set_archived", document_id, False,
                                   expected_revision=expected_revision,
                                   idempotency_key=idempotency_key)

    def delete(self, document_id, *, expected_revision, confirmed, idempotency_key=None):
        return self._repo_mutation("delete_document", document_id,
                                   expected_revision=expected_revision,
                                   confirmed=confirmed, idempotency_key=idempotency_key)

    def _repo_mutation(self, method_name, document_id, *args, expected_revision,
                       idempotency_key=None, **kwargs):
        scope = self._scope()
        if scope is None:
            return self._error("PLANNING_TENANT_SCOPE_MISMATCH")
        method = getattr(self.repository, method_name, None)
        if not callable(method):
            return self._error("PLANNING_OPERATION_UNAVAILABLE")
        return method(
            document_id, *args, expected_revision=expected_revision,
            idempotency_key=idempotency_key or uuid4().hex,
            owner_id=scope["owner_id"], store_id=scope["store_id"], **kwargs,
        )

    @staticmethod
    def _identity_key(identity):
        if not isinstance(identity, dict):
            return None
        return tuple(str(identity.get(key) or "") for key in ("product_id", "offer_id", "sku", "store_id"))

    @staticmethod
    def _scope():
        tenant_scope = str(get_current_tenant_user_id() or "").strip()
        owner_id, store_id = split_store_tenant_scope(tenant_scope)
        if not owner_id or not tenant_scope:
            return None
        return {
            "owner_id": owner_id, "store_id": str(store_id or ""),
            "tenant_scope": tenant_scope,
        }

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "read_only": True, "executed": False}
