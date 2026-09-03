class PeriodProfitReturnEvidenceService:
    """Read-only paginated evidence loader over Ozon Returns API."""

    PAGE_SIZE = 500
    MAX_PAGES = 10

    def __init__(self, ozon_client):
        self.ozon_client = ozon_client

    def load(
        self,
        date_from,
        date_to,
        offer_id=None,
        return_schema="FBO",
    ):
        evidence = []
        last_id = 0
        successful_pages = 0
        complete = False
        partial_reason = None

        for page_number in range(self.MAX_PAGES):
            response = self.ozon_client.get_returns(
                offer_id=offer_id,
                return_schema=return_schema,
                since=date_from,
                to=date_to,
                limit=self.PAGE_SIZE,
                last_id=last_id,
            )

            if (
                not isinstance(response, dict)
                or response.get("error")
            ):
                if page_number == 0:
                    return self._unavailable(
                        response
                    )

                partial_reason = (
                    "RETURNS_PAGE_UNAVAILABLE"
                )
                break

            records = self._extract_records(
                response
            )
            successful_pages += 1

            evidence.extend(
                self._normalize_record(item)
                for item in records
                if isinstance(item, dict)
            )

            if not self._has_next(response):
                complete = True
                break

            if not records:
                partial_reason = (
                    "RETURNS_EMPTY_PAGE_WITH_HAS_NEXT"
                )
                break

            next_id = self._next_id(
                records[-1]
            )
            if (
                next_id is None
                or next_id == last_id
            ):
                partial_reason = (
                    "RETURNS_CURSOR_INVALID"
                )
                break

            last_id = next_id
        else:
            partial_reason = (
                "RETURNS_PAGE_LIMIT_REACHED"
            )

        status = (
            "PERIOD_PROFIT_RETURN_EVIDENCE_READY"
            if complete
            else "PERIOD_PROFIT_RETURN_EVIDENCE_PARTIAL"
        )

        return {
            "error": False,
            "status": status,
            "date_from": str(date_from),
            "date_to": str(date_to),
            "offer_id": (
                str(offer_id)
                if offer_id is not None
                else None
            ),
            "return_schema": str(return_schema),
            "return_record_count": len(evidence),
            "return_record_count_exact": complete,
            "returns_observed": bool(evidence),
            "complete": complete,
            "partial_reason": partial_reason,
            "page_count": successful_pages,
            "records": evidence,
            "financial_impact_supported": False,
            "returns_profit_adjustment_allowed": False,
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _has_next(response):
        if type(response.get("has_next")) is bool:
            return response["has_next"]

        result = response.get("result")
        if (
            isinstance(result, dict)
            and type(result.get("has_next")) is bool
        ):
            return result["has_next"]

        return False

    @staticmethod
    def _next_id(record):
        if not isinstance(record, dict):
            return None

        value = record.get("id")
        if value is None:
            value = record.get("return_id")

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

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
        result = {
            key: item.get(key)
            for key in fields
            if key in item
        }
        result["source"] = (
            "OZON_RETURNS_API"
        )
        return result

    @staticmethod
    def _unavailable(response):
        return {
            "error": True,
            "code": (
                "PERIOD_PROFIT_RETURN_EVIDENCE_UNAVAILABLE"
            ),
            "status": (
                "PERIOD_PROFIT_RETURN_EVIDENCE_UNAVAILABLE"
            ),
            "message": (
                (response or {}).get("message")
                if isinstance(response, dict)
                else None
            ),
            "read_only": True,
            "executed": False,
        }
