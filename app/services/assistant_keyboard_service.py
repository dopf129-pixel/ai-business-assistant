class AssistantKeyboardService:


    def build_main_keyboard(
        self
    ):

        return {
            "error": False,

            "type": "inline_keyboard",

            "buttons": [
                {
                    "text": "📊 Анализ",
                    "callback": "analyze"
                },
                {
                    "text": "📋 План действий",
                    "callback": "plan"
                },
                {
                    "text": "📜 История",
                    "callback": "history"
                },
                {
                    "text": "🧠 Память",
                    "callback": "memory"
                },
                {
                    "text": "💰 Юнит-экономика товаров",
                    "callback": "unit_economics"
                },
                {
                    "text": "🎯 Решения по товарам",
                    "callback": "product_decisions"
                },
                {
                    "text": "↩️ Расходы на возвраты",
                    "callback": "returns_finance_impact"
                }
            ]
        }


    def build_unit_economics_keyboard(
        self,
        skus
    ):

        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {
                    "text": str(sku),
                    "callback": (
                        "unit_economics:"
                        + str(sku)
                    )
                }
                for sku in (skus or [])
            ]
        }


    def build_product_decisions_keyboard(
        self,
        skus
    ):

        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {
                    "text": str(sku),
                    "callback": (
                        "product_decision:"
                        + str(sku)
                    )
                }
                for sku in (skus or [])
            ]
        }


    def build_returns_finance_impact_keyboard(
        self,
        skus
    ):

        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {
                    "text": str(sku),
                    "callback": (
                        "returns_finance_impact:"
                        + str(sku)
                    )
                }
                for sku in (skus or [])
            ]
        }
