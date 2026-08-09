class AssistantMemoryService:


    def __init__(
        self
    ):

        self.context = {}


    def save(
        self,
        key,
        value
    ):

        self.context[key] = value


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


        return {
            "error": False,
            "cleared": True
        }