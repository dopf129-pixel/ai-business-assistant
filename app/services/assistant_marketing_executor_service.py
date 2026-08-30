class AssistantMarketingExecutorService:


    def execute(
        self,
        action
    ):


        if not isinstance(
            action,
            dict
        ):

            return {
                "error": True,
                "message": "Недостаточно данных для анализа маркетинга"
            }


        context = action.get(
            "context"
        )


        if not isinstance(
            context,
            dict
        ):

            return {
                "error": True,
                "message": "Недостаточно данных для анализа маркетинга"
            }


        evidence = context.get(
            "evidence"
        )


        if (
            not isinstance(
                evidence,
                (list, tuple)
            )
            or not evidence
        ):

            return {
                "error": True,
                "message": "Недостаточно данных для анализа маркетинга"
            }


        normalized = []


        for item in evidence:

            if (
                not isinstance(
                    item,
                    str
                )
                or not item.strip()
            ):

                return {
                    "error": True,
                    "message": "Недостаточно данных для анализа маркетинга"
                }

            normalized.append(
                item.strip()
            )


        details = list(
            normalized
        )


        reason = context.get(
            "reason"
        )


        if (
            isinstance(
                reason,
                str
            )
            and reason.strip()
        ):

            details.append(
                "Причина анализа: "
                + reason.strip()
            )


        return {
            "error": False,
            "result": {
                "type": "marketing",
                "message": "Маркетинговые данные подготовлены",
                "details": details,
                "priority": action.get(
                    "priority",
                    "NORMAL"
                )
            }
        }
