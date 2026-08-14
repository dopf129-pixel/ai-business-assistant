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


        self.memory = (
            self.context.get(
                "memory",
                []
            )
        )



    def remember(
        self,
        experience
    ):


        item = {

            "action":
                experience.get(
                    "action"
                ),

            "status":
                experience.get(
                    "status"
                ),

            "experience":
                experience

        }


        self.memory.append(
            item
        )


        self.context["memory"] = (
            self.memory
        )


        if self.storage_service:

            self.storage_service.save(
                self.context
            )


        return {

            "error":
                False,

            "memory":
                item,

            "count":
                len(
                    self.memory
                )

        }



    def recall(
        self,
        action=None
    ):


        if action is None:

            return self.memory



        results = []


        for item in self.memory:


            if item.get(
                "action"
            ) == action:


                results.append(
                    item
                )


        return results



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

            "error":
                False,

            "saved":
                True

        }



    def get(
        self,
        key
    ):


        if key not in self.context:


            return {

                "error":
                    True,

                "message":
                    "Контекст не найден"

            }



        return {

            "error":
                False,

            "value":
                self.context[key]

        }



    def clear(
        self
    ):


        self.context = {}

        self.memory = []


        if self.storage_service:

            self.storage_service.save(
                self.context
            )


        return {

            "error":
                False,

            "cleared":
                True

        }