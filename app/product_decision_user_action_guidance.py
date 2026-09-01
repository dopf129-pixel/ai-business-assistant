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

ALLOWED_PRIORITIES = {"CRITICAL", "HIGH", "NORMAL", "LOW", "NONE"}
ALLOWED_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}


def build_product_decision_user_action_guidance(verification):
    if not isinstance(verification, dict):
        return _blocked(
            "USER_ACTION_GUIDANCE_VERIFICATION_INPUT_INVALID",
            {},
        )

    source = deepcopy(verification)

    verification_id = _required_string(
        source.get("decision_persistence_verification_id")
    )
    application_id = _required_string(
        source.get("decision_persistence_application_id")
    )
    sku = _required_string(source.get("sku"))

    if not verification_id or not application_id or not sku:
        return _blocked("USER_ACTION_GUIDANCE_CONTEXT_REQUIRED", source)

    if (
        verification_id
        != "product-decision-persistence-verification:" + application_id
    ):
        return _blocked(
            "USER_ACTION_GUIDANCE_VERIFICATION_ID_MISMATCH",
            source,
        )

    if (
        source.get("error") is not False
        or source.get("status") != "PRODUCT_DECISION_PERSISTENCE_VERIFIED"
    ):
        return _blocked(
            "USER_ACTION_GUIDANCE_VERIFICATION_STATUS_INVALID",
            source,
        )

    if source.get("decision_persistence_verified") is not True:
        return _blocked(
            "USER_ACTION_GUIDANCE_VERIFICATION_REQUIRED",
            source,
        )

    mismatched_fields = source.get("mismatched_fields")
    if not isinstance(mismatched_fields, list) or mismatched_fields:
        return _blocked(
            "USER_ACTION_GUIDANCE_VERIFICATION_MISMATCH_EVIDENCE_INVALID",
            source,
        )

    if (
        source.get("externally_verified") is not False
        or source.get("persistent") is not True
        or source.get("product_decision_recomputed") is not True
        or source.get("product_decision_persisted") is not True
        or source.get("product_decision_mutated") is not False
        or source.get("ozon_mutation_called") is not False
        or source.get("execution_allowed") is not False
        or source.get("execution_ready") is not False
        or source.get("executed") is not False
    ):
        return _blocked(
            "USER_ACTION_GUIDANCE_SAFETY_BOUNDARY_VIOLATION",
            source,
        )

    snapshot = source.get("verified_snapshot")
    if not isinstance(snapshot, dict):
        return _blocked(
            "USER_ACTION_GUIDANCE_SNAPSHOT_REQUIRED",
            source,
        )

    snapshot_sku = _required_string(snapshot.get("sku"))
    if not snapshot_sku:
        return _blocked(
            "USER_ACTION_GUIDANCE_SNAPSHOT_INVALID",
            source,
        )
    if snapshot_sku != sku:
        return _blocked(
            "USER_ACTION_GUIDANCE_SNAPSHOT_SKU_MISMATCH",
            source,
        )

    verified_recorded_at = _required_string(
        source.get("verified_recorded_at")
    )
    snapshot_recorded_at = _required_string(snapshot.get("recorded_at"))
    if (
        not verified_recorded_at
        or not snapshot_recorded_at
        or verified_recorded_at != snapshot_recorded_at
    ):
        return _blocked(
            "USER_ACTION_GUIDANCE_VERIFIED_RECORDING_MISMATCH",
            source,
        )

    decision_type = _required_string(snapshot.get("decision_type"))
    priority = _required_string(snapshot.get("priority"))
    confidence = _required_string(snapshot.get("confidence"))
    reasons = snapshot.get("reasons")

    guidance = GUIDANCE_BY_DECISION.get(decision_type)
    if guidance is None:
        return _blocked(
            "USER_ACTION_GUIDANCE_DECISION_UNSUPPORTED",
            source,
        )

    if (
        priority not in ALLOWED_PRIORITIES
        or confidence not in ALLOWED_CONFIDENCE
        or not isinstance(reasons, list)
        or not reasons
        or any(_required_string(reason) is None for reason in reasons)
    ):
        return _blocked(
            "USER_ACTION_GUIDANCE_SNAPSHOT_INVALID",
            source,
        )

    return {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_GUIDANCE_READY",
        "user_action_guidance_id":
            "product-decision-user-action-guidance:" + verification_id,
        "decision_persistence_verification_id": verification_id,
        "decision_persistence_application_id": application_id,
        "sku": sku,
        "decision_type": decision_type,
        "priority": priority,
        "confidence": confidence,
        "action_type": guidance["action_type"],
        "title": guidance["title"],
        "steps": list(guidance["steps"]),
        "reasons": deepcopy(reasons),
        "verified_recorded_at": verified_recorded_at,
        "decision_persistence_verified": True,
        "externally_verified": False,
        "persistent": True,
        "user_execution_required": True,
        "automatic_execution_prohibited": True,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }


def _required_string(value):
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _blocked(code, source):
    safe_source = source if isinstance(source, dict) else {}
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_USER_ACTION_GUIDANCE_BLOCKED",
        "user_action_guidance_id": None,
        "decision_persistence_verification_id": safe_source.get(
            "decision_persistence_verification_id"
        ),
        "decision_persistence_application_id": safe_source.get(
            "decision_persistence_application_id"
        ),
        "sku": safe_source.get("sku"),
        "decision_type": None,
        "priority": None,
        "confidence": None,
        "action_type": None,
        "title": None,
        "steps": [],
        "reasons": [],
        "verified_recorded_at": None,
        "decision_persistence_verified": False,
        "externally_verified": False,
        "persistent": False,
        "user_execution_required": True,
        "automatic_execution_prohibited": True,
        "ozon_mutation_called": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
