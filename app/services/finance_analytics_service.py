from datetime import datetime, timedelta
import math


class FinanceAnalyticsService:

    AMOUNT_FIELDS = (
        "gross_sales",
        "net_accrual",
        "commission",
        "logistics",
        "acquiring",
        "other_fees",
    )

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

            try:
                daily = (
                    self.finance_service
                    .get_daily_finance(
                        current_date,
                        sku
                    )
                )
            except Exception:
                self._mark_failed_day(
                    result,
                    current_date,
                    "Финансовые данные дня недоступны"
                )
                continue

            if not isinstance(
                daily,
                dict
            ):
                self._mark_failed_day(
                    result,
                    current_date,
                    "Некорректные финансовые данные дня"
                )
                continue

            error_marker = daily.get(
                "error"
            )

            if (
                error_marker is not None
                and not isinstance(
                    error_marker,
                    bool
                )
            ):
                self._mark_failed_day(
                    result,
                    current_date,
                    "Некорректные финансовые данные дня"
                )
                continue

            if error_marker is True:
                message = daily.get(
                    "message"
                )

                if not isinstance(
                    message,
                    str
                ) or not message.strip():
                    message = (
                        "Неизвестная ошибка"
                    )

                self._mark_failed_day(
                    result,
                    current_date,
                    message
                )
                continue

            normalized = (
                self._normalize_daily(
                    daily
                )
            )

            if normalized is None:
                self._mark_failed_day(
                    result,
                    current_date,
                    "Некорректные финансовые данные дня"
                )
                continue

            next_amounts = {}

            for field in self.AMOUNT_FIELDS:
                next_value = (
                    result[field]
                    + normalized[field]
                )

                if not math.isfinite(
                    next_value
                ):
                    self._mark_failed_day(
                        result,
                        current_date,
                        "Некорректный итог финансового периода"
                    )
                    return self._aggregate_failure(
                        result
                    )

                next_amounts[field] = (
                    next_value
                )

            next_fee_breakdown = dict(
                result[
                    "fee_breakdown"
                ]
            )

            for (
                name,
                amount
            ) in normalized[
                "fee_breakdown"
            ].items():

                next_value = (
                    next_fee_breakdown.get(
                        name,
                        0.0
                    )
                    + amount
                )

                if not math.isfinite(
                    next_value
                ):
                    self._mark_failed_day(
                        result,
                        current_date,
                        "Некорректный итог финансового периода"
                    )
                    return self._aggregate_failure(
                        result
                    )

                next_fee_breakdown[
                    name
                ] = next_value

            result[
                "days_loaded"
            ] += 1

            result[
                "operations"
            ] += normalized[
                "operations"
            ]

            result[
                "sales_count"
            ] += normalized[
                "sales_count"
            ]

            for field in self.AMOUNT_FIELDS:
                result[field] = (
                    next_amounts[field]
                )

            result[
                "fee_breakdown"
            ] = next_fee_breakdown

        for field in self.AMOUNT_FIELDS:

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

    def _normalize_daily(
        self,
        daily
    ):

        operations = self._count(
            daily.get(
                "operations",
                0
            )
        )

        sales_count = self._count(
            daily.get(
                "sales_count",
                0
            )
        )

        if (
            operations is None
            or sales_count is None
        ):
            return None

        normalized = {
            "operations": operations,
            "sales_count": sales_count,
        }

        for field in self.AMOUNT_FIELDS:
            value = self._number(
                daily.get(
                    field,
                    0
                )
            )

            if value is None:
                return None

            normalized[
                field
            ] = value

        fee_breakdown = daily.get(
            "fee_breakdown",
            {}
        )

        if fee_breakdown is None:
            fee_breakdown = {}

        if not isinstance(
            fee_breakdown,
            dict
        ):
            return None

        normalized_fees = {}

        for (
            name,
            amount
        ) in fee_breakdown.items():

            value = self._number(
                amount
            )

            if value is None:
                return None

            normalized_fees[
                name
            ] = value

        normalized[
            "fee_breakdown"
        ] = normalized_fees

        return normalized

    @staticmethod
    def _count(
        value
    ):

        if isinstance(
            value,
            bool
        ):
            return None

        if isinstance(
            value,
            int
        ):
            return (
                value
                if value >= 0
                else None
            )

        try:
            number = float(
                value
            )
        except (
            TypeError,
            ValueError
        ):
            return None

        if (
            not math.isfinite(
                number
            )
            or number < 0
            or not number.is_integer()
        ):
            return None

        return int(
            number
        )

    @staticmethod
    def _number(
        value
    ):

        if isinstance(
            value,
            bool
        ):
            return None

        if value in (
            None,
            ""
        ):
            return 0.0

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
    def _mark_failed_day(
        result,
        current_date,
        message
    ):

        result[
            "days_failed"
        ] += 1

        result[
            "errors"
        ].append(
            {
                "date": current_date,
                "message": message,
            }
        )

    @staticmethod
    def _aggregate_failure(
        result
    ):

        result["error"] = True
        result[
            "code"
        ] = (
            "FINANCE_PERIOD_AGGREGATE_INVALID"
        )
        result[
            "message"
        ] = (
            "Некорректный итог финансового периода"
        )

        return result
