from math import isfinite


class FinanceIntelligenceService:

    def analyze(
        self,
        finance_data,
        previous_data=None
    ):

        if (
            not isinstance(finance_data, dict)
            or not finance_data
        ):
            return self._missing_data_result()

        if (
            previous_data is not None
            and not isinstance(previous_data, dict)
        ):
            return self._missing_data_result()

        revenue = self._number(
            finance_data.get(
                "revenue"
            )
        )
        expenses = self._number(
            finance_data.get(
                "expenses"
            )
        )

        if revenue is None or expenses is None:
            return self._missing_data_result()

        profit = finance_data.get(
            "profit"
        )

        profit_scope = finance_data.get(
            "profit_scope"
        )

        if profit is None:
            profit = revenue - expenses

            if not profit_scope:
                profit_scope = (
                    "DERIVED_REVENUE_MINUS_EXPENSES"
                )

        else:
            profit = self._number(
                profit
            )

            if profit is None:
                return self._missing_data_result()

            if not profit_scope:
                profit_scope = "CALLER_PROVIDED"

        margin = finance_data.get(
            "margin"
        )

        if margin is None:
            margin = (
                profit / revenue * 100
                if revenue
                else 0
            )

        else:
            margin = self._number(
                margin
            )

            if margin is None:
                return self._missing_data_result()

        metrics = {
            "revenue": round(revenue, 2),
            "expenses": round(expenses, 2),
            "profit": round(profit, 2),
            "margin": round(margin, 2)
        }

        return {
            "error": False,
            "metrics": metrics,
            "profit_scope": profit_scope,
            "insights": self._build_insights(
                metrics,
                previous_data,
                profit_scope
            )
        }

    def _build_insights(
        self,
        metrics,
        previous_data,
        profit_scope=None
    ):

        insights = []

        result_label = (
            "Расчётный валовый результат"
            if profit_scope
            == "PERIOD_GROSS_PROFIT"
            else "Расчётный финансовый результат"
        )

        if metrics["profit"] > 0:
            insights.append(
                {
                    "type": "finance_profitable",
                    "severity": "positive",
                    "message": result_label + " положительный"
                }
            )
        elif metrics["profit"] < 0:
            insights.append(
                {
                    "type": "finance_loss",
                    "severity": "critical",
                    "message": result_label + " отрицательный"
                }
            )
        else:
            insights.append(
                {
                    "type": "finance_break_even",
                    "severity": "neutral",
                    "message": result_label + " равен нулю"
                }
            )

        if not previous_data:
            return insights

        if self._previous_data_malformed(
            previous_data
        ):
            return []

        previous_profit = self._resolve_profit(
            previous_data
        )

        if (
            previous_profit is not None
            and metrics["profit"] < previous_profit
        ):
            insights.append(
                {
                    "type": "profit_decline",
                    "severity": "attention",
                    "change_percent": self._change_percent(
                        metrics["profit"],
                        previous_profit
                    ),
                    "message": (
                        result_label
                        + " снизился относительно предыдущего периода"
                    )
                }
            )

        previous_expenses = self._number(
            previous_data.get(
                "expenses"
            )
        )

        if (
            previous_expenses is not None
            and metrics["expenses"] > previous_expenses
        ):
            insights.append(
                {
                    "type": "expenses_growth",
                    "severity": "attention",
                    "change_percent": self._change_percent(
                        metrics["expenses"],
                        previous_expenses
                    ),
                    "message": "Расходы выросли относительно предыдущего периода"
                }
            )

        return insights

    def _previous_data_malformed(
        self,
        data
    ):
        for field in (
            "revenue",
            "expenses",
            "profit",
            "margin"
        ):
            if (
                field in data
                and self._number(
                    data.get(field)
                ) is None
            ):
                return True

        return False

    def _number(
        self,
        value
    ):
        if (
            value is None
            or isinstance(value, bool)
        ):
            return None

        try:
            number = float(
                value
            )
        except (
            TypeError,
            ValueError
        ):
            return None

        if not isfinite(
            number
        ):
            return None

        return number

    def _resolve_profit(
        self,
        data
    ):

        profit = data.get(
            "profit"
        )

        if profit is not None:
            return self._number(
                profit
            )

        revenue = data.get(
            "revenue"
        )
        expenses = data.get(
            "expenses"
        )

        if revenue is None or expenses is None:
            return None

        revenue = self._number(
            revenue
        )
        expenses = self._number(
            expenses
        )

        if revenue is None or expenses is None:
            return None

        return revenue - expenses

    def _change_percent(
        self,
        current,
        previous
    ):

        if previous == 0:
            return None

        return round(
            (current - previous)
            / abs(previous)
            * 100,
            2
        )

    def _missing_data_result(
        self
    ):

        return {
            "error": True,
            "metrics": {
                "revenue": None,
                "expenses": None,
                "profit": None,
                "margin": None
            },
            "insights": [],
            "message": "Недостаточно финансовых данных для анализа"
        }
