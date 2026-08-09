class AssistantMemoryService:


    def __init__(
        self,
        storage_service=None
    ):

        self.storage_service = (
            storage_service
        )


        if self.storage_service:

            self.context = (
                self.storage_service
                .load()
            )

        else:

            self.context = {}



    def save(
        self,
        key,
        value
    ):

        self.context[key] = value


        if self.storage_service:

            self.storage_service.save(
                self.context
            )


        return {
            "error": False,
            "saved": True
        }



    def get(
        self,
        key
    ):

        if key not in self.context:

            return {
                "error": True,
                "message": "Контекст не найден"
            }


        return {
            "error": False,
            "value": self.context[key]
        }



    def clear(
        self
    ):

        self.context = {}


        if self.storage_service:

            self.storage_service.save(
                self.context
            )


        return {
            "error": False,
            "cleared": True
        }