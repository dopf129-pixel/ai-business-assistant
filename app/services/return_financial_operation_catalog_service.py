class ReturnFinancialOperationCatalogService:
    """Read-only catalog of real Ozon accrual operation types.

    The service exposes source operation IDs/names/descriptions for human review.
    It does not infer which operations are return-related.
    """

    def __init__(self, finance_service):
        self.finance_service = finance_service

    def load(self):
        result = self.finance_service.load_accrual_types()
        if not isinstance(result, dict) or result.get("error"):
            return {
                "error": True,
                "code": "RETURN_FINANCIAL_OPERATION_CATALOG_UNAVAILABLE",
                "status": "RETURN_FINANCIAL_OPERATION_CATALOG_UNAVAILABLE",
                "message": result.get("message") if isinstance(result, dict) else None,
                "read_only": True,
                "executed": False,
            }

        catalog = []
        for type_id, info in sorted(self.finance_service.accrual_types.items()):
            source = dict(info or {})
            catalog.append({
                "type_id": int(type_id),
                "name": source.get("name"),
                "description": source.get("description"),
                "source": "OZON_FINANCE_ACCRUAL_TYPES",
            })

        return {
            "error": False,
            "status": "RETURN_FINANCIAL_OPERATION_CATALOG_READY",
            "operation_count": len(catalog),
            "operations": catalog,
            "return_classification_applied": False,
            "mapping_activation_allowed": False,
            "read_only": True,
            "executed": False,
        }
