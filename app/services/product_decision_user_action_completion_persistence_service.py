from copy import deepcopy


class ProductDecisionUserActionCompletionPersistenceService:

    def __init__(self, storage_service):
        self.storage_service = storage_service

    def persist(self, evidence):
        source = deepcopy(dict(evidence or {}))
        evidence_id = str(source.get("user_action_completion_evidence_id") or "").strip()
        checklist_id = str(source.get("user_action_checklist_id") or "").strip()
        sku = str(source.get("sku") or "").strip()

        if not evidence_id or not checklist_id or not sku:
            return self._blocked("USER_ACTION_COMPLETION_PERSISTENCE_CONTEXT_REQUIRED", source)
        if source.get("status") not in {
            "PRODUCT_DECISION_USER_ACTION_COMPLETION_CONFIRMED",
            "PRODUCT_DECISION_USER_ACTION_COMPLETION_DECLINED",
        }:
            return self._blocked("USER_ACTION_COMPLETION_PERSISTENCE_STATUS_INVALID", source)
        if source.get("completion_evidence_source") != "USER_REPORT":
            return self._blocked("USER_ACTION_COMPLETION_PERSISTENCE_SOURCE_INVALID", source)
        if (
            source.get("externally_verified") is not False
            or source.get("persistent") is not False
            or source.get("checklist_mutated") is not False
            or source.get("ozon_mutation_called") is not False
            or source.get("execution_allowed") is not False
            or source.get("execution_ready") is not False
            or source.get("executed") is not False
        ):
            return self._blocked("USER_ACTION_COMPLETION_PERSISTENCE_SAFETY_BOUNDARY_VIOLATION", source)

        try:
            records = self.storage_service.load()
        except Exception:
            return self._blocked("USER_ACTION_COMPLETION_PERSISTENCE_READ_FAILED", source)
        if not isinstance(records, list):
            records = []

        existing = next((item for item in records if isinstance(item, dict) and item.get("user_action_completion_evidence_id") == evidence_id), None)
        if existing is not None:
            if existing != source:
                return self._blocked("USER_ACTION_COMPLETION_PERSISTENCE_ID_CONFLICT", source)
            return self._success(source, saved=False, record_count=len(records))

        records = [deepcopy(item) for item in records if isinstance(item, dict)]
        records.append(deepcopy(source))
        try:
            self.storage_service.save(records)
        except Exception:
            return self._blocked("USER_ACTION_COMPLETION_PERSISTENCE_WRITE_FAILED", source)
        return self._success(source, saved=True, record_count=len(records))

    @staticmethod
    def _success(source, saved, record_count):
        return {
            "error": False,
            "status": "PRODUCT_DECISION_USER_ACTION_COMPLETION_PERSISTED",
            "user_action_completion_evidence_id": source.get("user_action_completion_evidence_id"),
            "user_action_checklist_id": source.get("user_action_checklist_id"),
            "sku": source.get("sku"),
            "user_reported_completed": source.get("user_reported_completed") is True,
            "completion_evidence_source": "USER_REPORT",
            "completion_persisted": True,
            "saved": saved,
            "record_count": record_count,
            "externally_verified": False,
            "persistent": True,
            "checklist_mutated": False,
            "ozon_mutation_called": False,
            "execution_allowed": False,
            "execution_ready": False,
            "executed": False,
        }

    @staticmethod
    def _blocked(code, source):
        return {
            "error": True,
            "code": code,
            "status": "PRODUCT_DECISION_USER_ACTION_COMPLETION_PERSISTENCE_BLOCKED",
            "user_action_completion_evidence_id": source.get("user_action_completion_evidence_id"),
            "user_action_checklist_id": source.get("user_action_checklist_id"),
            "sku": source.get("sku"),
            "completion_persisted": False,
            "saved": False,
            "externally_verified": False,
            "persistent": False,
            "checklist_mutated": False,
            "ozon_mutation_called": False,
            "execution_allowed": False,
            "execution_ready": False,
            "executed": False,
        }
