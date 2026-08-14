class AssistantActionGeneratorService:


    def __init__(
        self,
        memory_service=None
    ):

        self.memory_service = (
            memory_service
        )



    def generate(
        self,
        request
    ):


        memory_context = []


        if self.memory_service:


            memory_context = (
                self.memory_service
                .recall(
                    request
                )
            )



        action = {

            "title":
                request,

            "type":
                "task"

        }



        return {

            "error":
                False,

            "action":
                action,

            "memory":
                memory_context

        }