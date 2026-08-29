from copy import deepcopy


ALLOWED_EVIDENCE_FIELDS = {
    "sales_source_recorded_at",
    "sales_observed_at",
    "stock_source_recorded_at",
    "stock_observed_at",
    "unit_economics_source_recorded_at",
    "unit_economics_observed_at",
}


class ProductDecisionRecomputePreviewService:

    def __init__(self, decision_service):
        self.decision_service = decision_service

    def recompute_preview(self, authorization, product_metrics):
        source = dict(authorization or {})
        metrics = deepcopy(dict(product_metrics or {}))

        authorization_id = str(source.get("recompute_authorization_id") or "").strip()
        eligibility_id = str(source.get("recompute_eligibility_id") or "").strip()
        draft_id = str(source.get("draft_id") or "").strip()
        sku = str(source.get("sku") or "").strip()

        if not authorization_id or not eligibility_id or not draft_id or not sku:
            return self._blocked("RECOMPUTE_PREVIEW_CONTEXT_REQUIRED", source)
        if authorization_id != "recompute-review-authorization:" + eligibility_id:
            return self._blocked("RECOMPUTE_AUTHORIZATION_ID_MISMATCH", source)
        if source.get("status") != "PRODUCT_DECISION_RECOMPUTE_REVIEW_AUTHORIZED":
            return self._blocked("RECOMPUTE_AUTHORIZATION_STATUS_INVALID", source)
        if source.get("decision") != "AUTHORIZE":
            return self._blocked("RECOMPUTE_AUTHORIZATION_DECISION_MISMATCH", source)
        if source.get("recompute_authorized") is not True:
            return self._blocked("RECOMPUTE_NOT_AUTHORIZED", source)
        if source.get("recompute_rejected") is not False:
            return self._blocked("RECOMPUTE_AUTHORIZATION_REJECTED", source)
        if source.get("recompute_allowed") is not True or source.get("recompute_started") is not False:
            return self._blocked("RECOMPUTE_PREVIEW_AUTHORIZATION_BOUNDARY_VIOLATION", source)
        if (
            source.get("product_decision_recomputed") is not False
            or source.get("product_decision_mutated") is not False
            or source.get("ozon_mutation_called") is not False
            or source.get("execution_allowed") is not False
            or source.get("execution_ready") is not False
            or source.get("executed") is not False
        ):
            return self._blocked("RECOMPUTE_PREVIEW_SAFETY_BOUNDARY_VIOLATION", source)

        evidence = self._safe_evidence(source.get("authorization_evidence"))
        if not evidence:
            return self._blocked("RECOMPUTE_PREVIEW_EVIDENCE_REQUIRED", source)
        if evidence != source.get("authorization_evidence"):
            return self._blocked("RECOMPUTE_PREVIEW_EVIDENCE_UNSAFE", source)
        if source.get("authorization_evidence_count") != len(evidence):
            return self._blocked("RECOMPUTE_PREVIEW_EVIDENCE_COUNT_MISMATCH", source)

        metric_sku = str(metrics.get("sku") or "").strip()
        if not metric_sku or metric_sku != sku:
            return self._blocked("RECOMPUTE_PREVIEW_SKU_MISMATCH", source)

        try:
            preview_decision = self.decision_service.decide(deepcopy(metrics))
        except Exception:
            return self._blocked("RECOMPUTE_PREVIEW_CALCULATION_FAILED", source)

        if not isinstance(preview_decision, dict):
            return self._blocked("RECOMPUTE_PREVIEW_RESULT_INVALID", source)
        if str(preview_decision.get("sku") or "").strip() != sku:
            return self._blocked("RECOMPUTE_PREVIEW_RESULT_SKU_MISMATCH", source)

        return {
            "error": False,
            "status": "PRODUCT_DECISION_RECOMPUTE_PREVIEW_READY",
            "recompute_preview_id": "product-decision-recompute-preview:" + authorization_id,
            "recompute_authorization_id": authorization_id,
            "recompute_eligibility_id": eligibility_id,
            "draft_id": draft_id,
            "sku": sku,
            "recompute_allowed": True,
            "recompute_started": True,
            "recompute_preview_computed": True,
            "preview_decision": deepcopy(preview_decision),
            "authorization_evidence": deepcopy(evidence),
            "authorization_evidence_count": len(evidence),
            "persistent": False,
            "task_draft_mutated": False,
            "product_decision_recomputed": True,
            "product_decision_mutated": False,
            "product_decision_persisted": False,
            "ozon_mutation_called": False,
            "execution_allowed": False,
            "execution_ready": False,
            "executed": False,
        }

    @staticmethod
    def _safe_evidence(values):
        if not isinstance(values, dict):
            return {}
        return {
            field: deepcopy(value)
            for field, value in values.items()
            if field in ALLOWED_EVIDENCE_FIELDS and value not in (None, "")
        }

    @staticmethod
    def _blocked(code, source):
        return {
            "error": True,
            "code": code,
            "status": "PRODUCT_DECISION_RECOMPUTE_PREVIEW_BLOCKED",
            "recompute_preview_id": None,
            "recompute_authorization_id": source.get("recompute_authorization_id"),
            "recompute_eligibility_id": source.get("recompute_eligibility_id"),
            "draft_id": source.get("draft_id"),
            "sku": source.get("sku"),
            "recompute_allowed": False,
            "recompute_started": False,
            "recompute_preview_computed": False,
            "preview_decision": None,
            "authorization_evidence": {},
            "authorization_evidence_count": 0,
            "persistent": False,
            "task_draft_mutated": False,
            "product_decision_recomputed": False,
            "product_decision_mutated": False,
            "product_decision_persisted": False,
            "ozon_mutation_called": False,
            "execution_allowed": False,
            "execution_ready": False,
            "executed": False,
        }
