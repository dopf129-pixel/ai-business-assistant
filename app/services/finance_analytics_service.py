from datetime import datetime, timedelta


class FinanceAnalyticsService:

    def __init__(
        self,
        finance_service
    ):

        self.finance_service = (
            finance_service
        )

    def _to_date(
        self,
        value
    ):

        if isinstance(
            value,
            datetime
        ):
            return value.date()

        return datetime.strptime(
            str(value),
            "%Y-%m-%d"
        ).date()

    def _date_range(
        self,
        date_from,
        date_to
    ):

        start = self._to_date(
            date_from
        )

        end = self._to_date(
            date_to
        )

        current = start

        while current <= end:

            yield current.isoformat()

            current += timedelta(
                days=1
            )

    def _empty_result(
        self,
        date_from,
        date_to,
        sku
    ):

        return {
            "error": False,
            "date_from": date_from,
            "date_to": date_to,
            "sku": (
                str(sku)
                if sku is not None
                else None
            ),
            "days_requested": 0,
            "days_loaded": 0,
            "days_failed": 0,
            "operations": 0,
            "sales_count": 0,
            "gross_sales": 0.0,
            "net_accrual": 0.0,
            "commission": 0.0,
            "logistics": 0.0,
            "acquiring": 0.0,
            "other_fees": 0.0,
            "fee_breakdown": {},
            "errors": []
        }

    def get_period_finance(
        self,
        date_from,
        date_to,
        sku=None
    ):

        if not date_from or not date_to:

            return {
                "error": True,
                "message": (
                    "Для финансового периода "
                    "необходимо указать date_from "
                    "и date_to"
                )
            }

        try:

            dates = list(
                self._date_range(
                    date_from,
                    date_to
                )
            )

        except (
            TypeError,
            ValueError
        ):

            return {
                "error": True,
                "message": (
                    "Некорректный диапазон дат"
                )
            }

        if not dates:

            return {
                "error": True,
                "message": (
                    "Пустой диапазон дат"
                )
            }

        result = self._empty_result(
            date_from=str(
                date_from
            ),
            date_to=str(
                date_to
            ),
            sku=sku
        )

        result[
            "days_requested"
        ] = len(
            dates
        )

        for current_date in dates:

            daily = (
                self.finance_service
                .get_daily_finance(
                    current_date,
                    sku
                )
            )

            if daily.get("error"):

                result[
                    "days_failed"
                ] += 1

                result[
                    "errors"
                ].append(
                    {
                        "date": current_date,
                        "message": daily.get(
                            "message",
                            "Неизвестная ошибка"
                        )
                    }
                )

                continue

            result[
                "days_loaded"
            ] += 1

            result[
                "operations"
            ] += int(
                daily.get(
                    "operations",
                    0
                )
            )

            result[
                "sales_count"
            ] += int(
                daily.get(
                    "sales_count",
                    0
                )
            )

            for field in (
                "gross_sales",
                "net_accrual",
                "commission",
                "logistics",
                "acquiring",
                "other_fees"
            ):

                result[
                    field
                ] += float(
                    daily.get(
                        field,
                        0
                    )
                    or 0
                )

            fee_breakdown = (
                daily.get(
                    "fee_breakdown",
                    {}
                )
                or {}
            )

            for (
                name,
                amount
            ) in fee_breakdown.items():

                result[
                    "fee_breakdown"
                ][name] = (
                    result[
                        "fee_breakdown"
                    ].get(
                        name,
                        0.0
                    )
                    + float(
                        amount or 0
                    )
                )

        for field in (
            "gross_sales",
            "net_accrual",
            "commission",
            "logistics",
            "acquiring",
            "other_fees"
        ):

            result[
                field
            ] = round(
                result[
                    field
                ],
                2
            )

        result[
            "fee_breakdown"
        ] = {
            name: round(
                amount,
                2
            )
            for (
                name,
                amount
            )
            in result[
                "fee_breakdown"
            ].items()
        }

        if (
            result["days_loaded"] == 0
            and result["days_failed"] > 0
        ):

            result["error"] = True

            result["message"] = (
                "Не удалось получить "
                "финансовые данные "
                "ни за один день периода"
            )

        return result