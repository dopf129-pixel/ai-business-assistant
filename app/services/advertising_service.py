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

        try:
            advertising_cost = float(
                advertising_cost
            )

        except (
            TypeError,
            ValueError
        ):

            return {
                "error": True,
                "message": (
                    "Некорректная сумма расходов "
                    "на рекламу"
                )
            }

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

            try:
                total_cost += float(
                    campaign.get(
                        "cost",
                        0
                    )
                )

            except (
                TypeError,
                ValueError,
                AttributeError
            ):
                continue

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