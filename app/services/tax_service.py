import math


class TaxService:

    SUPPORTED_MODES = {
        "USN_INCOME": "УСН Доходы",
        "USN_INCOME_MINUS_EXPENSES": (
            "УСН Доходы минус расходы"
        ),
        "NONE": "Без налога"
    }

    def calculate(
        self,
        mode,
        revenue,
        gross_profit,
        tax_rate=None,
        minimum_tax_rate=1.0
    ):

        if mode is None or str(mode).strip() == "":

            return {
                "error": False,
                "configured": False,
                "mode": None,
                "mode_name": "Не настроен",
                "tax_base": None,
                "tax_rate": None,
                "tax_amount": None
            }

        mode = str(mode).upper()

        if mode not in self.SUPPORTED_MODES:

            return {
                "error": True,
                "message": (
                    "Неподдерживаемый налоговый режим"
                )
            }

        if mode == "NONE":

            return {
                "error": False,
                "configured": True,
                "mode": mode,
                "mode_name": (
                    self.SUPPORTED_MODES[mode]
                ),
                "tax_base": 0.0,
                "tax_rate": 0.0,
                "tax_amount": 0.0
            }

        revenue = self._normalize_amount(
            revenue
        )
        gross_profit = self._normalize_amount(
            gross_profit
        )

        if (
            revenue is None
            or gross_profit is None
        ):

            return {
                "error": True,
                "message": (
                    "Некорректные данные для расчёта налога"
                )
            }

        if mode == "USN_INCOME":

            rate = self._normalize_rate(
                tax_rate,
                default=6.0
            )

            if rate is None:

                return {
                    "error": True,
                    "message": (
                        "Некорректная налоговая ставка"
                    )
                }

            tax_base = max(
                0.0,
                revenue
            )

            tax_amount = (
                tax_base
                * rate
                / 100
            )

            if not math.isfinite(
                tax_amount
            ):

                return self._invalid_result()

            return {
                "error": False,
                "configured": True,
                "mode": mode,
                "mode_name": (
                    self.SUPPORTED_MODES[mode]
                ),
                "tax_base": round(
                    tax_base,
                    2
                ),
                "tax_rate": round(
                    rate,
                    2
                ),
                "tax_amount": round(
                    tax_amount,
                    2
                )
            }

        if mode == "USN_INCOME_MINUS_EXPENSES":

            rate = self._normalize_rate(
                tax_rate,
                default=15.0
            )

            if rate is None:

                return {
                    "error": True,
                    "message": (
                        "Некорректная налоговая ставка"
                    )
                }

            normalized_minimum_rate = (
                self._normalize_rate(
                    minimum_tax_rate,
                    default=1.0
                )
            )

            if normalized_minimum_rate is None:

                return {
                    "error": True,
                    "message": (
                        "Некорректная минимальная налоговая ставка"
                    )
                }

            tax_base = max(
                0.0,
                gross_profit
            )

            regular_tax = (
                tax_base
                * rate
                / 100
            )

            minimum_tax = (
                max(
                    0.0,
                    revenue
                )
                * normalized_minimum_rate
                / 100
            )

            if (
                not math.isfinite(
                    regular_tax
                )
                or not math.isfinite(
                    minimum_tax
                )
            ):

                return self._invalid_result()

            tax_amount = max(
                regular_tax,
                minimum_tax
            )

            if not math.isfinite(
                tax_amount
            ):

                return self._invalid_result()

            return {
                "error": False,
                "configured": True,
                "mode": mode,
                "mode_name": (
                    self.SUPPORTED_MODES[mode]
                ),
                "tax_base": round(
                    tax_base,
                    2
                ),
                "tax_rate": round(
                    rate,
                    2
                ),
                "minimum_tax_rate": round(
                    normalized_minimum_rate,
                    2
                ),
                "regular_tax": round(
                    regular_tax,
                    2
                ),
                "minimum_tax": round(
                    minimum_tax,
                    2
                ),
                "tax_amount": round(
                    tax_amount,
                    2
                )
            }

    @staticmethod
    def _normalize_amount(value):
        if value in (
            None,
            ""
        ):
            return 0.0

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

    @staticmethod
    def _normalize_rate(
        value,
        default
    ):
        if value is None:
            value = default

        if isinstance(
            value,
            bool
        ):
            return None

        try:
            rate = float(
                value
            )
        except (
            TypeError,
            ValueError
        ):
            return None

        if (
            not math.isfinite(
                rate
            )
            or rate < 0.0
            or rate > 100.0
        ):
            return None

        return rate

    @staticmethod
    def _invalid_result():
        return {
            "error": True,
            "message": (
                "Некорректный результат расчёта налога"
            )
        }
