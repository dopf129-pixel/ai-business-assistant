class RetryPolicyService:


    def __init__(
        self
    ):

        self.max_attempts = 3


        self.retryable_errors = [

            "timeout",

            "connection",

            "temporary",

            "network",

            "unavailable"

        ]


        self.non_retryable_errors = [

            "permission",

            "invalid",

            "forbidden",

            "not found",

            "unauthorized"

        ]



    def should_retry(
        self,
        error
    ):


        error_text = str(
            error
        ).lower()



        for item in self.non_retryable_errors:


            if item in error_text:

                return False



        for item in self.retryable_errors:


            if item in error_text:

                return True



        return False



    def can_retry(
        self,
        attempt
    ):


        return (
            attempt
            <
            self.max_attempts
        )



    def get_decision(
        self,
        error
    ):


        if self.should_retry(
            error
        ):


            return {

                "retry":
                    True,

                "reason":
                    "Ошибка считается временной"

            }



        return {

            "retry":
                False,

            "reason":
                "Ошибка не подходит для повторного выполнения"

        }