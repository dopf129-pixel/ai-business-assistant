from period_profit_mapping_review_monitoring import build_review_reopen_handoff


class Quality:
    def report(self):
        return {
            "error": False,
            "status": "PERIOD_PROFIT_MAPPING_QUALITY_REPORT_READY",
            "scopes": {
                "RETURN": {
                    "scope": "RETURN",
                    "active_revision_id": "return-mapping-r2",
                    "mapping_id": "tampered-mapping",
                    "mapping_available": True,
                    "missing_type_ids": [],
                    "renamed_operations": [{"type_id": 1}],
                }
            },
        }


class Registry:
    def load_active(self, scope):
        return {
            "mapping_id": "return-financial-mapping:abc",
            "scope": "RETURN",
            "operations": [{"type_id": 1, "name": "Old", "description": None, "source": "OZON_FINANCE_ACCRUAL_TYPES"}],
        }


class Catalog:
    def load(self):
        return {
            "error": False,
            "status": "RETURN_FINANCIAL_OPERATION_CATALOG_READY",
            "operations": [{"type_id": 1, "name": "New", "description": None, "source": "OZON_FINANCE_ACCRUAL_TYPES"}],
        }


def test_v158_rejects_quality_mapping_lineage_mismatch():
    evaluation = {
        "error": False,
        "status": "PERIOD_PROFIT_MAPPING_REVIEW_REOPENED",
        "scope": "RETURN",
        "revision_id": "return-mapping-r2",
        "mapping_id": "return-financial-mapping:abc",
        "review_reopened": True,
        "human_rereview_required": True,
    }
    result = build_review_reopen_handoff(Registry(), Catalog(), Quality(), evaluation)
    assert result["code"] == "PERIOD_PROFIT_MAPPING_REVIEW_REOPEN_HANDOFF_LINEAGE_CHANGED"
    assert result["automatic_remap_allowed"] is False
