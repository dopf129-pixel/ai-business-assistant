from datetime import datetime, timezone


SCOPES = ("RETURN", "ADVERTISING", "STORAGE")


class PeriodProfitMappingQualityService:
    """Read-only quality diagnostics for active mappings against the current Ozon catalog."""

    def __init__(self, registry_service, catalog_service, clock=None, stale_after_days=90):
        self.registry_service = registry_service
        self.catalog_service = catalog_service
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.stale_after_days = int(stale_after_days)

    def report(self):
        health = self.registry_service.health()
        catalog = self.catalog_service.load()
        catalog_ready = (
            isinstance(catalog, dict)
            and catalog.get("status") == "RETURN_FINANCIAL_OPERATION_CATALOG_READY"
            and catalog.get("error") is False
        )
        catalog_by_id = {}
        if catalog_ready:
            for row in catalog.get("operations") or []:
                if isinstance(row, dict) and row.get("type_id") is not None:
                    catalog_by_id[int(row.get("type_id"))] = dict(row)

        scopes = {}
        review_required_scopes = []
        quality_scores = []
        for scope in SCOPES:
            result = self._scope_quality(scope, catalog_by_id, catalog_ready)
            scopes[scope] = result
            if result.get("review_required") is True:
                review_required_scopes.append(scope)
            if result.get("quality_score") is not None:
                quality_scores.append(int(result.get("quality_score")))

        overall_score = round(sum(quality_scores) / len(quality_scores)) if quality_scores else None
        return {
            "error": False,
            "status": "PERIOD_PROFIT_MAPPING_QUALITY_REPORT_READY",
            "registry_health_status": health.get("health_status"),
            "catalog_status": catalog.get("status") if isinstance(catalog, dict) else None,
            "catalog_available": catalog_ready,
            "stale_after_days": self.stale_after_days,
            "scopes": scopes,
            "review_required_scopes": review_required_scopes,
            "review_required": bool(review_required_scopes),
            "overall_quality_score": overall_score,
            "automatic_remap_allowed": False,
            "automatic_activation_allowed": False,
            "ozon_mutation": False,
            "profit_adjustment_allowed": False,
            "read_only": True,
            "executed": False,
        }

    def _scope_quality(self, scope, catalog_by_id, catalog_ready):
        history = self.registry_service.history(scope)
        active_id = history.get("active_revision_id")
        revisions = [dict(row) for row in history.get("revisions") or [] if isinstance(row, dict)]
        active_revision = next((row for row in revisions if row.get("revision_id") == active_id), None)
        mapping = self.registry_service.load_active(scope)
        if not active_id or not isinstance(mapping, dict) or active_revision is None:
            return {
                "scope": scope,
                "active_revision_id": active_id,
                "mapping_available": False,
                "age_days": None,
                "freshness_status": "NOT_CONFIGURED",
                "missing_type_ids": [],
                "renamed_operations": [],
                "catalog_drift_detected": False,
                "review_required": False,
                "quality_score": None,
            }

        age_days = self._age_days(active_revision.get("created_at"))
        freshness = "UNKNOWN"
        if age_days is not None:
            freshness = "STALE" if age_days > self.stale_after_days else "FRESH"

        missing = []
        renamed = []
        if catalog_ready:
            for operation in mapping.get("operations") or []:
                if not isinstance(operation, dict) or operation.get("type_id") is None:
                    continue
                type_id = int(operation.get("type_id"))
                current = catalog_by_id.get(type_id)
                if current is None:
                    missing.append(type_id)
                elif current.get("name") != operation.get("name"):
                    renamed.append({
                        "type_id": type_id,
                        "mapped_name": operation.get("name"),
                        "current_name": current.get("name"),
                    })

        catalog_drift = bool(missing or renamed)
        review_required = freshness == "STALE" or catalog_drift or not catalog_ready
        score = 100
        if freshness == "STALE":
            score -= 20
        if freshness == "UNKNOWN":
            score -= 10
        if not catalog_ready:
            score -= 30
        score -= 30 * len(missing)
        score -= 20 * len(renamed)
        score = max(0, min(100, score))

        return {
            "scope": scope,
            "active_revision_id": active_id,
            "mapping_id": mapping.get("mapping_id"),
            "mapping_available": True,
            "created_at": active_revision.get("created_at"),
            "age_days": age_days,
            "freshness_status": freshness,
            "missing_type_ids": sorted(missing),
            "renamed_operations": renamed,
            "catalog_drift_detected": catalog_drift,
            "catalog_available": catalog_ready,
            "review_required": review_required,
            "quality_score": score,
            "automatic_remap_allowed": False,
            "automatic_activation_allowed": False,
            "profit_adjustment_allowed": False,
        }

    def _age_days(self, value):
        if not value:
            return None
        try:
            created = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            now = self.clock()
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            return max(0, (now - created).days)
        except (TypeError, ValueError):
            return None
