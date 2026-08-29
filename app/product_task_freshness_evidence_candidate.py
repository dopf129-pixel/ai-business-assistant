from copy import deepcopy


EVIDENCE_FIELDS = {
    "sales": {
        "source": "sales_source_recorded_at",
        "observed": "sales_observed_at",
    },
    "stock": {
        "source": "stock_source_recorded_at",
        "observed": "stock_observed_at",
    },
    "unit_economics": {
        "source": "unit_economics_source_recorded_at",
        "observed": "unit_economics_observed_at",
        "observed_alias": "as_of",
    },
}


def build_freshness_evidence_candidate(refresh_result):
    refresh = deepcopy(refresh_result or {})
    candidates = []

    for item in refresh.get("results") or []:
        component = str(item.get("component") or "").strip()
        fields = EVIDENCE_FIELDS.get(component)
        data = item.get("data")
        if fields is None or not isinstance(data, dict):
            continue

        source_field = fields["source"]
        observed_field = fields["observed"]
        source_value = data.get(source_field)
        observed_value = data.get(observed_field)

        if observed_value in (None, "") and fields.get("observed_alias"):
            observed_value = data.get(fields["observed_alias"])

        update = {}
        if source_value not in (None, ""):
            update[source_field] = source_value
        if observed_value not in (None, ""):
            update[observed_field] = observed_value

        candidates.append({
            "component": component,
            "provider": item.get("provider"),
            "method": item.get("method"),
            "evidence": update,
            "source_evidence_present": source_field in update,
            "observation_evidence_present": observed_field in update,
            "cache_metadata_ignored": bool(
                isinstance(data.get("cache"), dict)
                and data.get("cache", {}).get("cached_at")
            ),
            "source_freshness_proven": source_field in update,
        })

    evidence_update = {}
    for candidate in candidates:
        evidence_update.update(candidate["evidence"])

    source_evidence_count = sum(
        1 for item in candidates if item["source_evidence_present"]
    )
    observation_evidence_count = sum(
        1 for item in candidates if item["observation_evidence_present"]
    )

    return {
        "error": False,
        "request_id": refresh.get("request_id"),
        "draft_id": refresh.get("draft_id"),
        "sku": refresh.get("sku"),
        "status": "CANDIDATE_READY" if evidence_update else "NO_EVIDENCE_CANDIDATE",
        "candidates": candidates,
        "candidate_count": len(candidates),
        "evidence_update": evidence_update,
        "source_evidence_count": source_evidence_count,
        "observation_evidence_count": observation_evidence_count,
        "source_freshness_proven": source_evidence_count > 0,
        "persistent": False,
        "product_decision_recomputed": False,
        "product_decision_mutated": False,
        "task_draft_mutated": False,
        "execution_allowed": False,
        "execution_ready": False,
        "executed": False,
    }
