class PeriodProfitReturnEvidenceService:
    """Read-only evidence loader over Ozon Returns API.

    This service deliberately does not calculate monetary return impact.
    It only proves whether return records are available for the requested period.
    """

    def __init__(self, ozon_client):
        self.ozon_client = ozon_client

    def load(self, date_from, date_to, offer_id=None, return_schema="FBO"):
        response = self.ozon_client.get_returns(
            offer_id=offer_id,
            return_schema=return_schema,
            since=date_from,
            to=date_to,
        )
        if not isinstance(response, dict) or response.get("error"):
            return {
                "error": True,
                "code": "PERIOD_PROFIT_RETURN_EVIDENCE_UNAVAILABLE",
                "status": "PERIOD_PROFIT_RETURN_EVIDENCE_UNAVAILABLE",
                "message": (response or {}).get("message") if isinstance(response, dict) else None,
                "read_only": True,
                "executed": False,
            }

        records = self._extract_records(response)
        evidence = [self._normalize_record(item) for item in records if isinstance(item, dict)]
        return {
            "error": False,
            "status": "PERIOD_PROFIT_RETURN_EVIDENCE_READY",
            "date_from": str(date_from),
            "date_to": str(date_to),
            "offer_id": str(offer_id) if offer_id is not None else None,
            "return_schema": str(return_schema),
            "return_record_count": len(evidence),
            "returns_observed": bool(evidence),
            "records": evidence,
            "financial_impact_supported": False,
            "returns_profit_adjustment_allowed": False,
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _extract_records(response):
        for key in ("returns", "items"):
            value = response.get(key)
            if isinstance(value, list):
                return value
        result = response.get("result")
        if isinstance(result, dict):
            for key in ("returns", "items"):
                value = result.get(key)
                if isinstance(value, list):
                    return value
        return []

    @staticmethod
    def _normalize_record(item):
        # Keep only descriptive/source fields when present. No monetary values are inferred.
        fields = (
            "id",
            "return_id",
            "posting_number",
            "offer_id",
            "sku",
            "status",
            "visual_status",
            "return_reason_name",
            "return_date",
            "visual_status_change_moment",
            "quantity",
        )
        result = {key: item.get(key) for key in fields if key in item}
        result["source"] = "OZON_RETURNS_API"
        return result
