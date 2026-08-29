class ReturnFinancialOperationReviewReportService:
    """Read-only report over the real Ozon accrual operation catalog."""

    def __init__(self, catalog_service):
        self.catalog_service = catalog_service

    def build(self):
        catalog = self.catalog_service.load()
        if not isinstance(catalog, dict) or catalog.get("error"):
            return {
                "error": True,
                "code": "RETURN_FINANCIAL_OPERATION_REVIEW_REPORT_UNAVAILABLE",
                "status": "RETURN_FINANCIAL_OPERATION_REVIEW_REPORT_UNAVAILABLE",
                "message": catalog.get("message") if isinstance(catalog, dict) else None,
                "read_only": True,
                "executed": False,
            }

        operations = []
        for row in catalog.get("operations", []):
            if not isinstance(row, dict):
                continue
            operations.append({
                "type_id": row.get("type_id"),
                "name": row.get("name"),
                "description": row.get("description"),
                "source": row.get("source"),
                "return_related": None,
                "human_verification_required": True,
            })

        return {
            "error": False,
            "status": "RETURN_FINANCIAL_OPERATION_REVIEW_REPORT_READY",
            "operation_count": len(operations),
            "operations": operations,
            "classification_scope": "UNCLASSIFIED_SOURCE_CATALOG",
            "human_verification_required": True,
            "mapping_activation_allowed": False,
            "returns_profit_adjustment_allowed": False,
            "read_only": True,
            "executed": False,
        }
