from copy import deepcopy


GUIDANCE_BY_DECISION = {
    "REPLENISH_HIGH_PRIORITY": {
        "action_type": "REVIEW_REPLENISHMENT",
        "title": "Проверить пополнение запаса",
        "steps": [
            "Проверьте текущий остаток и скорость продаж товара.",
            "Определите подходящий объём пополнения вручную с учётом поставки и доступного капитала.",
            "Если решение подтверждено, выполните пополнение самостоятельно в кабинете продавца.",
        ],
    },
    "REPLENISH_NORMAL": {
        "action_type": "REVIEW_REPLENISHMENT",
        "title": "Рассмотреть пополнение запаса",
        "steps": [
            "Проверьте текущий остаток, скорость продаж и ожидаемый срок поставки.",
            "Определите необходимость и объём пополнения вручную.",
            "При необходимости выполните пополнение самостоятельно в кабинете продавца.",
        ],
    },
    "INVESTIGATE_LOW_PROFIT": {
        "action_type": "REVIEW_UNIT_ECONOMICS",
        "title": "Проверить юнит-экономику",
        "steps": [
            "Проверьте цену, себестоимость, комиссии, логистику, последнюю милю, эквайринг и налог.",
            "Определите, какой компонент сильнее всего снижает прибыль на единицу.",
            "Любое изменение цены или других бизнес-параметров выполните самостоятельно после проверки.",
        ],
    },
    "WATCH_LOW_MARGIN": {
        "action_type": "REVIEW_MARGIN",
        "title": "Проверить низкую маржу",
        "steps": [
            "Проверьте текущую маржу и её исходные компоненты.",
            "Оцените, требуется ли изменение цены, затрат или условий поставки.",
            "Примите и выполните бизнес-решение самостоятельно.",
        ],
    },
    "HOLD_STOCK": {
        "action_type": "MONITOR_ONLY",
        "title": "Продолжить наблюдение",
        "steps": [
            "Сохраните текущие условия без автоматических изменений.",
            "Следите за остатком, скоростью продаж, прибылью и маржой.",
            "Вернитесь к решению при изменении исходных показателей.",
        ],
    },
}


def build_product_decision_user_action_guidance(verification):
    source = deepcopy(dict(verification or {}))
    verification_id = str(source.get("decision_persistence_verification_id") or "").strip()
    application_id = str(source.get("decision_persistence_application_id") or "").strip()
    sku = str(source.get("sku") or "").strip()

    if not verification_id or not application_id or not sku:
        return _blocked("USER_ACTION_GUIDANCE_CONTEXT_REQUIRED", source)
    if verification_id != "product-decision-persistence-verification:" + application_id:
        return _blocked("USER_ACTION_GUIDANCE_VERIFICATION_ID_MISMATCH", source)
    if source.get("status") != "PRODUCT_DECISION_PERSISTENCE_VERIFIED":
        return _blocked("USER_ACTION_GUIDANCE_VERIFICATION_STATUS_INVALID", source)
    if source.get("decision_persistence_verified") is not True:
        return _blocked("USER_ACTION_GUIDANCE_VERIFICATION_REQUIRED", source)
    if (
        source.get("persistent") is not True
        or source.get("product_decision_persisted") is not True
        or source.get("product_decision_mutated") is not False
        or source.get("ozon_mutation_called") is not False
        or source.get("execution_allowed") is not False
        or source.get("execution_ready") is not False
        or source.get("executed") is not False
    ):
        return _blocked("USER_ACTION_GUIDANCE_SAFETY_BOUNDARY_VIOLATION", source)

    snapshot = source.get("verified_snapshot")
    if not isinstance(snapshot, dict):
        return _blocked("USER_ACTION_GUIDANCE_SNAPSHOT_REQUIRED", source)
    if str(snapshot.get("sku") or "").strip() != sku:
        return _blocked("USER_ACTION_GUIDANCE_SNAPSHOT_SKU_MISMATCH", source)

    decision_type = str(snapshot.get("decision_type") or "").strip()
    guidance = GUIDANCE_BY_DECISION.get(decision_type)
    if guidance is None:
        return _blocked("USER_ACTION_GUIDANCE_DECISION_UNSUPPORTED", source)

    return {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_GUIDANCE_READY",
        "user_action_guidance_id": "product-decision-user-action-guidance:" + verification_id,
        "decision_persistence_verification_id": verification_id,
        "decision_persistence_application_id": application_id,
        "sku": sku,
        "decision_type": decision_type,
        "priority": snapshot.get("priority"),
        "action_type": guidance["action_type"],
        "title": guidance["title"],
        "steps": list(guidance["steps"]),
        "reasons": list(snapshot.get("reasons") or []),
        "user_execution_required": True,
        "automatic_execution_prohibited": True,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }


def _blocked(code, source):
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_USER_ACTION_GUIDANCE_BLOCKED",
        "user_action_guidance_id": None,
        "decision_persistence_verification_id": source.get("decision_persistence_verification_id"),
        "decision_persistence_application_id": source.get("decision_persistence_application_id"),
        "sku": source.get("sku"),
        "decision_type": None,
        "priority": None,
        "action_type": None,
        "title": None,
        "steps": [],
        "reasons": [],
        "user_execution_required": True,
        "automatic_execution_prohibited": True,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
