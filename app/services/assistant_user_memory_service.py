class AssistantUserMemoryService:


    def __init__(
        self,
        storage_service=None
    ):

        self.storage_service = (
            storage_service
        )


        if self.storage_service:

            self.memory = (
                self.storage_service
                .load()
            )

        else:

            self.memory = {}



    def remember(
        self,
        key,
        value
    ):

        self.memory[key] = value


        if self.storage_service:

            self.storage_service.save(
                self.memory
            )


        return {
            "error": False,
            "saved": True
        }



    def get(
        self,
        key
    ):

        if key not in self.memory:

            return {
                "error": True,
                "message": "Память не найдена"
            }


        return {
            "error": False,
            "value": self.memory[key]
        }



    def all(
        self
    ):

        return {
            "error": False,
            "memory": self.memory
        }