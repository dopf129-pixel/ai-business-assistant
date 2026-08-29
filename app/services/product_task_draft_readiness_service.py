from copy import deepcopy


class ProductTaskDraftReadinessService:

    REVIEW_FIELDS = {
        "REVIEW_REPLENISHMENT": (
            "current_stock",
            "sales_velocity",
            "days_of_stock",
        ),
        "REVIEW_UNIT_ECONOMICS": (
            "profit_per_unit",
            "margin_percent",
            "economics_basis",
        ),
        "REVIEW_MARGIN": (
            "profit_per_unit",
            "margin_percent",
        ),
    }
    EXECUTION_POLICY_BLOCKERS = {
        "REVIEW_REPLENISHMENT": (
            "REPLENISHMENT_QUANTITY_POLICY_MISSING",
            "SUPPLIER_LEAD_TIME_MISSING",
        ),
        "REVIEW_UNIT_ECONOMICS": (
            "ACTION_POLICY_NOT_DEFINED",
        ),
        "REVIEW_MARGIN": (
            "PRICE_CHANGE_POLICY_MISSING",
            "TARGET_MARGIN_POLICY_MISSING",
        ),
    }
    FRESHNESS_EVIDENCE_FIELDS = {
        "sales": (
            "sales_source_recorded_at",
            "sales_observed_at",
        ),
        "stock": (
            "stock_source_recorded_at",
            "stock_observed_at",
        ),
        "unit_economics": (
            "unit_economics_source_recorded_at",
            "unit_economics_observed_at",
        ),
    }

    def __init__(self, freshness_service=None):
        self.freshness_service = freshness_service

    def evaluate(self, draft):
        source = deepcopy(draft or {})
        proposal_type = str(source.get("proposal_type") or "").upper()
        required_fields = self.REVIEW_FIELDS.get(proposal_type, ())
        checks = [
            {
                "field": field,
                "available": source.get(field) is not None,
            }
            for field in required_fields
        ]
        missing_fields = [
            check["field"] for check in checks if not check["available"]
        ]
        lifecycle_current = source.get("status") == "DRAFT"
        proposal_supported = proposal_type in self.REVIEW_FIELDS
        freshness = (
            self.freshness_service.evaluate(source)
            if self.freshness_service is not None
            else None
        )
        freshness_coverage = self._freshness_coverage(source, freshness)
        freshness_refresh_guidance = self._freshness_refresh_guidance(
            freshness,
            freshness_coverage,
        )
        freshness_ready = (
            freshness is None or freshness.get("status") == "FRESH"
        )
        review_ready = (
            lifecycle_current
            and proposal_supported
            and not missing_fields
            and freshness_ready
        )
        review_blockers = []
        if not lifecycle_current:
            review_blockers.append("DRAFT_NOT_CURRENT")
        if not proposal_supported:
            review_blockers.append("PROPOSAL_NOT_SUPPORTED")
        if missing_fields:
            review_blockers.append("REQUIRED_DATA_MISSING")
        if freshness is not None and not freshness_ready:
            review_blockers.append("SOURCE_DATA_NOT_FRESH")

        execution_blockers = ["EXECUTION_WORKFLOW_NOT_CONNECTED"]
        execution_blockers.extend(
            self.EXECUTION_POLICY_BLOCKERS.get(proposal_type, ())
        )
        return {
            "error": False,
            "draft_id": source.get("draft_id"),
            "review_status": (
                "READY_FOR_REVIEW"
                if review_ready
                else "NEEDS_DATA_OR_REFRESH"
            ),
            "review_ready": review_ready,
            "required_checks": checks,
            "missing_fields": missing_fields,
            "review_blockers": review_blockers,
            "freshness": freshness,
            "freshness_coverage": freshness_coverage,
            "freshness_refresh_guidance": freshness_refresh_guidance,
            "execution_ready": False,
            "execution_blockers": execution_blockers,
            "executed": False,
        }

    def build_refresh_request(self, draft):
        source = deepcopy(draft or {})
        readiness = self.evaluate(source)
        guidance = readiness.get("freshness_refresh_guidance") or {}
        targets = deepcopy(guidance.get("targets") or [])
        required = bool(targets)
        request_id = None
        if required:
            request_id = "refresh:" + str(source.get("draft_id") or "unknown")

        return {
            "error": False,
            "request_id": request_id,
            "draft_id": source.get("draft_id"),
            "sku": source.get("sku"),
            "proposal_type": source.get("proposal_type"),
            "status": "REQUEST_DRAFT" if required else "NOT_REQUIRED",
            "required": required,
            "targets": targets,
            "target_count": len(targets),
            "source_decision_recorded_at": source.get("decision_recorded_at"),
            "persistent": False,
            "refresh_started": False,
            "execution_allowed": False,
            "execution_ready": False,
            "executed": False,
        }

    def summarize(self, drafts):
        items = []
        counts = {
            "READY_FOR_REVIEW": 0,
            "NEEDS_DATA_OR_REFRESH": 0,
        }
        freshness_counts = {"FRESH": 0, "STALE": 0, "UNKNOWN": 0}
        freshness_coverage_counts = {
            "SOURCE_PROVEN": 0,
            "OBSERVED_ONLY": 0,
            "NO_EVIDENCE": 0,
        }
        freshness_refresh_counts = {
            "SOURCE_TIMESTAMP_REQUIRED": 0,
            "VERIFY_SOURCE_TIMESTAMP": 0,
            "REFRESH_SOURCE_DATA": 0,
        }
        freshness_source_timestamp_counts = {
            "VERIFIED": 0,
            "UNVERIFIED": 0,
            "ABSENT": 0,
        }
        for draft in drafts or []:
            item = deepcopy(draft)
            readiness = self.evaluate(item)
            item["readiness"] = readiness
            counts[readiness["review_status"]] += 1
            freshness = readiness.get("freshness")
            if freshness and freshness.get("status") in freshness_counts:
                freshness_counts[freshness["status"]] += 1
            coverage = readiness.get("freshness_coverage") or {}
            for state, value in (coverage.get("counts") or {}).items():
                if state in freshness_coverage_counts:
                    freshness_coverage_counts[state] += int(value or 0)
            for state, value in (
                coverage.get("source_timestamp_counts") or {}
            ).items():
                if state in freshness_source_timestamp_counts:
                    freshness_source_timestamp_counts[state] += int(
                        value or 0
                    )
            guidance = readiness.get("freshness_refresh_guidance") or {}
            for action, value in (guidance.get("counts") or {}).items():
                if action in freshness_refresh_counts:
                    freshness_refresh_counts[action] += int(value or 0)
            items.append(item)
        return {
            "error": False,
            "counts": counts,
            "freshness_counts": freshness_counts,
            "freshness_coverage_counts": freshness_coverage_counts,
            "freshness_source_timestamp_counts": (
                freshness_source_timestamp_counts
            ),
            "freshness_refresh_counts": freshness_refresh_counts,
            "items": items,
            "execution_ready_count": 0,
            "executed_count": 0,
        }

    def _freshness_coverage(self, source, freshness):
        if not isinstance(freshness, dict):
            return None

        components = {}
        counts = {
            "SOURCE_PROVEN": 0,
            "OBSERVED_ONLY": 0,
            "NO_EVIDENCE": 0,
        }
        source_timestamp_counts = {
            "VERIFIED": 0,
            "UNVERIFIED": 0,
            "ABSENT": 0,
        }
        freshness_components = freshness.get("components") or {}

        for component_name, component_freshness in freshness_components.items():
            fields = self.FRESHNESS_EVIDENCE_FIELDS.get(component_name)
            if fields is None:
                continue

            source_field, observed_field = fields
            source_value = source.get(source_field)
            observed_value = source.get(observed_field)
            source_present = source_value not in (None, "")
            observed_present = observed_value not in (None, "")

            if source_present:
                evidence_state = "SOURCE_PROVEN"
            elif observed_present:
                evidence_state = "OBSERVED_ONLY"
            else:
                evidence_state = "NO_EVIDENCE"

            freshness_status = component_freshness.get("status")
            if source_present and freshness_status in {"FRESH", "STALE"}:
                source_timestamp_state = "VERIFIED"
            elif source_present:
                source_timestamp_state = "UNVERIFIED"
            else:
                source_timestamp_state = "ABSENT"

            counts[evidence_state] += 1
            source_timestamp_counts[source_timestamp_state] += 1
            components[component_name] = {
                "freshness_status": freshness_status,
                "evidence_state": evidence_state,
                "source_timestamp_state": source_timestamp_state,
                "source_recorded_at": source_value,
                "observed_at": observed_value,
            }

        return {
            "components": components,
            "counts": counts,
            "source_timestamp_counts": source_timestamp_counts,
            "source_proven_count": counts["SOURCE_PROVEN"],
            "observed_only_count": counts["OBSERVED_ONLY"],
            "no_evidence_count": counts["NO_EVIDENCE"],
            "source_timestamp_verified_count": (
                source_timestamp_counts["VERIFIED"]
            ),
            "source_timestamp_unverified_count": (
                source_timestamp_counts["UNVERIFIED"]
            ),
            "source_timestamp_absent_count": (
                source_timestamp_counts["ABSENT"]
            ),
        }

    def _freshness_refresh_guidance(self, freshness, coverage):
        if not isinstance(freshness, dict) or not isinstance(coverage, dict):
            return None

        targets = []
        counts = {
            "SOURCE_TIMESTAMP_REQUIRED": 0,
            "VERIFY_SOURCE_TIMESTAMP": 0,
            "REFRESH_SOURCE_DATA": 0,
        }
        freshness_components = freshness.get("components") or {}
        coverage_components = coverage.get("components") or {}

        for component_name, component_freshness in freshness_components.items():
            status = component_freshness.get("status")
            if status == "FRESH":
                continue

            coverage_component = (
                coverage_components.get(component_name) or {}
            )
            evidence_state = coverage_component.get("evidence_state")
            source_timestamp_state = coverage_component.get(
                "source_timestamp_state"
            )

            if status == "STALE":
                action = "REFRESH_SOURCE_DATA"
            elif source_timestamp_state == "UNVERIFIED":
                action = "VERIFY_SOURCE_TIMESTAMP"
            else:
                action = "SOURCE_TIMESTAMP_REQUIRED"

            counts[action] += 1
            targets.append({
                "component": component_name,
                "action": action,
                "freshness_status": status,
                "evidence_state": evidence_state,
                "source_timestamp_state": source_timestamp_state,
                "reasons": list(component_freshness.get("reasons") or []),
            })

        return {
            "required": bool(targets),
            "targets": targets,
            "counts": counts,
            "execution_ready": False,
            "executed": False,
        }
