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

        mode = str(mode or "").upper()

        revenue = float(
            revenue or 0
        )

        gross_profit = float(
            gross_profit or 0
        )

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
                "mode": mode,
                "mode_name": (
                    self.SUPPORTED_MODES[mode]
                ),
                "tax_base": 0.0,
                "tax_rate": 0.0,
                "tax_amount": 0.0
            }

        if mode == "USN_INCOME":

            rate = (
                6.0
                if tax_rate is None
                else float(tax_rate)
            )

            tax_base = max(
                0.0,
                revenue
            )

            tax_amount = (
                tax_base
                * rate
                / 100
            )

            return {
                "error": False,
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

            rate = (
                15.0
                if tax_rate is None
                else float(tax_rate)
            )

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
                * float(
                    minimum_tax_rate
                )
                / 100
            )

            tax_amount = max(
                regular_tax,
                minimum_tax
            )

            return {
                "error": False,
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
                    float(
                        minimum_tax_rate
                    ),
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