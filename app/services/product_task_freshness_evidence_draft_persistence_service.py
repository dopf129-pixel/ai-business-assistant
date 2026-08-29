from copy import deepcopy

from product_task_freshness_evidence_draft_application import (
    apply_freshness_evidence_to_draft,
)


class ProductTaskFreshnessEvidenceDraftPersistenceService:

    def __init__(self, storage_service):
        self.storage_service = storage_service

    def apply_and_persist(self, readiness):
        source = dict(readiness or {})
        draft_id = str(source.get("draft_id") or "").strip()
        sku = str(source.get("sku") or "").strip()
        if not draft_id or not sku:
            return self._blocked("DURABLE_DRAFT_CONTEXT_REQUIRED", source)

        records = self.storage_service.load()
        matches = [
            index for index, record in enumerate(records)
            if str(record.get("draft_id") or "") == draft_id
            and str(record.get("sku") or "") == sku
        ]
        if not matches:
            return self._blocked("DURABLE_DRAFT_NOT_FOUND", source)
        if len(matches) != 1:
            return self._blocked("DURABLE_DRAFT_AMBIGUOUS", source)

        index = matches[0]
        working_draft = deepcopy(records[index])
        result = apply_freshness_evidence_to_draft(working_draft, source)
        if result.get("error"):
            return {
                **result,
                "persisted": False,
                "storage_write_attempted": False,
            }

        if result.get("idempotent_noop"):
            return {
                **result,
                "status": "FRESHNESS_EVIDENCE_DRAFT_ALREADY_PERSISTED",
                "persisted": True,
                "storage_write_attempted": False,
            }

        records[index] = working_draft
        try:
            self.storage_service.save(records)
        except OSError:
            return self._blocked("DURABLE_DRAFT_WRITE_FAILED", source)

        return {
            **result,
            "status": "FRESHNESS_EVIDENCE_DRAFT_PERSISTED",
            "persisted": True,
            "storage_write_attempted": True,
            "product_decision_recomputed": False,
            "product_decision_mutated": False,
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
            "status": "FRESHNESS_EVIDENCE_DURABLE_PERSISTENCE_BLOCKED",
            "draft_id": source.get("draft_id"),
            "sku": source.get("sku"),
            "persisted": False,
            "storage_write_attempted": code == "DURABLE_DRAFT_WRITE_FAILED",
            "task_draft_mutated": False,
            "product_decision_recomputed": False,
            "product_decision_mutated": False,
            "ozon_mutation_called": False,
            "execution_allowed": False,
            "execution_ready": False,
            "executed": False,
        }
