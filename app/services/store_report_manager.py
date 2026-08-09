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

        return (
            self.orchestrator
            .build(
                period_code=period_code,
                date_to=date_to,
                products=products
            )
        )