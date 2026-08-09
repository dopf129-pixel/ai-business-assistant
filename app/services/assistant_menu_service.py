class AssistantMenuService:


    def get_menu(
        self
    ):

        return {
            "error": False,
            "buttons": [
                {
                    "id": "analyze",
                    "title": "📊 Анализ"
                },
                {
                    "id": "plan",
                    "title": "📋 План действий"
                },
                {
                    "id": "history",
                    "title": "📜 История"
                },
                {
                    "id": "memory",
                    "title": "🧠 Память"
                }
            ]
        }