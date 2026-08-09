class StoreReportManager:

    def __init__(
        self,
        orchestrator
    ):

        self.orchestrator = (
            orchestrator
        )


    def build_store_report(
        self,
        period_code,
        date_to,
        products
    ):

        if not period_code:

            return {
                "error": True,
                "message": "Не указан период анализа"
            }


        if products is None:

            return {
                "error": True,
                "message": "Не переданы товары"
            }


        return (
            self.orchestrator
            .build(
                period_code=period_code,
                date_to=date_to,
                products=products
            )
        )