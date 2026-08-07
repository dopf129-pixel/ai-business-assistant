from datetime import date, datetime, timedelta


class AnalysisPeriodService:

    PERIODS = {
        "TODAY": {
            "label": "Сегодня",
            "days": 1
        },
        "7D": {
            "label": "Последние 7 дней",
            "days": 7
        },
        "28D": {
            "label": "Последние 28 дней",
            "days": 28
        },
        "56D": {
            "label": "Последние 56 дней",
            "days": 56
        },
        "90D": {
            "label": "Последние 90 дней",
            "days": 90
        },
        "ALL": {
            "label": "За всё время",
            "days": None
        }
    }

    def normalize_date(
        self,
        value
    ):

        if value is None:
            return date.today()

        if isinstance(
            value,
            datetime
        ):
            return value.date()

        if isinstance(
            value,
            date
        ):
            return value

        return datetime.strptime(
            str(value),
            "%Y-%m-%d"
        ).date()

    def get_period(
        self,
        period_code,
        date_to=None
    ):

        period_code = str(
            period_code or ""
        ).upper()

        if period_code not in self.PERIODS:

            return {
                "error": True,
                "message": (
                    "Неизвестный период анализа"
                )
            }

        period_config = (
            self.PERIODS[
                period_code
            ]
        )

        end_date = self.normalize_date(
            date_to
        )

        days = period_config[
            "days"
        ]

        if days is None:

            start_date = None

        else:

            start_date = (
                end_date
                - timedelta(
                    days=days - 1
                )
            )

        return {
            "error": False,
            "code": period_code,
            "label": period_config[
                "label"
            ],
            "days": days,
            "date_from": (
                start_date.isoformat()
                if start_date
                else None
            ),
            "date_to": (
                end_date.isoformat()
            )
        }

    def get_previous_period(
        self,
        period_code,
        date_to=None
    ):

        current = self.get_period(
            period_code=period_code,
            date_to=date_to
        )

        if current.get(
            "error"
        ):
            return current

        if current.get(
            "days"
        ) is None:

            return {
                "error": True,
                "message": (
                    "Для периода «За всё время» "
                    "нельзя автоматически построить "
                    "предыдущий период"
                )
            }

        current_start = (
            self.normalize_date(
                current[
                    "date_from"
                ]
            )
        )

        previous_end = (
            current_start
            - timedelta(
                days=1
            )
        )

        previous = self.get_period(
            period_code=period_code,
            date_to=previous_end
        )

        if previous.get(
            "error"
        ):
            return previous

        previous[
            "label"
        ] = (
            "Предыдущий период: "
            f'{previous["label"]}'
        )

        return previous

    def get_available_periods(
        self
    ):

        return [
            {
                "code": code,
                "label": config[
                    "label"
                ],
                "days": config[
                    "days"
                ]
            }
            for code, config
            in self.PERIODS.items()
        ]