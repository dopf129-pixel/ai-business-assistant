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
        items,
        page=1,
        total_pages=1,
        include_learning_summary=False,
        include_task_drafts=False
    ):
        buttons = [
            {
                "text": str(
                    item.get("text")
                    if isinstance(item, dict)
                    else item
                ),
                "callback": (
                    "product_decision:"
                    + str(
                        item.get("sku")
                        if isinstance(item, dict)
                        else item
                    )
                )
            }
            for item in (items or [])
        ]

        if include_learning_summary:
            buttons.append({
                "text": "📚 Итоги обучения",
                "callback": "product_decision_learning_summary",
            })

        if include_task_drafts:
            buttons.append({
                "text": "📋 Черновики задач",
                "callback": "product_action_task_drafts",
            })

        if page > 1:
            buttons.append({
                "text": "⬅️ Назад",
                "callback": "product_decisions_page:" + str(page - 1),
            })
        if page < total_pages:
            buttons.append({
                "text": "Вперёд ➡️",
                "callback": "product_decisions_page:" + str(page + 1),
            })

        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": buttons
        }

    def build_product_decision_feedback_keyboard(self, sku, proposal=None):
        sku = str(sku)
        buttons = []
        proposal = proposal or {}
        aliases = {
            "REVIEW_REPLENISHMENT": "r",
            "REVIEW_UNIT_ECONOMICS": "e",
            "REVIEW_MARGIN": "m",
        }
        alias = aliases.get(proposal.get("proposal_type"))
        if proposal.get("action_required") and alias:
            buttons.extend([
                {
                    "text": "✅ Подтвердить шаг",
                    "callback": "product_proposal:yes:" + alias + ":" + sku,
                },
                {
                    "text": "✖️ Отклонить шаг",
                    "callback": "product_proposal:no:" + alias + ":" + sku,
                },
            ])
        buttons.extend([
            {
                "text": "👍 Полезно",
                "callback": (
                    "product_decision_feedback:useful:" + sku
                ),
            },
            {
                "text": "👎 Неактуально",
                "callback": (
                    "product_decision_feedback:not_relevant:" + sku
                ),
            },
            {
                "text": "📚 История решений",
                "callback": "product_decision_history:" + sku,
            },
        ])
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": buttons,
        }

    def build_product_task_drafts_keyboard(self, drafts):
        buttons = []
        for draft in drafts or []:
            if draft.get("status") == "ARCHIVED":
                continue
            draft_id = str(draft.get("draft_id") or "")
            if not draft_id:
                continue
            buttons.append({
                "text": "🗄 Архивировать " + str(draft.get("sku") or "—"),
                "callback": "product_task_draft:archive:" + draft_id,
            })
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": buttons,
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
