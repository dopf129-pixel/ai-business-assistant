from copy import deepcopy


MIN_SAMPLE_BY_CONFIDENCE = {
    "NONE": 0,
    "LOW": 3,
    "MEDIUM": 10,
    "HIGH": 30,
}
QUALITY_SCORE = {
    "NO_EVIDENCE": 0,
    "VERY_LIMITED": 1,
    "LIMITED": 2,
    "DESCRIPTIVE_BASELINE": 3,
}
ALLOWED_OUTCOME_TYPES = {
    "DECISION_CHANGED",
    "SAME_DECISION_LOWER_PRIORITY",
    "SAME_DECISION_HIGHER_PRIORITY",
    "NO_DECISION_CHANGE",
}
ALLOWED_PRIORITY_CHANGES = {
    "PRIORITY_DECREASED",
    "PRIORITY_INCREASED",
    "PRIORITY_UNCHANGED",
}
OUTCOME_ID_PREFIX = "product-decision-user-action-post-decision-outcome:"


def build_product_decision_user_action_learning_confidence(quality):
    if not isinstance(quality, dict):
        return _blocked("LEARNING_CONFIDENCE_QUALITY_INPUT_INVALID")

    source = deepcopy(quality)

    if (
        source.get("error") is not False
        or source.get("status")
        != "PRODUCT_DECISION_USER_ACTION_LEARNING_EVIDENCE_QUALITY_READY"
    ):
        return _blocked("LEARNING_CONFIDENCE_QUALITY_STATUS_INVALID")

    if (
        source.get("completion_evidence_source") != "USER_REPORT"
        or source.get("quality_scope") != "DESCRIPTIVE_OBSERVATIONS_ONLY"
        or source.get("externally_verified") is not False
        or source.get("persistent") is not False
        or source.get("causal_inference_supported") is not False
        or source.get("decision_rule_update_allowed") is not False
        or source.get("automatic_execution_allowed") is not False
        or source.get("execution_allowed") is not False
        or source.get("execution_ready") is not False
        or source.get("executed") is not False
    ):
        return _blocked("LEARNING_CONFIDENCE_SAFETY_BOUNDARY_VIOLATION")

    observation_count = source.get("observation_count")
    sku_count = source.get("sku_count")
    quality_name = source.get("evidence_quality")
    quality_score = source.get("evidence_quality_score")

    if (
        type(observation_count) is not int
        or observation_count < 0
        or type(sku_count) is not int
        or sku_count < 0
        or sku_count > observation_count
    ):
        return _blocked("LEARNING_CONFIDENCE_COUNTS_INVALID")

    if (
        quality_name not in QUALITY_SCORE
        or type(quality_score) is not int
        or quality_score not in QUALITY_SCORE.values()
    ):
        return _blocked("LEARNING_CONFIDENCE_QUALITY_FIELDS_INVALID")

    outcome_counts = _validated_count_map(
        source.get("outcome_counts"),
        ALLOWED_OUTCOME_TYPES,
        allow_empty=observation_count == 0,
    )
    priority_change_counts = _validated_count_map(
        source.get("priority_change_counts"),
        ALLOWED_PRIORITY_CHANGES,
        allow_empty=observation_count == 0,
    )
    sku_observation_counts = _validated_sku_counts(
        source.get("sku_observation_counts"),
        allow_empty=observation_count == 0,
    )
    outcome_ids = _validated_outcome_ids(
        source.get("outcome_ids"),
        observation_count,
    )

    if (
        outcome_counts is None
        or priority_change_counts is None
        or sku_observation_counts is None
        or outcome_ids is None
    ):
        return _blocked("LEARNING_CONFIDENCE_AGGREGATES_INVALID")

    if (
        sum(outcome_counts.values()) != observation_count
        or sum(priority_change_counts.values()) != observation_count
        or sum(sku_observation_counts.values()) != observation_count
        or len(sku_observation_counts) != sku_count
    ):
        return _blocked("LEARNING_CONFIDENCE_AGGREGATES_MISMATCH")

    expected_quality, expected_score = _expected_quality(
        observation_count,
        sku_count,
    )
    if (
        quality_name != expected_quality
        or quality_score != expected_score
    ):
        return _blocked("LEARNING_CONFIDENCE_QUALITY_SAMPLE_MISMATCH")

    if observation_count < 3:
        confidence = "NONE"
    elif observation_count < 10 or sku_count < 2:
        confidence = "LOW"
    elif observation_count < 30 or sku_count < 3:
        confidence = "MEDIUM"
    else:
        confidence = "HIGH"

    return {
        "error": False,
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_CONFIDENCE_READY",
        "evidence_quality": quality_name,
        "evidence_quality_score": quality_score,
        "observation_count": observation_count,
        "sku_count": sku_count,
        "outcome_counts": deepcopy(outcome_counts),
        "priority_change_counts": deepcopy(priority_change_counts),
        "sku_observation_counts": deepcopy(sku_observation_counts),
        "outcome_ids": deepcopy(outcome_ids),
        "completion_evidence_source": "USER_REPORT",
        "descriptive_confidence": confidence,
        "minimum_sample_required": MIN_SAMPLE_BY_CONFIDENCE[confidence],
        "confidence_scope": "DESCRIPTIVE_PATTERN_CONFIDENCE_ONLY",
        "externally_verified": False,
        "persistent": False,
        "causal_inference_supported": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }


def _expected_quality(observation_count, sku_count):
    if observation_count == 0:
        return "NO_EVIDENCE", 0
    if observation_count < 3:
        return "VERY_LIMITED", 1
    if observation_count < 10 or sku_count < 2:
        return "LIMITED", 2
    return "DESCRIPTIVE_BASELINE", 3


def _validated_count_map(value, allowed_keys, allow_empty):
    if not isinstance(value, dict):
        return None
    if not value:
        return {} if allow_empty else None

    result = {}
    for key, count in value.items():
        if key not in allowed_keys or type(count) is not int or count <= 0:
            return None
        result[key] = count
    return result


def _validated_sku_counts(value, allow_empty):
    if not isinstance(value, dict):
        return None
    if not value:
        return {} if allow_empty else None

    result = {}
    for raw_sku, count in value.items():
        sku = _required_string(raw_sku)
        if (
            sku is None
            or sku != raw_sku
            or type(count) is not int
            or count <= 0
        ):
            return None
        result[sku] = count
    return result


def _validated_outcome_ids(value, observation_count):
    if not isinstance(value, list) or len(value) != observation_count:
        return None

    result = []
    for raw_outcome_id in value:
        outcome_id = _required_string(raw_outcome_id)
        if (
            outcome_id is None
            or outcome_id != raw_outcome_id
            or not outcome_id.startswith(OUTCOME_ID_PREFIX)
        ):
            return None
        result.append(outcome_id)

    if len(set(result)) != len(result):
        return None

    return result


def _required_string(value):
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _blocked(code):
    return {
        "error": True,
        "code": code,
        "status": "PRODUCT_DECISION_USER_ACTION_LEARNING_CONFIDENCE_BLOCKED",
        "evidence_quality": None,
        "evidence_quality_score": None,
        "observation_count": None,
        "sku_count": None,
        "outcome_counts": None,
        "priority_change_counts": None,
        "sku_observation_counts": None,
        "outcome_ids": None,
        "completion_evidence_source": "USER_REPORT",
        "descriptive_confidence": None,
        "minimum_sample_required": None,
        "confidence_scope": "DESCRIPTIVE_PATTERN_CONFIDENCE_ONLY",
        "externally_verified": False,
        "persistent": False,
        "causal_inference_supported": False,
        "decision_rule_update_allowed": False,
        "automatic_execution_allowed": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
