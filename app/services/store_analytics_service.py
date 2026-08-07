from services.business_analytics_service import (
    BusinessAnalyticsService
)


class StoreAnalyticsService:

    def __init__(
        self,
        tax_mode,
        tax_rate,
        minimum_tax_rate,
        advertising_cost,
        analysis_date=None,
        expense_repository=None
    ):

        self.business_analytics = (
            BusinessAnalyticsService(
                tax_mode=tax_mode,
                tax_rate=tax_rate,
                minimum_tax_rate=minimum_tax_rate,
                advertising_cost=advertising_cost,
                analysis_date=analysis_date,
                expense_repository=expense_repository
            )
        )

    def analyze(
        self,
        profits
    ):

        return (
            self.business_analytics
            .calculate(
                profits
            )
        )

    def print_dashboards(
        self,
        result
    ):

        self.business_analytics.print_dashboards(
            result
        )