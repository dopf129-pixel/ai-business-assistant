from services.sales_context_provider import (
    SalesContextProvider
)
from services.stock_context_provider import (
    StockContextProvider
)
from services.finance_context_provider import (
    FinanceContextProvider
)


class AssistantEntryService:

    def __init__(
        self,
        main_flow_service,
        product_service=None,
        period_profit_service=None,
        analytics_service=None,
        metrics_service=None,
        sales_context_provider=None,
        stock_context_provider=None,
        finance_context_provider=None,
        period_profit_runtime_service=None,
        return_operation_review_runtime_service=None,
        period_profit_mapping_admin_runtime_service=None,
        period_profit_mapping_recovery_runtime_service=None,
        freshness_operational_runtime_service=None,
        task_persistence_operational_runtime_service=None
    ):
        self.main_flow_service = main_flow_service

        # Backward-compatible legacy attributes.
        # Context construction itself is delegated to providers.
        self.product_service = product_service
        self.period_profit_service = period_profit_service
        self.analytics_service = analytics_service
        self.metrics_service = metrics_service
        self.period_profit_runtime_service = (
            period_profit_runtime_service
        )
        self.return_operation_review_runtime_service = (
            return_operation_review_runtime_service
        )
        self.period_profit_mapping_admin_runtime_service = (
            period_profit_mapping_admin_runtime_service
        )
        self.period_profit_mapping_recovery_runtime_service = (
            period_profit_mapping_recovery_runtime_service
        )
        self.freshness_operational_runtime_service = (
            freshness_operational_runtime_service
        )
        self.task_persistence_operational_runtime_service = (
            task_persistence_operational_runtime_service
        )

        self._sales_context_provider_explicit = (
            sales_context_provider is not None
        )

        self.sales_context_provider = (
            sales_context_provider
            or SalesContextProvider(
                product_service=product_service,
                period_profit_service=period_profit_service,
                analytics_service=analytics_service
            )
        )
        self._stock_context_provider_explicit = (
            stock_context_provider is not None
        )

        self.stock_context_provider = (
            stock_context_provider
            or StockContextProvider(
                product_service=product_service,
                analytics_service=analytics_service,
                metrics_service=metrics_service
            )
        )
        self.finance_context_provider = (
            finance_context_provider
            or FinanceContextProvider()
        )

    def handle(
        self,
        text,
        context=None,
        user_id=None
    ):
        if self.task_persistence_operational_runtime_service is not None:
            direct_result = (
                self.task_persistence_operational_runtime_service
                .handle_text(
                    text,
                    user_id=user_id
                )
            )
            if direct_result is not None:
                return direct_result

        if self.freshness_operational_runtime_service is not None:
            direct_result = (
                self.freshness_operational_runtime_service
                .handle_text(text)
            )
            if direct_result is not None:
                return direct_result

        if self.period_profit_mapping_recovery_runtime_service is not None:
            direct_result = (
                self.period_profit_mapping_recovery_runtime_service
                .handle_text(text)
            )
            if direct_result is not None:
                return direct_result

        if self.period_profit_mapping_admin_runtime_service is not None:
            direct_result = (
                self.period_profit_mapping_admin_runtime_service
                .handle_text(text)
            )
            if direct_result is not None:
                return direct_result

        if self.return_operation_review_runtime_service is not None:
            direct_result = (
                self.return_operation_review_runtime_service
                .handle_text(text)
            )
            if direct_result is not None:
                return direct_result

        if self.period_profit_runtime_service is not None:
            direct_result = (
                self.period_profit_runtime_service
                .handle_text(text)
            )
            if direct_result is not None:
                return direct_result

        report = {
            "sales_down": True,
            "low_stock": True
        }

        finance_context = dict(
            (context or {}).get(
                "finance_context"
            )
            or {}
        )

        if finance_context:
            report["finance_context"] = finance_context

        stock_context = dict(
            (context or {}).get(
                "stock_context"
            )
            or {}
        )

        if stock_context:
            report["stock_context"] = stock_context
        else:
            stock_report = self._build_stock_report()

            if stock_report is not None:
                report.update(stock_report)

        sales_report = self._build_sales_report()

        if sales_report:
            if finance_context:
                sales_report.pop(
                    "finance_context",
                    None
                )

            report.update(sales_report)

        return (
            self.main_flow_service
            .process(
                text,
                report,
                context,
                user_id
            )
        )

    def _build_stock_report(self):
        if (
            not self._stock_context_provider_explicit
            and not any(
                [
                    self.product_service,
                    self.analytics_service,
                    self.metrics_service
                ]
            )
        ):
            return None

        return self.stock_context_provider.build()

    def _build_sales_report(self):
        sales_result = (
            self.sales_context_provider
            .build()
        )

        configured = (
            self._sales_context_provider_explicit
            or any(
                [
                    self.product_service,
                    self.period_profit_service,
                    self.analytics_service
                ]
            )
        )

        if not isinstance(
            sales_result,
            dict
        ):
            if configured:
                return {
                    "sales_down": False,
                    "sales_evidence_available": False
                }

            return None

        sales_report = sales_result.get(
            "report"
        )

        if not sales_report:
            if configured:
                return {
                    "sales_down": False,
                    "sales_evidence_available": False
                }

            return None

        result = dict(
            sales_report
        )
        finance_report = (
            self.finance_context_provider
            .build(
                sales_result.get(
                    "period_data"
                )
            )
        )

        if finance_report:
            result.update(
                finance_report
            )

        return result

    def _build_finance_data(
        self,
        profits
    ):
        return (
            self.finance_context_provider
            ._build_finance_data(profits)
        )
