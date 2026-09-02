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

from services.expense_repository import (
    ExpenseRepository
)

from services.expense_service import (
    ExpenseService
)

from services.expense_dashboard_service import (
    ExpenseDashboardService
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
        advertising_cost,
        analysis_date=None,
        date_from=None,
        date_to=None,
        expense_repository=None
    ):

        self.tax_mode = tax_mode
        self.tax_rate = tax_rate

        self.minimum_tax_rate = (
            minimum_tax_rate
        )

        self.advertising_cost = (
            advertising_cost
        )

        # Обратная совместимость:
        # если передана старая analysis_date,
        # считаем её периодом из одного дня.

        if analysis_date:

            self.date_from = str(
                analysis_date
            )

            self.date_to = str(
                analysis_date
            )

        else:

            self.date_from = (
                str(date_from)
                if date_from
                else None
            )

            self.date_to = (
                str(date_to)
                if date_to
                else None
            )

        self.store_profit_service = (
            StoreProfitService()
        )

        self.store_profit_dashboard = (
            StoreProfitDashboardService()
        )

        self.tax_service = (
            TaxService()
        )

        self.tax_dashboard = (
            TaxDashboardService()
        )

        self.advertising_service = (
            AdvertisingService()
        )

        self.advertising_dashboard = (
            AdvertisingDashboardService()
        )

        self.expense_repository = (
            expense_repository
            or ExpenseRepository()
        )

        self.expense_service = (
            ExpenseService()
        )

        self.expense_dashboard = (
            ExpenseDashboardService()
        )

        self.business_profit_service = (
            BusinessProfitService()
        )

        self.business_profit_dashboard = (
            BusinessProfitDashboardService()
        )

    def get_period_info(
        self
    ):

        return {
            "date_from": self.date_from,
            "date_to": self.date_to
        }

    def load_expenses(
        self
    ):

        # Если период вообще не передан,
        # ничего из реальной базы не читаем.
        #
        # Это важно для изолированных тестов.

        if (
            not self.date_from
            and not self.date_to
        ):

            return {
                "error": False,
                "expenses_count": 0,
                "expenses": [],
                "other_expenses": 0.0
            }

        try:

            # Один день

            if (
                self.date_from
                and self.date_to
                and self.date_from
                == self.date_to
            ):

                rows = (
                    self.expense_repository
                    .get_expenses_by_date(
                        self.date_to
                    )
                )

            # Обычный диапазон:
            # 7 / 28 / 56 / 90 дней

            elif (
                self.date_from
                and self.date_to
            ):

                rows = (
                    self.expense_repository
                    .get_expenses_by_period(
                        self.date_from,
                        self.date_to
                    )
                )

            # "За всё время" до date_to.
            #
            # ISO-даты в базе имеют формат
            # YYYY-MM-DD, поэтому начало
            # можно безопасно задать очень
            # ранней датой.

            elif (
                not self.date_from
                and self.date_to
            ):

                rows = (
                    self.expense_repository
                    .get_expenses_by_period(
                        "0001-01-01",
                        self.date_to
                    )
                )

            else:

                rows = []

        except Exception as error:

            return {
                "error": True,
                "message": (
                    "Не удалось получить "
                    "прочие расходы: "
                    f"{error}"
                )
            }

        expenses = []

        for row in rows:

            expenses.append(
                {
                    "name": row.get(
                        "category",
                        "Без названия"
                    ),
                    "amount": row.get(
                        "amount",
                        0
                    ),
                    "description": row.get(
                        "description",
                        ""
                    )
                }
            )

        return (
            self.expense_service
            .calculate(
                expenses
            )
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

        if not isinstance(
            store_profit,
            dict
        ):

            return {
                "error": True,
                "code": "STORE_PROFIT_RESULT_INVALID",
                "message": (
                    "Некорректный результат прибыли магазина"
                ),
                "period": (
                    self.get_period_info()
                )
            }

        if store_profit.get(
            "error"
        ):

            return {
                "error": True,
                "code": store_profit.get(
                    "code",
                    "STORE_PROFIT_CALCULATION_FAILED"
                ),
                "message": store_profit.get(
                    "message",
                    "Не удалось рассчитать прибыль магазина"
                ),
                "period": (
                    self.get_period_info()
                ),
                "store_profit": store_profit
            }

        configured_rate = None

        if self.tax_rate > 0:

            configured_rate = (
                self.tax_rate
            )

        tax = (
            self.tax_service
            .calculate(
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
        )

        if self.advertising_cost is None:

            advertising = {
                "error": False,
                "configured": False,
                "advertising_cost": None
            }

        else:

            advertising = (
                self.advertising_service
                .calculate(
                    self.advertising_cost
                )
            )

            if not advertising.get(
                "error"
            ):

                advertising = dict(
                    advertising
                )

                advertising.setdefault(
                    "configured",
                    True
                )


        if advertising.get(
            "error"
        ):

            return {
                "error": True,
                "message": advertising.get(
                    "message",
                    "Ошибка рекламных расходов"
                ),
                "period": (
                    self.get_period_info()
                ),
                "store_profit": store_profit,
                "tax": tax,
                "advertising": advertising
            }

        expenses = (
            self.load_expenses()
        )

        if expenses.get(
            "error"
        ):

            return {
                "error": True,
                "message": expenses.get(
                    "message",
                    "Ошибка прочих расходов"
                ),
                "period": (
                    self.get_period_info()
                ),
                "store_profit": store_profit,
                "tax": tax,
                "advertising": advertising,
                "expenses": expenses
            }

        if tax.get(
            "error"
        ):

            business_profit = (
                self.business_profit_service
                .calculate(
                    store_profit=store_profit,
                    tax=tax,
                    advertising_cost=0,
                    other_expenses=(
                        expenses.get(
                            "other_expenses",
                            0
                        )
                    )
                )
            )

        elif advertising.get(
            "configured"
        ) is False:

            missing_fields = [
                "advertising"
            ]

            if (
                tax.get("configured") is False
                or tax.get("tax_amount") is None
            ):

                missing_fields.append(
                    "tax"
                )

            business_profit = {
                "error": False,
                "configured": False,
                "gross_sales": store_profit.get(
                    "gross_sales"
                ),
                "gross_profit": store_profit.get(
                    "gross_profit"
                ),
                "tax_amount": tax.get(
                    "tax_amount"
                ),
                "advertising_cost": None,
                "other_expenses": expenses.get(
                    "other_expenses"
                ),
                "business_profit": None,
                "margin_percent": None,
                "missing_fields": missing_fields
            }

        else:

            business_profit = (
                self.business_profit_service
                .calculate(
                    store_profit=store_profit,
                    tax=tax,
                    advertising_cost=(
                        advertising.get(
                            "advertising_cost"
                        )
                    ),
                    other_expenses=(
                        expenses.get(
                            "other_expenses",
                            0
                        )
                    )
                )
            )

        if not isinstance(
            business_profit,
            dict
        ):

            return {
                "error": True,
                "code": "BUSINESS_PROFIT_RESULT_INVALID",
                "message": (
                    "Некорректный результат прибыли бизнеса"
                ),
                "period": (
                    self.get_period_info()
                ),
                "store_profit": store_profit,
                "tax": tax,
                "advertising": advertising,
                "expenses": expenses
            }

        business_profit_code = (
            business_profit.get(
                "code"
            )
        )

        if (
            business_profit.get(
                "error"
            ) is True
            and isinstance(
                business_profit_code,
                str
            )
            and business_profit_code.startswith(
                "BUSINESS_PROFIT_"
            )
        ):

            return {
                "error": True,
                "code": business_profit_code,
                "message": business_profit.get(
                    "message",
                    "Не удалось рассчитать прибыль бизнеса"
                ),
                "period": (
                    self.get_period_info()
                ),
                "store_profit": store_profit,
                "tax": tax,
                "advertising": advertising,
                "expenses": expenses,
                "business_profit": business_profit
            }

        return {
            "error": False,
            "period": (
                self.get_period_info()
            ),
            "store_profit": store_profit,
            "tax": tax,
            "advertising": advertising,
            "expenses": expenses,
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

        expenses = result.get(
            "expenses",
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

        self.expense_dashboard.print_dashboard(
            expenses
        )

        self.business_profit_dashboard.print_dashboard(
            business_profit
        )