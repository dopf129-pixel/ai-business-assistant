class AssistantEntryService:


    def __init__(
        self,
        main_flow_service
    ):

        self.main_flow_service = (
            main_flow_service
        )



    def handle(
        self,
        text,
        context=None
    ):


        report = {
            "sales_down": True,
            "low_stock": True
        }



        return (
            self.main_flow_service
            .process(
                text,
                report,
                context
            )
        )