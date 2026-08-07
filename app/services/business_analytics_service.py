from services.store_profit_service import (
    StoreProfitService
)

from services.store_profit_dashboard_service import (
    StoreProfitDashboardService
)

from services.tax_service import TaxService
from services.tax_dashboard_service import (
    TaxDashboardService
)

from services.advertising_service import (
    AdvertisingService
)

from services.advertising_dashboard_service import (
    AdvertisingDashboardService
)

from services.business_profit_service import (
    BusinessProfitService
)

from services.business_profit_dashboard_service import (
    BusinessProfitDashboardService
)


class BusinessAnalyticsService:

    def __init__(
        self,
        tax_mode,
        tax_rate,
        minimum_tax_rate,
        advertising_cost
    ):

        self.tax_mode = tax_mode
        self.tax_rate = tax_rate
        self.minimum_tax_rate = minimum_tax_rate
        self.advertising_cost = advertising_cost

        self.store_profit_service = (
            StoreProfitService()
        )

        self.store_profit_dashboard = (
            StoreProfitDashboardService()
        )

        self.tax_service = TaxService()
        self.tax_dashboard = TaxDashboardService()

        self.advertising_service = (
            AdvertisingService()
        )

        self.advertising_dashboard = (
            AdvertisingDashboardService()
        )

        self.business_profit_service = (
            BusinessProfitService()
        )

        self.business_profit_dashboard = (
            BusinessProfitDashboardService()
        )

    def calculate(
        self,
        profits
    ):

        store_profit = (
            self.store_profit_service
            .calculate(
                profits
            )
        )

        configured_rate = None

        if self.tax_rate > 0:
            configured_rate = self.tax_rate

        tax = self.tax_service.calculate(
            mode=self.tax_mode,
            revenue=store_profit.get(
                "gross_sales",
                0
            ),
            gross_profit=store_profit.get(
                "gross_profit",
                0
            ),
            tax_rate=configured_rate,
            minimum_tax_rate=(
                self.minimum_tax_rate
            )
        )

        advertising = (
            self.advertising_service
            .calculate(
                self.advertising_cost
            )
        )

        if advertising.get("error"):

            return {
                "error": True,
                "message": advertising.get(
                    "message",
                    "Ошибка рекламных расходов"
                ),
                "store_profit": store_profit,
                "tax": tax,
                "advertising": advertising
            }

        business_profit = (
            self.business_profit_service
            .calculate(
                store_profit=store_profit,
                tax=tax,
                advertising_cost=(
                    advertising.get(
                        "advertising_cost",
                        0
                    )
                )
            )
        )

        return {
            "error": False,
            "store_profit": store_profit,
            "tax": tax,
            "advertising": advertising,
            "business_profit": business_profit
        }

    def print_dashboards(
        self,
        result
    ):

        store_profit = result.get(
            "store_profit",
            {}
        )

        tax = result.get(
            "tax",
            {}
        )

        advertising = result.get(
            "advertising",
            {}
        )

        business_profit = result.get(
            "business_profit",
            {}
        )

        self.store_profit_dashboard.print_dashboard(
            store_profit
        )

        self.tax_dashboard.print_dashboard(
            tax
        )

        self.advertising_dashboard.print_dashboard(
            advertising
        )

        self.business_profit_dashboard.print_dashboard(
            business_profit
        )