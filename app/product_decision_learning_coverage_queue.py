from copy import deepcopy


COVERAGE_RANK = {
    "NEEDS_USER_FEEDBACK": 1,
    "NO_DECISION_HISTORY": 2,
    "WAITING_FOR_LATER_OBSERVATION": 3,
}

VALID_FEEDBACK = {None, "USEFUL", "NOT_RELEVANT"}
VALID_OUTCOMES = {
    None,
    "PRIORITY_DECREASED",
    "PRIORITY_INCREASED",
    "DECISION_CHANGED",
}


def build_product_decision_learning_coverage_queue(items):
    rows = [
        deepcopy(dict(item))
        for item in (items or [])
        if isinstance(item, dict)
    ]
    if len(rows) != len(items or []):
        return _blocked("LEARNING_COVERAGE_ITEMS_INVALID")

    seen = set()
    queue = []
    for row in rows:
        sku = str(row.get("sku") or "").strip()
        history = row.get("history")
        if not sku or sku in seen or not isinstance(history, list):
            return _blocked("LEARNING_COVERAGE_CONTEXT_INVALID")
        seen.add(sku)

        records = []
        for record in history:
            if not isinstance(record, dict):
                return _blocked("LEARNING_COVERAGE_HISTORY_INVALID")
            current = deepcopy(record)
            if str(current.get("sku") or "").strip() != sku:
                return _blocked("LEARNING_COVERAGE_HISTORY_SKU_MISMATCH")
            feedback = current.get("feedback")
            outcome = current.get("outcome")
            if feedback not in VALID_FEEDBACK:
                return _blocked("LEARNING_COVERAGE_FEEDBACK_INVALID")
            if outcome not in VALID_OUTCOMES:
                return _blocked("LEARNING_COVERAGE_OUTCOME_INVALID")
            records.append(current)

        if not records:
            coverage_state = "NO_DECISION_HISTORY"
            reason_codes = ["NO_PERSISTED_DECISION_HISTORY"]
            current_feedback = None
            current_decision_type = None
            historical_outcome_count = 0
        else:
            latest = records[0]
            current_feedback = latest.get("feedback")
            current_decision_type = latest.get("decision_type")
            historical_outcome_count = sum(
                record.get("outcome") in VALID_OUTCOMES - {None}
                for record in records
            )

            if current_feedback is None:
                coverage_state = "NEEDS_USER_FEEDBACK"
                reason_codes = ["LATEST_DECISION_FEEDBACK_MISSING"]
            else:
                coverage_state = "WAITING_FOR_LATER_OBSERVATION"
                reason_codes = [
                    "LATEST_DECISION_FEEDBACK_RECORDED",
                    "FUTURE_DECISION_OBSERVATION_NOT_YET_AVAILABLE",
                ]

        queue.append({
            "sku": sku,
            "coverage_state": coverage_state,
            "learning_attention_rank": COVERAGE_RANK[coverage_state],
            "reason_codes": reason_codes,
            "history_count": len(records),
            "current_feedback": current_feedback,
            "current_decision_type": current_decision_type,
            "historical_outcome_count": historical_outcome_count,
            "business_priority_claimed": False,
            "causal_claim_allowed": False,
            "success_rate_claim_allowed": False,
            "profitability_claim_allowed": False,
            "decision_rule_update_allowed": False,
            "automatic_execution_allowed": False,
            "executed": False,
        })

    queue.sort(
        key=lambda item: (
            item["learning_attention_rank"],
            item["sku"],
        )
    )
    counts = {
        state: sum(
            item["coverage_state"] == state
            for item in queue
        )
        for state in COVERAGE_RANK
    }

    return {
        "error": False,
        "status": "PRODUCT_DECISION_LEARNING_COVERAGE_QUEUE_READY",
        "total": len(queue),
        "counts": counts,
        "items": queue,
        "evidence_scope": "PERSISTED_DECISION_HISTORY_COVERAGE_ONLY",
        "business_priority_claimed": False,
        "causal_claim_allowed": False,
        "success_rate_claim_allowed": False,
        "profitability_claim_allowed": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }


def _blocked(code):
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_LEARNING_COVERAGE_QUEUE_BLOCKED",
        "total": 0,
        "counts": {
            "NEEDS_USER_FEEDBACK": 0,
            "NO_DECISION_HISTORY": 0,
            "WAITING_FOR_LATER_OBSERVATION": 0,
        },
        "items": [],
        "evidence_scope": "PERSISTED_DECISION_HISTORY_COVERAGE_ONLY",
        "business_priority_claimed": False,
        "causal_claim_allowed": False,
        "success_rate_claim_allowed": False,
        "profitability_claim_allowed": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }
