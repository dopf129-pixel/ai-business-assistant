from period_profit_request import build_period_profit_request, build_previous_period_profit_request
from period_profit_comparison import build_period_profit_comparison
from period_profit_response import build_period_profit_response
from period_profit_coverage import build_period_profit_coverage
from period_profit_return_financial_evidence import build_period_profit_return_financial_evidence
from period_profit_expense_financial_evidence import build_period_profit_expense_financial_evidence


class PeriodProfitQueryService:
    """Read-only orchestration for user-facing profit queries."""

    def __init__(
        self,
        summary_service,
        product_provider,
        return_evidence_service=None,
        return_financial_operation_names=None,
        authorized_return_mapping=None,
        authorized_advertising_mapping=None,
        authorized_storage_mapping=None,
    ):
        self.summary_service = summary_service
        self.product_provider = product_provider
        self.return_evidence_service = return_evidence_service
        self.return_financial_operation_names = tuple(return_financial_operation_names or ())
        self.authorized_return_mapping = dict(authorized_return_mapping or {})
        self.authorized_advertising_mapping = dict(authorized_advertising_mapping or {})
        self.authorized_storage_mapping = dict(authorized_storage_mapping or {})

    def query(self, period_code=None, date_from=None, date_to=None, compare_previous=False, today=None):
        request = build_period_profit_request(period_code=period_code, date_from=date_from, date_to=date_to, today=today)
        if request.get("error"):
            return request

        products = self.product_provider()
        if not isinstance(products, list):
            return {"error": True, "code": "PERIOD_PROFIT_PRODUCTS_UNAVAILABLE", "status": "PERIOD_PROFIT_QUERY_UNAVAILABLE"}

        summary = self.summary_service.calculate(request["date_from"], request["date_to"], products)
        if summary.get("error"):
            return summary

        return_evidence = None
        if self.return_evidence_service is not None:
            return_evidence = self.return_evidence_service.load(request["date_from"], request["date_to"])
            if return_evidence.get("error"):
                return return_evidence

        operation_names, mapping = self._return_financial_mapping()
        return_financial_evidence = build_period_profit_return_financial_evidence(
            [{"fee_breakdown": summary.get("fee_breakdown")}], operation_names
        )
        return_financial_evidence["authorized_mapping_id"] = mapping.get("mapping_id") if mapping else None
        return_financial_evidence["authorized_mapping_applied"] = bool(mapping)

        advertising_evidence = self._expense_evidence(summary, "ADVERTISING", self.authorized_advertising_mapping)
        storage_evidence = self._expense_evidence(summary, "STORAGE", self.authorized_storage_mapping)

        coverage = build_period_profit_coverage(
            summary,
            return_financial_evidence,
            advertising_evidence,
            storage_evidence,
        )
        if coverage.get("error"):
            return coverage

        comparison = None
        previous_summary = None
        if compare_previous:
            previous_request = build_previous_period_profit_request(request)
            if previous_request.get("error"):
                return previous_request
            previous_summary = self.summary_service.calculate(previous_request["date_from"], previous_request["date_to"], products)
            if previous_summary.get("error"):
                return previous_summary
            comparison = build_period_profit_comparison(summary, previous_summary)
            if comparison.get("error"):
                return comparison

        response = build_period_profit_response(
            summary,
            comparison,
            return_evidence,
            return_financial_evidence,
            advertising_evidence,
            storage_evidence,
        )
        if response.get("error"):
            return response

        return {
            "error": False,
            "status": "PERIOD_PROFIT_QUERY_READY",
            "request": request,
            "summary": summary,
            "coverage": coverage,
            "return_evidence": return_evidence,
            "return_financial_evidence": return_financial_evidence,
            "advertising_financial_evidence": advertising_evidence,
            "storage_financial_evidence": storage_evidence,
            "previous_summary": previous_summary,
            "comparison": comparison,
            "text": response["text"],
            "read_only": True,
            "executed": False,
        }

    def _return_financial_mapping(self):
        mapping = self.authorized_return_mapping
        if (
            mapping.get("status") == "RETURN_FINANCIAL_OPERATION_AUTHORIZED_MAPPING_READY"
            and mapping.get("error") is False
            and mapping.get("mapping_authorized") is True
            and mapping.get("financial_evidence_mapping_allowed") is True
            and mapping.get("returns_profit_adjustment_allowed") is False
            and mapping.get("automatic_activation_allowed") is False
            and mapping.get("immutable_artifact") is True
        ):
            return tuple(mapping.get("operation_names") or ()), mapping
        return self.return_financial_operation_names, None

    def _expense_evidence(self, summary, scope, mapping):
        mapping = dict(mapping or {})
        valid = (
            mapping.get("status") == "PERIOD_PROFIT_EXPENSE_OPERATION_AUTHORIZED_MAPPING_READY"
            and mapping.get("error") is False
            and mapping.get("scope") == scope
            and mapping.get("mapping_authorized") is True
            and mapping.get("financial_evidence_mapping_allowed") is True
            and mapping.get("profit_adjustment_allowed") is False
            and mapping.get("automatic_activation_allowed") is False
            and mapping.get("immutable_artifact") is True
        )
        names = tuple(mapping.get("operation_names") or ()) if valid else ()
        evidence = build_period_profit_expense_financial_evidence(summary.get("fee_breakdown"), scope, names)
        evidence["authorized_mapping_applied"] = valid
        evidence["authorized_mapping_id"] = mapping.get("mapping_id") if valid else None
        return evidence
