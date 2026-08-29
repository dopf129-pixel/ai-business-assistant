from datetime import datetime, timezone

from period_profit_mapping_quality_response import build_period_profit_mapping_quality_response
from services.period_profit_mapping_quality_service import PeriodProfitMappingQualityService


class Registry:
    def health(self):
        return {"health_status": "HEALTHY"}

    def history(self, scope):
        if scope == "RETURN":
            return {
                "active_revision_id": "return-mapping-r1",
                "revisions": [{
                    "revision_id": "return-mapping-r1",
                    "created_at": "2026-01-01T00:00:00+00:00",
                }],
            }
        if scope == "ADVERTISING":
            return {
                "active_revision_id": "advertising-mapping-r1",
                "revisions": [{
                    "revision_id": "advertising-mapping-r1",
                    "created_at": "2026-08-20T00:00:00+00:00",
                }],
            }
        return {"active_revision_id": None, "revisions": []}

    def load_active(self, scope):
        if scope == "RETURN":
            return {
                "mapping_id": "r1",
                "operations": [{"type_id": 1, "name": "Old Return Name"}],
            }
        if scope == "ADVERTISING":
            return {
                "mapping_id": "a1",
                "operations": [{"type_id": 2, "name": "Promo"}, {"type_id": 9, "name": "Gone"}],
            }
        return None


class Catalog:
    def load(self):
        return {
            "error": False,
            "status": "RETURN_FINANCIAL_OPERATION_CATALOG_READY",
            "operations": [
                {"type_id": 1, "name": "Return Fee"},
                {"type_id": 2, "name": "Promo"},
            ],
        }


def _service():
    return PeriodProfitMappingQualityService(
        Registry(),
        Catalog(),
        clock=lambda: datetime(2026, 8, 29, tzinfo=timezone.utc),
        stale_after_days=90,
    )


def test_old_mapping_is_stale_and_rename_requires_review():
    report = _service().report()
    row = report["scopes"]["RETURN"]
    assert row["freshness_status"] == "STALE"
    assert row["catalog_drift_detected"] is True
    assert row["renamed_operations"][0]["current_name"] == "Return Fee"
    assert row["review_required"] is True
    assert row["automatic_remap_allowed"] is False


def test_missing_type_id_requires_review_without_automatic_remap():
    row = _service().report()["scopes"]["ADVERTISING"]
    assert row["freshness_status"] == "FRESH"
    assert row["missing_type_ids"] == [9]
    assert row["catalog_drift_detected"] is True
    assert row["review_required"] is True
    assert row["automatic_activation_allowed"] is False


def test_unconfigured_scope_is_not_reported_as_bad_mapping():
    row = _service().report()["scopes"]["STORAGE"]
    assert row["mapping_available"] is False
    assert row["freshness_status"] == "NOT_CONFIGURED"
    assert row["review_required"] is False
    assert row["quality_score"] is None


def test_quality_report_is_consolidated_and_read_only():
    report = _service().report()
    assert report["status"] == "PERIOD_PROFIT_MAPPING_QUALITY_REPORT_READY"
    assert sorted(report["review_required_scopes"]) == ["ADVERTISING", "RETURN"]
    assert report["review_required"] is True
    assert report["automatic_remap_allowed"] is False
    assert report["profit_adjustment_allowed"] is False


def test_user_response_explains_manual_review_and_safety():
    response = build_period_profit_mapping_quality_response(_service().report())
    assert "нужна ручная проверка" in response["text"]
    assert "remap, activation, Ozon и формула прибыли не изменяются" in response["text"]
    assert response["automatic_remap_allowed"] is False
    assert response["profit_adjustment_allowed"] is False
