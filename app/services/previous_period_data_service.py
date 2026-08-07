from services.analysis_period_service import (
    AnalysisPeriodService
)


class PreviousPeriodDataService:

    def __init__(
        self,
        data_loader=None
    ):

        self.period_service = (
            AnalysisPeriodService()
        )

        self.data_loader = (
            data_loader
        )


    def get_previous_period(
        self,
        period_code,
        date_to
    ):

        return (
            self.period_service
            .get_previous_period(
                period_code,
                date_to
            )
        )


    def load_previous_data(
        self,
        period_code,
        date_to
    ):

        previous_period = (
            self.get_previous_period(
                period_code,
                date_to
            )
        )


        if previous_period.get(
            "error"
        ):

            return previous_period


        if not self.data_loader:

            return {
                "error": False,
                "period": previous_period,
                "data": [],
                "message": (
                    "Источник данных "
                    "не подключён"
                )
            }


        try:

            data = (
                self.data_loader(
                    previous_period.get(
                        "date_from"
                    ),
                    previous_period.get(
                        "date_to"
                    )
                )
            )


        except Exception as error:

            return {
                "error": True,
                "message": (
                    "Ошибка загрузки "
                    "предыдущего периода: "
                    f"{error}"
                )
            }


        return {
            "error": False,
            "period": previous_period,
            "data": data
        }