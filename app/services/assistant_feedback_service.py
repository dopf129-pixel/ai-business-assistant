class AssistantFeedbackService:


    def __init__(
        self,
        memory_service=None
    ):

        self.experiences = []

        self.memory_service = (
            memory_service
        )



    def record(
        self,
        result
    ):


        experience = {

            "action":
                result.get(
                    "action"
                ),

            "status":
                result.get(
                    "status"
                ),

            "experience":
                self._analyze(
                    result
                )

        }


        self.experiences.append(
            experience
        )


        if self.memory_service:


            self.memory_service.remember(

                experience

            )



        return {

            "error":
                False,

            "experience":
                experience,

            "count":
                len(
                    self.experiences
                )

        }



    def _analyze(
        self,
        result
    ):


        status = result.get(
            "status"
        )


        if status == "DONE":

            return "successful execution"



        if status == "FAILED":

            return "failed execution"



        return "unknown result"