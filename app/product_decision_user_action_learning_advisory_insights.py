from copy import deepcopy


def build_product_decision_user_action_learning_advisory_insights(summary, confidence):
    source = deepcopy(dict(summary or {}))
    conf = deepcopy(dict(confidence or {}))

    if source.get("status") != "PRODUCT_DECISION_USER_ACTION_LEARNING_SUMMARY_READY":
        return _blocked("LEARNING_ADVISORY_SUMMARY_STATUS_INVALID")
    if conf.get("status") != "PRODUCT_DECISION_USER_ACTION_LEARNING_CONFIDENCE_READY":
        return _blocked("LEARNING_ADVISORY_CONFIDENCE_STATUS_INVALID")
    if (
        source.get("causal_claim_allowed") is not False
        or source.get("decision_rule_update_allowed") is not False
        or source.get("automatic_execution_allowed") is not False
        or conf.get("causal_inference_supported") is not False
        or conf.get("decision_rule_update_allowed") is not False
        or conf.get("automatic_execution_allowed") is not False
        or source.get("executed") is not False
        or conf.get("executed") is not False
    ):
        return _blocked("LEARNING_ADVISORY_SAFETY_BOUNDARY_VIOLATION")

    observation_count = int(source.get("observation_count") or 0)
    confidence_level = conf.get("descriptive_confidence") or "NONE"
    outcome_counts = dict(source.get("outcome_counts") or {})
    priority_counts = dict(source.get("priority_change_counts") or {})

    insights = []
    if observation_count == 0:
        insights.append("Недостаточно наблюдений для описательных выводов.")
    else:
        changed = int(outcome_counts.get("DECISION_CHANGED") or 0)
        unchanged = int(outcome_counts.get("NO_DECISION_CHANGE") or 0)
        decreased = int(priority_counts.get("PRIORITY_DECREASED") or 0)
        increased = int(priority_counts.get("PRIORITY_INCREASED") or 0)
        if changed:
            insights.append(f"После пользовательских отчётов наблюдалось изменений решений: {changed}.")
        if unchanged:
            insights.append(f"Без изменения решения наблюдалось случаев: {unchanged}.")
        if decreased:
            insights.append(f"Снижение приоритета наблюдалось случаев: {decreased}.")
        if increased:
            insights.append(f"Повышение приоритета наблюдалось случаев: {increased}.")
        if not insights:
            insights.append("Наблюдения есть, но выраженного описательного паттерна пока не выделено.")

    return {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_ADVISORY_READY",
        "observation_count": observation_count,
        "descriptive_confidence": confidence_level,
        "insights": insights,
        "advisory_only": True,
        "causal_claim_allowed": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }


def _blocked(code):
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_ADVISORY_BLOCKED",
        "insights": [],
        "advisory_only": True,
        "causal_claim_allowed": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "executed": False,
    }
