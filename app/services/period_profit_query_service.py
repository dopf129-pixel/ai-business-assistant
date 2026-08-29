from period_profit_request import build_period_profit_request, build_previous_period_profit_request
from period_profit_comparison import build_period_profit_comparison
from period_profit_response import build_period_profit_response
from period_profit_coverage import build_period_profit_coverage


class PeriodProfitQueryService:
    """Read-only orchestration for user-facing profit queries."""

    def __init__(self, summary_service, product_provider):
        self.summary_service = summary_service
        self.product_provider = product_provider

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

        coverage = build_period_profit_coverage(summary)
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

        response = build_period_profit_response(summary, comparison)
        if response.get("error"):
            return response

        return {
            "error": False,
            "status": "PERIOD_PROFIT_QUERY_READY",
            "request": request,
            "summary": summary,
            "coverage": coverage,
            "previous_summary": previous_summary,
            "comparison": comparison,
            "text": response["text"],
            "read_only": True,
            "executed": False,
        }
