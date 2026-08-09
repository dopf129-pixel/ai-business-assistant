class StoreReportHistoryService:

    def __init__(
        self,
        storage_service=None
    ):

        self.storage_service = (
            storage_service
        )

        if self.storage_service:

            self.reports = (
                self.storage_service
                .load()
            )

        else:

            self.reports = []


    def save_report(
        self,
        report
    ):

        self.reports.append(
            report
        )


        if self.storage_service:

            self.storage_service.save(
                self.reports
            )


        return {
            "error": False,
            "saved": True,
            "count": len(
                self.reports
            )
        }


    def get_report(
        self,
        index
    ):

        if (
            index < 0
            or
            index >= len(
                self.reports
            )
        ):

            return {
                "error": True,
                "message": "Отчёт не найден"
            }


        return {
            "error": False,
            "report": (
                self.reports[index]
            )
        }


    def list_reports(
        self
    ):

        return {
            "error": False,
            "reports": (
                self.reports
            ),
            "count": len(
                self.reports
            )
        }