from math import isfinite

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
        mapping_observability_service=None,
        return_cogs_recovery_evidence_service=None,
        external_expense_evidence_service=None,
    ):
        self.summary_service = summary_service
        self.product_provider = product_provider
        self.return_evidence_service = return_evidence_service
        self.return_cogs_recovery_evidence_service = (
            return_cogs_recovery_evidence_service
        )
        self.return_financial_operation_names = tuple(return_financial_operation_names or ())
        self.authorized_return_mapping = dict(authorized_return_mapping or {})
        self.authorized_advertising_mapping = dict(authorized_advertising_mapping or {})
        self.authorized_storage_mapping = dict(authorized_storage_mapping or {})
        self.mapping_observability_service = mapping_observability_service
        self.external_expense_evidence_service = (
            external_expense_evidence_service
        )

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

        return_cogs_recovery_evidence = None
        if (
            self.return_cogs_recovery_evidence_service
            is not None
            and return_evidence is not None
        ):
            return_cogs_recovery_evidence = (
                self.return_cogs_recovery_evidence_service
                .analyze(
                    return_evidence,
                    products,
                )
            )

        external_expense_evidence = None
        external_expense_adjustment = None
        if (
            self.external_expense_evidence_service
            is not None
        ):
            external_expense_evidence = (
                self.external_expense_evidence_service
                .load(
                    request["date_from"],
                    request["date_to"],
                )
            )
            external_expense_adjustment = (
                self._external_expense_adjustment(
                    summary,
                    external_expense_evidence,
                )
            )
            if external_expense_adjustment.get(
                "error"
            ) is True:
                return external_expense_adjustment

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
            return_cogs_recovery_evidence,
            external_expense_evidence,
        )
        if coverage.get("error"):
            return coverage

        mapping_observability = None
        if self.mapping_observability_service is not None:
            mapping_observability = self.mapping_observability_service.snapshot()

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
            mapping_observability,
            return_cogs_recovery_evidence,
            external_expense_evidence,
            external_expense_adjustment,
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
            "return_cogs_recovery_evidence": (
                return_cogs_recovery_evidence
            ),
            "advertising_financial_evidence": advertising_evidence,
            "storage_financial_evidence": storage_evidence,
            "external_expense_evidence": (
                external_expense_evidence
            ),
            "external_expense_adjustment": (
                external_expense_adjustment
            ),
            "mapping_observability": mapping_observability,
            "previous_summary": previous_summary,
            "comparison": comparison,
            "text": response["text"],
            "read_only": True,
            "executed": False,
        }

    @staticmethod
    def _external_expense_adjustment(
        summary,
        evidence,
    ):
        source = dict(evidence or {})

        if source.get("error") is True:
            return {
                "error": False,
                "status": (
                    "PERIOD_PROFIT_EXTERNAL_EXPENSE_ADJUSTMENT_UNAVAILABLE"
                ),
                "observed_profit_after_external_expenses": None,
                "observed_margin_percent": None,
                "complete_profit_after_external_expenses": None,
                "complete_margin_percent": None,
                "profit_adjustment_complete": False,
                "read_only": True,
                "executed": False,
            }

        if source.get("status") not in {
            "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_READY",
            "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_PARTIAL",
        }:
            return {
                "error": True,
                "code": (
                    "PERIOD_PROFIT_EXTERNAL_EXPENSE_EVIDENCE_INVALID"
                ),
                "status": (
                    "PERIOD_PROFIT_EXTERNAL_EXPENSE_ADJUSTMENT_UNAVAILABLE"
                ),
            }

        try:
            profit = float(
                summary.get("profit")
            )
            revenue = float(
                summary.get("revenue")
            )
            expenses = float(
                source.get(
                    "observed_expense_total"
                )
            )
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return {
                "error": True,
                "code": (
                    "PERIOD_PROFIT_EXTERNAL_EXPENSE_ADJUSTMENT_INVALID"
                ),
                "status": (
                    "PERIOD_PROFIT_EXTERNAL_EXPENSE_ADJUSTMENT_UNAVAILABLE"
                ),
            }

        if (
            not all(
                isfinite(value)
                for value in (
                    profit,
                    revenue,
                    expenses,
                )
            )
            or expenses < 0
        ):
            return {
                "error": True,
                "code": (
                    "PERIOD_PROFIT_EXTERNAL_EXPENSE_ADJUSTMENT_INVALID"
                ),
                "status": (
                    "PERIOD_PROFIT_EXTERNAL_EXPENSE_ADJUSTMENT_UNAVAILABLE"
                ),
            }

        observed_profit = (
            profit
            - expenses
        )
        if not isfinite(
            observed_profit
        ):
            return {
                "error": True,
                "code": (
                    "PERIOD_PROFIT_EXTERNAL_EXPENSE_ADJUSTMENT_INVALID"
                ),
                "status": (
                    "PERIOD_PROFIT_EXTERNAL_EXPENSE_ADJUSTMENT_UNAVAILABLE"
                ),
            }

        observed_margin = 0.0
        if revenue != 0:
            observed_margin = (
                observed_profit
                / revenue
                * 100
            )
            if not isfinite(
                observed_margin
            ):
                return {
                    "error": True,
                    "code": (
                        "PERIOD_PROFIT_EXTERNAL_EXPENSE_ADJUSTMENT_INVALID"
                    ),
                    "status": (
                        "PERIOD_PROFIT_EXTERNAL_EXPENSE_ADJUSTMENT_UNAVAILABLE"
                    ),
                }

        complete = (
            source.get(
                "coverage_complete"
            )
            is True
        )

        return {
            "error": False,
            "status": (
                "PERIOD_PROFIT_EXTERNAL_EXPENSE_ADJUSTMENT_READY"
                if complete
                else "PERIOD_PROFIT_EXTERNAL_EXPENSE_ADJUSTMENT_PARTIAL"
            ),
            "observed_external_expenses": (
                round(expenses, 2)
            ),
            "observed_profit_after_external_expenses": (
                round(observed_profit, 2)
            ),
            "observed_margin_percent": (
                round(observed_margin, 2)
            ),
            "complete_profit_after_external_expenses": (
                round(observed_profit, 2)
                if complete
                else None
            ),
            "complete_margin_percent": (
                round(observed_margin, 2)
                if complete
                else None
            ),
            "profit_adjustment_complete": (
                complete
            ),
            "accounting_net_profit_claim_allowed": False,
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
