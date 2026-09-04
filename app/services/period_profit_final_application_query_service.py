from period_profit_comparison import build_period_profit_comparison
from period_profit_coverage import build_period_profit_coverage
from period_profit_request import build_previous_period_profit_request
from period_profit_response import build_period_profit_response


class PeriodProfitFinalApplicationQueryService:
    """Finalize read-only Period Profit from durable committed Return COGS evidence."""

    def __init__(self, base_service, return_cogs_application_service):
        self.base_service = base_service
        self.return_cogs_application_service = return_cogs_application_service
        # Preserve the established PeriodProfitQueryService compatibility surface.
        self.summary_service = getattr(base_service, "summary_service", None)
        self.product_provider = getattr(base_service, "product_provider", None)
        self.return_evidence_service = getattr(base_service, "return_evidence_service", None)
        self.return_cogs_recovery_evidence_service = getattr(
            base_service, "return_cogs_recovery_evidence_service", None
        )
        self.external_expense_evidence_service = getattr(
            base_service, "external_expense_evidence_service", None
        )

    def query(self, period_code=None, date_from=None, date_to=None, compare_previous=False, today=None):
        query = getattr(self.base_service, "query", None)
        if not callable(query):
            return self._error("PERIOD_PROFIT_FINAL_BASE_UNAVAILABLE")
        try:
            base = query(
                period_code=period_code,
                date_from=date_from,
                date_to=date_to,
                compare_previous=compare_previous,
                today=today,
            )
        except Exception:
            return self._error("PERIOD_PROFIT_FINAL_BASE_EXCEPTION")
        if not isinstance(base, dict):
            return self._error("PERIOD_PROFIT_FINAL_BASE_INVALID")
        if base.get("error") is True:
            return dict(base)
        if base.get("error") is not False:
            return self._error("PERIOD_PROFIT_FINAL_BASE_INVALID")

        application = self._apply(
            base.get("summary"),
            base.get("return_cogs_recovery_evidence"),
        )
        if application.get("error") is True:
            return application

        result = dict(base)
        summary = application["summary"]
        return_cogs_evidence = application.get("evidence")
        result["summary"] = summary
        result["return_cogs_recovery_evidence"] = return_cogs_evidence
        result["return_cogs_profit_application"] = application

        external_adjustment = result.get("external_expense_adjustment")
        external_evidence = result.get("external_expense_evidence")
        if external_evidence is not None:
            adjuster = getattr(self.base_service, "_external_expense_adjustment", None)
            if not callable(adjuster):
                return self._error("PERIOD_PROFIT_FINAL_EXTERNAL_ADJUSTMENT_UNAVAILABLE")
            external_adjustment = adjuster(summary, external_evidence)
            if not isinstance(external_adjustment, dict) or external_adjustment.get("error") is True:
                return external_adjustment if isinstance(external_adjustment, dict) else self._error(
                    "PERIOD_PROFIT_FINAL_EXTERNAL_ADJUSTMENT_INVALID"
                )
            result["external_expense_adjustment"] = external_adjustment

        previous_summary = result.get("previous_summary")
        comparison = result.get("comparison")
        if compare_previous:
            previous = self._previous_summary(result.get("request"))
            if previous.get("error") is True:
                return previous
            previous_summary = previous.get("summary")
            comparison = build_period_profit_comparison(summary, previous_summary)
            if comparison.get("error"):
                return comparison
            result["previous_summary"] = previous_summary
            result["comparison"] = comparison

        coverage = build_period_profit_coverage(
            summary,
            result.get("return_financial_evidence"),
            result.get("advertising_financial_evidence"),
            result.get("storage_financial_evidence"),
            return_cogs_evidence,
            external_evidence,
        )
        if coverage.get("error"):
            return coverage
        result["coverage"] = coverage

        response = build_period_profit_response(
            summary,
            comparison,
            result.get("return_evidence"),
            result.get("return_financial_evidence"),
            result.get("advertising_financial_evidence"),
            result.get("storage_financial_evidence"),
            result.get("mapping_observability"),
            return_cogs_evidence,
            external_evidence,
            external_adjustment,
        )
        if response.get("error"):
            return response
        result["text"] = response["text"]
        result["status"] = "PERIOD_PROFIT_QUERY_READY"
        result["period_profit_final_application_complete"] = True
        result["read_only"] = True
        result["executed"] = False
        return result

    def _previous_summary(self, current_request):
        if not isinstance(current_request, dict):
            return self._error("PERIOD_PROFIT_FINAL_PREVIOUS_REQUEST_INVALID")
        previous_request = build_previous_period_profit_request(current_request)
        if previous_request.get("error"):
            return previous_request

        products_provider = getattr(self.base_service, "product_provider", None)
        summary_service = getattr(self.base_service, "summary_service", None)
        if not callable(products_provider) or summary_service is None:
            return self._error("PERIOD_PROFIT_FINAL_PREVIOUS_DEPENDENCY_UNAVAILABLE")
        products = products_provider()
        if not isinstance(products, list):
            return self._error("PERIOD_PROFIT_PRODUCTS_UNAVAILABLE")
        summary = summary_service.calculate(
            previous_request["date_from"],
            previous_request["date_to"],
            products,
        )
        if not isinstance(summary, dict) or summary.get("error") is True:
            return summary if isinstance(summary, dict) else self._error(
                "PERIOD_PROFIT_FINAL_PREVIOUS_SUMMARY_INVALID"
            )

        return_loader = getattr(self.base_service, "return_evidence_service", None)
        cogs_service = getattr(self.base_service, "return_cogs_recovery_evidence_service", None)
        if return_loader is None or cogs_service is None:
            return {"error": False, "summary": summary}
        load = getattr(return_loader, "load", None)
        analyze = getattr(cogs_service, "analyze", None)
        if not callable(load) or not callable(analyze):
            return self._error("PERIOD_PROFIT_FINAL_PREVIOUS_RETURN_DEPENDENCY_UNAVAILABLE")
        try:
            return_evidence = load(previous_request["date_from"], previous_request["date_to"])
            if not isinstance(return_evidence, dict) or return_evidence.get("error") is True:
                return return_evidence if isinstance(return_evidence, dict) else self._error(
                    "PERIOD_PROFIT_FINAL_PREVIOUS_RETURN_EVIDENCE_INVALID"
                )
            cogs_evidence = analyze(return_evidence, products)
        except Exception:
            return self._error("PERIOD_PROFIT_FINAL_PREVIOUS_RETURN_EVIDENCE_UNAVAILABLE")
        application = self._apply(summary, cogs_evidence)
        if application.get("error") is True:
            return application
        return {"error": False, "summary": application["summary"]}

    def _apply(self, summary, evidence):
        apply = getattr(self.return_cogs_application_service, "apply", None)
        if not callable(apply):
            return self._error("PERIOD_PROFIT_FINAL_APPLICATION_SERVICE_UNAVAILABLE")
        try:
            result = apply(summary, evidence)
        except Exception:
            return self._error("PERIOD_PROFIT_FINAL_APPLICATION_SERVICE_EXCEPTION")
        if not isinstance(result, dict):
            return self._error("PERIOD_PROFIT_FINAL_APPLICATION_RESULT_INVALID")
        return result

    @staticmethod
    def _error(code):
        return {
            "error": True,
            "code": code,
            "status": "PERIOD_PROFIT_QUERY_UNAVAILABLE",
            "read_only": True,
            "executed": False,
        }
