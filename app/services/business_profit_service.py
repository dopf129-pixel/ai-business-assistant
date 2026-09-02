import math


class BusinessProfitService:

    def calculate(
        self,
        store_profit,
        tax,
        advertising_cost=0,
        other_expenses=0
    ):

        if not store_profit:

            return {
                "error": True,
                "message": (
                    "Нет данных о прибыли магазина"
                )
            }

        if not isinstance(
            store_profit,
            dict
        ):

            return self._store_profit_invalid()

        store_error = store_profit.get(
            "error"
        )

        if (
            store_error is not None
            and not isinstance(
                store_error,
                bool
            )
        ):

            return self._store_profit_invalid()

        if store_error is True:

            return self._store_profit_invalid(
                store_profit.get(
                    "message"
                )
            )

        if not isinstance(
            tax,
            dict
        ):

            return self._tax_invalid()

        tax_error = tax.get(
            "error"
        )

        if (
            tax_error is not None
            and not isinstance(
                tax_error,
                bool
            )
        ):

            return self._tax_invalid()

        if tax_error is True:

            return {
                "error": True,
                "message": tax.get(
                    "message",
                    "Не удалось рассчитать налог"
                )
            }

        configured = tax.get(
            "configured"
        )

        if (
            configured is not None
            and not isinstance(
                configured,
                bool
            )
        ):

            return self._tax_invalid()

        gross_sales = self._number(
            store_profit.get(
                "gross_sales",
                0
            )
        )

        gross_profit = self._number(
            store_profit.get(
                "gross_profit",
                0
            )
        )

        advertising_cost = (
            self._non_negative_cost(
                advertising_cost
            )
        )

        other_expenses = (
            self._non_negative_cost(
                other_expenses
            )
        )

        if (
            gross_sales is None
            or gross_profit is None
        ):

            return self._store_profit_invalid()

        if (
            advertising_cost is None
            or other_expenses is None
        ):

            return self._cost_invalid()

        if (
            configured is False
            or tax.get(
                "tax_amount"
            ) is None
        ):

            return {
                "error": False,
                "configured": False,
                "gross_sales": round(
                    gross_sales,
                    2
                ),
                "gross_profit": round(
                    gross_profit,
                    2
                ),
                "tax_amount": None,
                "advertising_cost": round(
                    advertising_cost,
                    2
                ),
                "other_expenses": round(
                    other_expenses,
                    2
                ),
                "business_profit": None,
                "margin_percent": None
            }

        tax_amount = (
            self._non_negative_number(
                tax.get(
                    "tax_amount"
                )
            )
        )

        if tax_amount is None:

            return self._tax_invalid()

        business_profit = (
            gross_profit
            - tax_amount
            - advertising_cost
            - other_expenses
        )

        if not math.isfinite(
            business_profit
        ):

            return self._result_invalid()

        margin_percent = 0.0

        if gross_sales > 0:

            margin_percent = (
                business_profit
                / gross_sales
                * 100
            )

            if not math.isfinite(
                margin_percent
            ):

                return self._result_invalid()

        return {
            "error": False,
            "configured": True,
            "gross_sales": round(
                gross_sales,
                2
            ),
            "gross_profit": round(
                gross_profit,
                2
            ),
            "tax_amount": round(
                tax_amount,
                2
            ),
            "advertising_cost": round(
                advertising_cost,
                2
            ),
            "other_expenses": round(
                other_expenses,
                2
            ),
            "business_profit": round(
                business_profit,
                2
            ),
            "margin_percent": round(
                margin_percent,
                2
            )
        }

    @staticmethod
    def _number(
        value
    ):

        if isinstance(
            value,
            bool
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

        if not math.isfinite(
            number
        ):
            return None

        return number

    @classmethod
    def _non_negative_number(
        cls,
        value
    ):

        number = cls._number(
            value
        )

        if (
            number is None
            or number < 0
        ):

            return None

        return number

    @classmethod
    def _non_negative_cost(
        cls,
        value
    ):

        if value in (
            None,
            ""
        ):

            return 0.0

        return cls._non_negative_number(
            value
        )

    @staticmethod
    def _store_profit_invalid(
        message=None
    ):

        return {
            "error": True,
            "code": "BUSINESS_PROFIT_STORE_PROFIT_INVALID",
            "message": (
                message
                or "Некорректные данные прибыли магазина"
            )
        }

    @staticmethod
    def _tax_invalid():

        return {
            "error": True,
            "code": "BUSINESS_PROFIT_TAX_RESULT_INVALID",
            "message": (
                "Некорректный результат расчёта налога"
            )
        }

    @staticmethod
    def _cost_invalid():

        return {
            "error": True,
            "code": "BUSINESS_PROFIT_COST_INPUT_INVALID",
            "message": (
                "Некорректные расходы для расчёта прибыли бизнеса"
            )
        }

    @staticmethod
    def _result_invalid():

        return {
            "error": True,
            "code": "BUSINESS_PROFIT_RESULT_INVALID",
            "message": (
                "Некорректный результат прибыли бизнеса"
            )
        }
