class StoreReportHistoryService:

    def __init__(
        self
    ):

        self.reports = []


    def save_report(
        self,
        report
    ):

        self.reports.append(
            report
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