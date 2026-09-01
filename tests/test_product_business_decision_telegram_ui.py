from services.assistant_keyboard_service import AssistantKeyboardService
from services.assistant_button_handler_service import AssistantButtonHandlerService


class StubAssistant:
    def ask(self, message, user_id=None):
        return {"error": False, "message": message}


class StubProductService:
    def __init__(self, products=None):
        self.products = products

    def load_products(self):
        return self.products or [
            {
                "product_id": "101",
                "offer_id": "hook-2",
                "sku": "3921245627",
            },
            {
                "product_id": "102",
                "offer_id": "hook-3",
                "sku": "3921245628",
            },
        ]


class StubDecisionQuery:
    def __init__(self, result=None, products=None):
        self.product_service = StubProductService(products=products)
        self.result = result or {
            "error": False,
            "code": None,
            "product_id": "101",
            "sku": "hook-2",
            "decision_type": "REPLENISH_HIGH_PRIORITY",
            "priority": "CRITICAL",
            "reasons": [
                "DAYS_OF_STOCK_CRITICAL",
                "POSITIVE_UNIT_PROFIT",
            ],
            "confidence": "HIGH",
            "missing_data": ["advertising", "storage", "returns"],
            "sales_velocity": 4.0,
            "sales_trend": "GROWING",
            "current_stock": 8,
            "days_of_stock": 2.0,
            "stock_priority": "CRITICAL",
            "decision_profit_per_unit": 35.10,
            "decision_margin_percent": 36.56,
        }
        self.calls = []
        self.decision_history_service = None
        self.action_proposal_confirmation_service = None
        self.action_task_draft_service = None
        self.task_draft_readiness_service = None

    def query(self, sku):
        self.calls.append(sku)
        result = dict(self.result)
        result.setdefault("sku", sku)
        return result

    def query_all(self):
        decisions = []
        for product in self.product_service.load_products():
            sku = product.get("offer_id") or product.get("sku")
            decision = dict(self.result)
            decision["sku"] = sku
            decisions.append(decision)
        counts = {}
        proposal_counts = {}
        actionable = 0
        for decision in decisions:
            decision_type = decision["decision_type"]
            counts[decision_type] = counts.get(decision_type, 0) + 1
            proposal = decision.get("action_proposal") or {}
            proposal_type = proposal.get("proposal_type")
            if proposal_type:
                proposal_counts[proposal_type] = (
                    proposal_counts.get(proposal_type, 0) + 1
                )
            if proposal.get("action_required"):
                actionable += 1
        return {
            "error": False,
            "code": None,
            "total": len(decisions),
            "counts": counts,
            "proposal_counts": proposal_counts,
            "actionable_proposals_count": actionable,
            "decisions": decisions,
        }


def _handler(
    result=None,
    products=None,
    history_service=None,
    confirmation_service=None,
):
    keyboard = AssistantKeyboardService()
    query = StubDecisionQuery(result=result, products=products)
    query.decision_history_service = history_service
    query.action_proposal_confirmation_service = confirmation_service
    query.action_task_draft_service = getattr(
        confirmation_service,
        "task_draft_service",
        None,
    )
    handler = AssistantButtonHandlerService(
        assistant=StubAssistant(),
        keyboard_service=keyboard,
        product_business_decision_query=query,
    )
    return handler, keyboard, query


def test_main_keyboard_contains_product_decisions_and_preserves_existing_buttons():
    keyboard = AssistantKeyboardService()
    callbacks = [
        item["callback"]
        for item in keyboard.build_main_keyboard()["buttons"]
    ]

    assert "product_decisions" in callbacks
    for callback in (
        "analyze",
        "plan",
        "history",
        "memory",
        "unit_economics",
    ):
        assert callback in callbacks


def test_product_decisions_menu_shows_ranked_decision_overview():
    handler, _, _ = _handler()

    result = handler.handle("product_decisions")

    assert result["error"] is False
    assert "🎯 Решения по товарам" in result["message"]
    assert "Всего товаров: 2" in result["message"]
    assert "Срочно пополнить: 2" in result["message"]
    assert "Товары отсортированы по срочности." in result["message"]
    callbacks = [
        item["callback"]
        for item in result["keyboard"]["buttons"]
    ]
    assert callbacks == [
        "product_decision:hook-2",
        "product_decision:hook-3",
    ]
    labels = [
        item["text"]
        for item in result["keyboard"]["buttons"]
    ]
    assert labels == [
        "🔴 hook-2 — Пополнить срочно",
        "🔴 hook-3 — Пополнить срочно",
    ]


def test_product_decisions_menu_paginates_large_assortment():
    products = [
        {
            "product_id": str(index),
            "offer_id": f"item-{index}",
            "sku": str(1000 + index),
        }
        for index in range(1, 11)
    ]
    handler, _, _ = _handler(products=products)

    first = handler.handle("product_decisions")
    first_callbacks = [
        item["callback"]
        for item in first["keyboard"]["buttons"]
    ]

    assert "Страница: 1 из 2" in first["message"]
    assert first_callbacks[:8] == [
        f"product_decision:item-{index}"
        for index in range(1, 9)
    ]
    assert first_callbacks[-1] == "product_decisions_page:2"

    second = handler.handle("product_decisions_page:2")
    second_callbacks = [
        item["callback"]
        for item in second["keyboard"]["buttons"]
    ]

    assert "Страница: 2 из 2" in second["message"]
    assert second_callbacks == [
        "product_decision:item-9",
        "product_decision:item-10",
        "product_decisions_page:1",
    ]


def test_product_decision_callback_calls_query_and_formats_decision():
    handler, _, query = _handler()

    result = handler.handle("product_decision:hook-2")

    assert query.calls == ["hook-2"]
    assert result["error"] is False
    assert result["decision"]["decision_type"] == "REPLENISH_HIGH_PRIORITY"
    assert "🎯 Решение по товару" in result["message"]
    assert "hook-2" in result["message"]
    assert "Высокий приоритет пополнения" in result["message"]
    assert "Артикул:\nhook-2" in result["message"]
    assert "Тип:" not in result["message"]
    assert "Приоритет:\nКритический" in result["message"]
    assert "Скорость продаж: 4 шт./день" in result["message"]
    assert "Остаток: 8 шт." in result["message"]
    assert "Запас: 2 дн." in result["message"]
    assert "Прибыль с 1 шт.: 35.10 ₽" in result["message"]
    assert "Маржа: 36.56%" in result["message"]
    assert "Уверенность:\nВысокая" in result["message"]
    assert "DAYS_OF_STOCK_CRITICAL" not in result["message"]
    assert "Остаток критически низкий" in result["message"]
    assert "Реклама" in result["message"]
    assert "Хранение" in result["message"]
    assert "Возвраты" in result["message"]


def test_sku_not_found_returns_user_message():
    handler, _, _ = _handler(
        {
            "error": True,
            "code": "SKU_NOT_FOUND",
            "sku": "missing",
            "decision_type": "INSUFFICIENT_DATA",
            "priority": "NONE",
            "reasons": [],
            "confidence": "LOW",
            "missing_data": ["sku"],
        }
    )

    result = handler.handle("product_decision:missing")

    assert result["message"] == "Товар не найден"


def test_insufficient_data_returns_user_message():
    handler, _, _ = _handler(
        {
            "error": False,
            "code": "INSUFFICIENT_DATA",
            "product_id": "101",
            "sku": "hook-2",
            "decision_type": "INSUFFICIENT_DATA",
            "priority": "NONE",
            "reasons": [],
            "confidence": "LOW",
            "missing_data": ["profit_per_unit"],
        }
    )

    result = handler.handle("product_decision:hook-2")

    assert result["message"] == "Недостаточно данных для решения"


def test_product_decision_card_shows_returns_aware_economics():
    handler, _, _ = _handler(
        {
            "error": False,
            "code": None,
            "product_id": "101",
            "sku": "hook-2",
            "decision_type": "REPLENISH_HIGH_PRIORITY",
            "priority": "CRITICAL",
            "reasons": [
                "DAYS_OF_STOCK_CRITICAL",
                "POSITIVE_UNIT_PROFIT",
            ],
            "confidence": "MEDIUM",
            "missing_data": ["returns"],
            "economics_basis": "ESTIMATED_RETURNS",
            "decision_profit_per_unit": 33.98,
            "decision_margin_percent": 35.40,
            "returns_reserve_per_unit": 1.12,
            "returns_coverage_percent": 91.11,
        }
    )

    result = handler.handle("product_decision:hook-2")
    message = result["message"]

    assert "Прибыль с 1 шт.: 33.98 ₽" in message
    assert (
        "Основа расчёта:\n"
        "С исторической оценкой возвратов"
    ) in message
    assert "Возвраты и невыкупы: 1.12 ₽" in message
    assert "Финансовое покрытие: 91.11%" in message
    assert "Уверенность:\nСредняя" in message


def test_product_decision_card_shows_safe_manual_action_proposal():
    handler, _, _ = _handler(
        {
            "error": False,
            "code": None,
            "product_id": "101",
            "sku": "hook-2",
            "decision_type": "REPLENISH_HIGH_PRIORITY",
            "priority": "CRITICAL",
            "reasons": ["DAYS_OF_STOCK_CRITICAL"],
            "confidence": "HIGH",
            "missing_data": [],
            "action_proposal": {
                "available": True,
                "proposal_type": "REVIEW_REPLENISHMENT",
                "action_required": True,
                "requires_confirmation": True,
                "execution_allowed": False,
                "automation_status": "PROHIBITED",
            },
        }
    )

    message = handler.handle("product_decision:hook-2")["message"]

    assert "Следующий шаг:" in message
    assert "Проверить возможность пополнения" in message
    assert "⚠️ Требует ручного подтверждения." in message
    assert "REVIEW_REPLENISHMENT" not in message


def test_product_decisions_overview_counts_manual_reviews():
    handler, _, _ = _handler(
        {
            "error": False,
            "code": None,
            "product_id": "101",
            "sku": "hook-2",
            "decision_type": "REPLENISH_NORMAL",
            "priority": "HIGH",
            "reasons": ["DAYS_OF_STOCK_LOW"],
            "confidence": "HIGH",
            "missing_data": [],
            "action_proposal": {
                "available": True,
                "proposal_type": "REVIEW_REPLENISHMENT",
                "action_required": True,
                "requires_confirmation": True,
                "execution_allowed": False,
                "automation_status": "PROHIBITED",
            },
        }
    )

    message = handler.handle("product_decisions")["message"]

    assert "Предложений к ручной проверке: 2" in message


def test_product_decision_card_shows_previous_decision_after_change():
    handler, _, _ = _handler(
        {
            "error": False,
            "code": None,
            "product_id": "101",
            "sku": "hook-2",
            "decision_type": "INVESTIGATE_LOW_PROFIT",
            "priority": "HIGH",
            "reasons": ["NEGATIVE_UNIT_PROFIT"],
            "confidence": "HIGH",
            "missing_data": [],
            "decision_changed": True,
            "previous_decision_type": "REPLENISH_HIGH_PRIORITY",
        }
    )

    message = handler.handle("product_decision:hook-2")["message"]

    assert "Изменение решения:" in message
    assert (
        "Высокий приоритет пополнения → "
        "Проверить низкую прибыльность"
    ) in message
    assert "REPLENISH_HIGH_PRIORITY" not in message


def test_product_decision_card_explains_correlated_outcome():
    handler, _, _ = _handler(
        {
            "error": False,
            "code": None,
            "product_id": "101",
            "sku": "hook-2",
            "decision_type": "HOLD_STOCK",
            "priority": "LOW",
            "reasons": ["POSITIVE_UNIT_PROFIT"],
            "confidence": "HIGH",
            "missing_data": [],
            "decision_changed": True,
            "previous_decision_type": "REPLENISH_HIGH_PRIORITY",
            "previous_feedback": "USEFUL",
            "decision_outcome": "PRIORITY_DECREASED",
        }
    )

    message = handler.handle("product_decision:hook-2")["message"]

    assert "Наблюдение после прошлой оценки:" in message
    assert "Срочность рекомендации снизилась" in message
    assert "PRIORITY_DECREASED" not in message


class StubDecisionHistory:
    def __init__(self, result=None):
        self.result = result or {
            "error": False,
            "code": None,
            "sku": "hook-2",
            "feedback": "USEFUL",
            "saved": True,
        }
        self.calls = []

    def record_feedback(self, sku, feedback):
        self.calls.append((sku, feedback))
        result = dict(self.result)
        result["sku"] = sku
        result["feedback"] = str(feedback).upper()
        return result

    def learning_summary(self):
        return {
            "error": False,
            "products_count": 2,
            "decision_snapshots_count": 3,
            "feedback_count": 2,
            "feedback_counts": {
                "USEFUL": 1,
                "NOT_RELEVANT": 1,
            },
            "outcome_count": 1,
            "outcome_counts": {
                "PRIORITY_DECREASED": 1,
                "PRIORITY_INCREASED": 0,
                "DECISION_CHANGED": 0,
            },
        }

    def history(self, sku, limit=None):
        records = [{
            "sku": sku,
            "decision_type": "HOLD_STOCK",
            "priority": "LOW",
            "recorded_at": "2026-08-28T10:00:00+00:00",
            "feedback": "USEFUL",
            "outcome": "PRIORITY_DECREASED",
        }]
        return records[:limit] if limit is not None else records

    def latest(self, sku):
        records = self.history(sku, limit=1)
        return records[0] if records else None


class StubProposalConfirmation:
    def __init__(self, result=None):
        self.result = result or {
            "error": False,
            "code": None,
            "proposal_status": "CONFIRMED",
            "saved": True,
            "executed": False,
        }
        self.calls = []
        self.task_draft_service = None

    def decide(self, sku, expected_proposal_type, status):
        self.calls.append((sku, expected_proposal_type, status))
        result = dict(self.result)
        if result.get("error") is False:
            result["sku"] = sku
            result["proposal_type"] = expected_proposal_type
            result["proposal_status"] = status
            result["execution_allowed"] = False
            task_draft = result.get("task_draft")
            if isinstance(task_draft, dict):
                task_draft = dict(task_draft)
                task_draft.setdefault("sku", sku)
                task_draft.setdefault(
                    "proposal_type",
                    expected_proposal_type,
                )
                task_draft.setdefault("executed", False)
                task_draft.setdefault("execution_allowed", False)
                result["task_draft"] = task_draft
        return result


class StubTaskDrafts:
    def __init__(self):
        self.record = {
            "draft_id": "d1",
            "sku": "hook-2",
            "proposal_type": "REVIEW_REPLENISHMENT",
            "status": "DRAFT",
            "execution_allowed": False,
            "executed": False,
            "current_stock": 8,
            "sales_velocity": 4.0,
            "days_of_stock": 2.0,
            "profit_per_unit": 35.1,
            "margin_percent": 36.5,
            "economics_basis": "ESTIMATED_RETURNS",
        }

    def latest_for_sku(self, sku):
        return dict(self.record) if sku == "hook-2" else None

    def summary(self):
        return {
            "error": False,
            "total": 1,
            "counts": {
                "DRAFT": 1,
                "STALE": 0,
                "DISMISSED": 0,
                "ARCHIVED": 0,
            },
            "drafts": [dict(self.record)],
            "executed_count": 0,
        }

    def list_drafts(self, status=None, limit=None):
        items = [dict(self.record)]
        return items[:limit] if limit is not None else items

    def archive(self, draft_id):
        if draft_id != self.record["draft_id"]:
            return {"error": True, "code": "TASK_DRAFT_NOT_FOUND"}
        self.record["status"] = "ARCHIVED"
        return {
            "error": False,
            "task_draft": dict(self.record),
            "saved": True,
            "executed": False,
            "execution_allowed": False,
        }

    def get(self, draft_id):
        if draft_id != self.record["draft_id"]:
            return {"error": True, "code": "TASK_DRAFT_NOT_FOUND"}
        record = dict(self.record)
        record.update({
            "priority": "CRITICAL",
            "created_at": "created-time",
            "updated_at": "updated-time",
        })
        return {
            "error": False,
            "task_draft": record,
            "audit_events": [{
                "event_id": "e1",
                "event_type": "CREATED",
                "occurred_at": "created-time",
                "executed": False,
            }],
            "legacy_history_unavailable": False,
            "executed": False,
            "execution_allowed": False,
        }


class StubDraftReadiness:
    def evaluate(self, draft):
        return {
            "error": False,
            "draft_id": draft.get("draft_id"),
            "review_status": "READY_FOR_REVIEW",
            "review_ready": True,
            "required_checks": [],
            "missing_fields": [],
            "review_blockers": [],
            "execution_ready": False,
            "execution_blockers": [
                "EXECUTION_WORKFLOW_NOT_CONNECTED",
                "REPLENISHMENT_QUANTITY_POLICY_MISSING",
                "SUPPLIER_LEAD_TIME_MISSING",
            ],
            "executed": False,
        }

    def summarize(self, drafts):
        items = []
        for draft in drafts:
            item = dict(draft)
            item["readiness"] = self.evaluate(item)
            items.append(item)
        return {
            "error": False,
            "counts": {
                "READY_FOR_REVIEW": len(items),
                "NEEDS_DATA_OR_REFRESH": 0,
            },
            "items": items,
            "execution_ready_count": 0,
            "executed_count": 0,
        }

def test_product_decision_card_offers_manual_feedback_buttons():
    result = {
        "error": False,
        "code": None,
        "product_id": "101",
        "sku": "hook-2",
        "decision_type": "HOLD_STOCK",
        "priority": "LOW",
        "reasons": ["POSITIVE_UNIT_PROFIT"],
        "confidence": "HIGH",
        "missing_data": [],
        "decision_history_available": True,
    }
    handler, _, _ = _handler(
        result=result,
        history_service=StubDecisionHistory(),
    )

    response = handler.handle("product_decision:hook-2")
    callbacks = [
        item["callback"]
        for item in response["keyboard"]["buttons"]
    ]

    assert callbacks == [
        "product_decision_feedback:useful:hook-2",
        "product_decision_feedback:not_relevant:hook-2",
        "product_decision_history:hook-2",
    ]


def test_product_decision_feedback_callback_records_signal():
    history = StubDecisionHistory()
    handler, _, _ = _handler(history_service=history)

    response = handler.handle(
        "product_decision_feedback:useful:hook-2"
    )

    assert history.calls == [("hook-2", "useful")]
    assert response["error"] is False
    assert response["message"] == "Оценка сохранена: решение полезно."


def test_product_decision_feedback_requires_recorded_history():
    history = StubDecisionHistory({
        "error": True,
        "code": "DECISION_HISTORY_NOT_FOUND",
        "saved": False,
    })
    handler, _, _ = _handler(history_service=history)

    response = handler.handle(
        "product_decision_feedback:not_relevant:missing"
    )

    assert response["error"] is True
    assert response["message"] == (
        "Сначала откройте актуальное решение по товару"
    )


def test_product_decisions_menu_links_to_learning_summary():
    handler, _, _ = _handler(history_service=StubDecisionHistory())

    response = handler.handle("product_decisions")
    callbacks = [
        item["callback"]
        for item in response["keyboard"]["buttons"]
    ]

    assert "product_decision_learning_summary" in callbacks


def test_learning_summary_callback_formats_observational_counts():
    handler, _, _ = _handler(history_service=StubDecisionHistory())

    response = handler.handle("product_decision_learning_summary")

    assert response["error"] is False
    assert "📚 Итоги обучения решений" in response["message"]
    assert "Товаров в памяти: 2" in response["message"]
    assert "👍 Полезно: 1" in response["message"]
    assert "Срочность снизилась: 1" in response["message"]
    assert "не доказательством причинности" in response["message"]


def test_product_decision_history_callback_formats_latest_records():
    handler, _, _ = _handler(history_service=StubDecisionHistory())

    response = handler.handle("product_decision_history:hook-2")

    assert response["error"] is False
    assert "📚 История решений" in response["message"]
    assert "Артикул: hook-2" in response["message"]
    assert "Удерживать текущий запас" in response["message"]
    assert "Приоритет: Низкий" in response["message"]
    assert "Оценка: Полезно" in response["message"]
    assert "Наблюдение: Срочность рекомендации снизилась" in (
        response["message"]
    )


def test_actionable_proposal_card_offers_confirm_and_dismiss_buttons():
    result = {
        "error": False,
        "sku": "hook-2",
        "decision_type": "REPLENISH_NORMAL",
        "priority": "HIGH",
        "reasons": [],
        "confidence": "HIGH",
        "missing_data": [],
        "decision_history_available": True,
        "action_proposal": {
            "available": True,
            "proposal_type": "REVIEW_REPLENISHMENT",
            "action_required": True,
            "requires_confirmation": True,
        },
    }
    handler, _, _ = _handler(
        result=result,
        history_service=StubDecisionHistory(),
        confirmation_service=StubProposalConfirmation(),
    )

    response = handler.handle("product_decision:hook-2")
    callbacks = [
        item["callback"] for item in response["keyboard"]["buttons"]
    ]

    assert "product_proposal:yes:r:hook-2" in callbacks
    assert "product_proposal:no:r:hook-2" in callbacks


def test_proposal_confirmation_records_intent_but_never_executes():
    confirmation = StubProposalConfirmation()
    handler, _, _ = _handler(confirmation_service=confirmation)

    response = handler.handle("product_proposal:yes:r:hook-2")

    assert confirmation.calls == [
        ("hook-2", "REVIEW_REPLENISHMENT", "CONFIRMED")
    ]
    assert response["error"] is False
    assert response["executed"] is False
    assert "Выполнение не запускалось" in response["message"]


def test_stale_proposal_confirmation_requires_reopening_decision():
    confirmation = StubProposalConfirmation({
        "error": True,
        "code": "STALE_PROPOSAL",
        "saved": False,
        "executed": False,
    })
    handler, _, _ = _handler(confirmation_service=confirmation)

    response = handler.handle("product_proposal:no:m:hook-2")

    assert response["error"] is True
    assert response["executed"] is False
    assert "устарел" in response["message"]


def test_confirmation_response_explains_created_draft_and_no_execution():
    confirmation = StubProposalConfirmation({
        "error": False,
        "code": None,
        "proposal_status": "CONFIRMED",
        "saved": True,
        "executed": False,
        "task_draft": {
            "sku": "hook-2",
            "status": "DRAFT",
            "executed": False,
        },
    })
    handler, _, _ = _handler(confirmation_service=confirmation)

    response = handler.handle("product_proposal:yes:r:hook-2")

    assert "Создан безопасный черновик задачи" in response["message"]
    assert "Выполнение не запускалось" in response["message"]
    assert response["executed"] is False


def test_task_draft_summary_is_available_from_decisions_menu():
    confirmation = StubProposalConfirmation()
    confirmation.task_draft_service = StubTaskDrafts()
    handler, _, _ = _handler(confirmation_service=confirmation)

    menu = handler.handle("product_decisions")
    callbacks = [
        item["callback"] for item in menu["keyboard"]["buttons"]
    ]
    summary = handler.handle("product_action_task_drafts")

    assert "product_action_task_drafts" in callbacks
    assert summary["error"] is False
    assert summary["executed"] is False
    assert "Ожидают подготовки: 1" in summary["message"]
    assert "Выполнено: 0" in summary["message"]
    assert "не изменяют данные Ozon" in summary["message"]


def test_task_draft_summary_offers_safe_archive_action():
    confirmation = StubProposalConfirmation()
    confirmation.task_draft_service = StubTaskDrafts()
    handler, _, _ = _handler(confirmation_service=confirmation)

    summary = handler.handle("product_action_task_drafts")
    callbacks = [
        item["callback"] for item in summary["keyboard"]["buttons"]
    ]
    archived = handler.handle("product_task_draft:archive:d1")

    assert callbacks == [
        "product_task_draft:view:d1",
        "product_task_draft:archive:d1",
    ]
    assert archived["error"] is False
    assert archived["executed"] is False
    assert "Выполнение не запускалось" in archived["message"]


def test_task_draft_summary_shows_prioritized_review_queue_reasons():
    class StubReviewQueue:
        def prioritize(self, drafts, limit=10):
            item = dict(drafts[0])
            item.update({
                "review_priority": "URGENT",
                "review_score": 155,
                "review_reasons": [
                    "CURRENT_DRAFT",
                    "SOURCE_PRIORITY_CRITICAL",
                    "REPLENISHMENT_REVIEW",
                ],
            })
            return {
                "error": False,
                "total_reviewable": 1,
                "priority_counts": {
                    "URGENT": 1,
                    "HIGH": 0,
                    "NORMAL": 0,
                    "LOW": 0,
                },
                "items": [item],
                "executed_count": 0,
            }

    confirmation = StubProposalConfirmation()
    confirmation.task_draft_service = StubTaskDrafts()
    handler, _, query = _handler(confirmation_service=confirmation)
    query.task_draft_review_queue_service = StubReviewQueue()

    response = handler.handle("product_action_task_drafts")

    assert "hook-2 [Срочно]" in response["message"]
    assert "Приоритет очереди:" in response["message"]
    assert "Срочно: 1" in response["message"]
    assert "решение актуально" in response["message"]
    assert "критический приоритет товара" in response["message"]
    assert "проверка пополнения" in response["message"]
    assert response["review_queue"]["executed_count"] == 0
    assert response["keyboard"]["buttons"][0]["text"].startswith("🔴")


def test_task_draft_detail_shows_source_metrics_and_audit_trail():
    confirmation = StubProposalConfirmation()
    confirmation.task_draft_service = StubTaskDrafts()
    handler, _, _ = _handler(confirmation_service=confirmation)

    response = handler.handle("product_task_draft:view:d1")

    assert response["error"] is False
    assert response["executed"] is False
    assert "📋 Черновик задачи" in response["message"]
    assert "Артикул: hook-2" in response["message"]
    assert "Приоритет решения: Критический" in response["message"]
    assert "Прибыль с 1 шт.: 35.10 ₽" in response["message"]
    assert "Черновик создан" in response["message"]
    assert "Исполнение: недоступно" in response["message"]
    assert response["keyboard"]["buttons"] == [{
        "text": "🗄 Архивировать черновик",
        "callback": "product_task_draft:archive:d1",
    }]


def test_archived_task_draft_detail_has_no_lifecycle_controls():
    confirmation = StubProposalConfirmation()
    drafts = StubTaskDrafts()
    drafts.record["status"] = "ARCHIVED"
    confirmation.task_draft_service = drafts
    handler, _, _ = _handler(confirmation_service=confirmation)

    response = handler.handle("product_task_draft:view:d1")

    assert "Статус: Архивирован" in response["message"]
    assert response["keyboard"]["buttons"] == []
    assert response["executed"] is False


def test_task_draft_detail_separates_review_and_execution_readiness():
    confirmation = StubProposalConfirmation()
    confirmation.task_draft_service = StubTaskDrafts()
    handler, _, query = _handler(confirmation_service=confirmation)
    query.task_draft_readiness_service = StubDraftReadiness()

    detail = handler.handle("product_task_draft:view:d1")
    queue = handler.handle("product_action_task_drafts")

    assert "Готовность к ручной проверке:" in detail["message"]
    assert "Данных достаточно" in detail["message"]
    assert "Готовность к исполнению: нет" in detail["message"]
    assert "не утверждена политика количества" in detail["message"]
    assert "не указан срок поставки" in detail["message"]
    assert detail["readiness"]["execution_ready"] is False
    assert "Данных достаточно: 1" in queue["message"]
    assert "данных достаточно для проверки" in queue["message"]
    assert "Готово к исполнению: 0" in queue["message"]
    assert queue["readiness_summary"]["executed_count"] == 0
