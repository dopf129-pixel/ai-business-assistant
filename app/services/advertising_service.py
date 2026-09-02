import math


class AdvertisingService:

    def calculate(
        self,
        advertising_cost=0
    ):

        if advertising_cost in (
            None,
            ""
        ):

            return {
                "error": False,
                "configured": False,
                "advertising_cost": None
            }

        if isinstance(
            advertising_cost,
            bool
        ):

            return self._invalid_amount()

        try:
            advertising_cost = float(
                advertising_cost
            )

        except (
            TypeError,
            ValueError
        ):

            return self._invalid_amount()

        if not math.isfinite(
            advertising_cost
        ):

            return self._invalid_amount()

        if advertising_cost < 0:

            return {
                "error": True,
                "message": (
                    "Расходы на рекламу "
                    "не могут быть отрицательными"
                )
            }

        return {
            "error": False,
            "configured": True,
            "advertising_cost": round(
                advertising_cost,
                2
            )
        }

    def total(
        self,
        campaigns
    ):

        if not campaigns:

            return {
                "error": False,
                "advertising_cost": 0.0,
                "campaigns": 0
            }

        total_cost = 0.0

        for campaign in campaigns:

            if not isinstance(
                campaign,
                dict
            ):
                continue

            raw_cost = campaign.get(
                "cost",
                0
            )

            if isinstance(
                raw_cost,
                bool
            ):
                continue

            try:
                cost = float(
                    raw_cost
                )

            except (
                TypeError,
                ValueError
            ):
                continue

            if (
                not math.isfinite(
                    cost
                )
                or cost < 0
            ):
                continue

            total_cost += cost

            if not math.isfinite(
                total_cost
            ):

                return {
                    "error": True,
                    "message": (
                        "Некорректный итог расходов "
                        "на рекламу"
                    )
                }

        return {
            "error": False,
            "campaigns": len(
                campaigns
            ),
            "advertising_cost": round(
                total_cost,
                2
            )
        }

    @staticmethod
    def _invalid_amount():

        return {
            "error": True,
            "message": (
                "Некорректная сумма расходов "
                "на рекламу"
            )
        }
