class AssistantButtonHandlerService:

    PRODUCT_DECISIONS_PAGE_SIZE = 8


    DECISION_LABELS = {
        "REPLENISH_HIGH_PRIORITY": "Высокий приоритет пополнения",
        "REPLENISH_NORMAL": "Рекомендуется пополнение",
        "WATCH_LOW_MARGIN": "Следить за низкой маржой",
        "INVESTIGATE_LOW_PROFIT": "Проверить низкую прибыльность",
        "HOLD_STOCK": "Удерживать текущий запас",
        "INSUFFICIENT_DATA": "Недостаточно данных для решения"
    }

    PRIORITY_LABELS = {
        "CRITICAL": "Критический",
        "HIGH": "Высокий",
        "NORMAL": "Обычный",
        "LOW": "Низкий",
        "NONE": "Нет"
    }

    DECISION_BUTTON_LABELS = {
        "REPLENISH_HIGH_PRIORITY": "Пополнить срочно",
        "REPLENISH_NORMAL": "Пополнить",
        "WATCH_LOW_MARGIN": "Низкая маржа",
        "INVESTIGATE_LOW_PROFIT": "Проверить прибыль",
        "HOLD_STOCK": "Наблюдать",
        "INSUFFICIENT_DATA": "Нет данных"
    }

    DECISION_BUTTON_ICONS = {
        "CRITICAL": "🔴",
        "HIGH": "🟠",
        "NORMAL": "🟡",
        "LOW": "🟢",
        "NONE": "⚪"
    }

    CONFIDENCE_LABELS = {
        "HIGH": "Высокая",
        "MEDIUM": "Средняя",
        "LOW": "Низкая"
    }

    REASON_LABELS = {
        "DAYS_OF_STOCK_CRITICAL": "Остаток критически низкий",
        "DAYS_OF_STOCK_LOW": "Остаток ниже комфортного уровня",
        "HIGH_SALES_VELOCITY": "Высокая скорость продаж",
        "SALES_DECLINING": "Продажи снижаются",
        "POSITIVE_UNIT_PROFIT": "Прибыль с единицы положительная",
        "LOW_UNIT_PROFIT": "Прибыль с единицы низкая",
        "NEGATIVE_UNIT_PROFIT": "Прибыль с единицы отрицательная",
        "LOW_MARGIN": "Маржа низкая",
        "ECONOMICS_INCOMPLETE": "Юнит-экономика неполная",
        "IDENTITY_MISMATCH": "Данные товара не совпадают между источниками"
    }

    ECONOMICS_BASIS_LABELS = {
        "CONFIRMED_RETURNS": "С подтверждёнными расходами на возвраты",
        "ESTIMATED_RETURNS": "С исторической оценкой возвратов",
        "RETURNS_UNAVAILABLE": "Расходы на возвраты неизвестны"
    }

    DECISION_OUTCOME_LABELS = {
        "PRIORITY_DECREASED": "Срочность рекомендации снизилась",
        "PRIORITY_INCREASED": "Срочность рекомендации выросла",
        "DECISION_CHANGED": "Рекомендация изменилась при том же приоритете"
    }

    ACTION_PROPOSAL_LABELS = {
        "REVIEW_REPLENISHMENT": "Проверить возможность пополнения",
        "REVIEW_UNIT_ECONOMICS": "Проверить юнит-экономику и расходы",
        "REVIEW_MARGIN": "Проверить цену, расходы и маржу",
        "MONITOR_ONLY": "Продолжить наблюдение за товаром"
    }

    ACTION_PROPOSAL_ALIASES = {
        "r": "REVIEW_REPLENISHMENT",
        "e": "REVIEW_UNIT_ECONOMICS",
        "m": "REVIEW_MARGIN",
    }

    ACTION_PROPOSAL_STATUS_LABELS = {
        "CONFIRMED": "Подтверждён",
        "DISMISSED": "Отклонён",
    }

    ACTION_TASK_DRAFT_STATUS_LABELS = {
        "DRAFT": "Ожидает дальнейшей подготовки",
        "DISMISSED": "Отклонён",
        "STALE": "Устарел после изменения решения",
        "ARCHIVED": "Архивирован",
    }

    MISSING_DATA_LABELS = {
        "advertising": "Реклама",
        "storage": "Хранение",
        "returns": "Возвраты",
        "tax": "Налог",
        "sales_velocity": "Скорость продаж",
        "sales_trend": "Тренд продаж",
        "current_stock": "Текущий остаток",
        "days_of_stock": "Дни запаса",
        "stock_priority": "Приоритет остатка",
        "profit_per_unit": "Прибыль с единицы",
        "margin_percent": "Маржа",
        "IDENTITY_MISMATCH": "Идентификатор товара"
    }


    def __init__(
        self,
        assistant,
        memory_service=None,
        history_service=None,
        task_context_service=None,
        keyboard_service=None,
        unit_economics_query=None,
        product_business_decision_query=None,
        returns_finance_impact_query=None
    ):

        self.assistant = (
            assistant
        )

        self.memory_service = (
            memory_service
        )

        self.history_service = (
            history_service
        )

        self.task_context_service = (
            task_context_service
        )

        self.keyboard_service = (
            keyboard_service
        )

        self.unit_economics_query = (
            unit_economics_query
        )

        self.product_business_decision_query = (
            product_business_decision_query
        )

        self.returns_finance_impact_query = (
            returns_finance_impact_query
        )


    def prepare_context(
        self,
        user_id,
        action,
        task
    ):

        if (
            self.task_context_service
            and user_id
        ):

            self.task_context_service.user_context_service.update(
                user_id,
                "last_action",
                action
            )

            self.task_context_service.update_task(
                user_id,
                task
            )


    def handle(
        self,
        button_id,
        user_id=None
    ):

        if button_id == "returns_finance_impact":

            return (
                self._open_returns_finance_impact_menu()
            )

        if button_id.startswith(
            "returns_finance_impact:"
        ):

            sku = button_id.split(
                ":",
                1
            )[1]

            return (
                self._show_returns_finance_impact(
                    sku
                )
            )

        if button_id == "product_decisions":

            return (
                self._open_product_decisions_menu()
            )

        if button_id.startswith("product_decisions_page:"):
            page_value = button_id.split(":", 1)[1]
            try:
                page = int(page_value)
            except (TypeError, ValueError):
                page = 1
            return self._open_product_decisions_menu(page=page)

        if button_id == "product_decision_learning_summary":
            return self._show_product_decision_learning_summary()

        if button_id == "product_action_task_drafts":
            return self._show_product_action_task_drafts()

        if button_id.startswith("product_task_draft:archive:"):
            draft_id = button_id.split(":", 2)[2]
            return self._archive_product_task_draft(draft_id)

        if button_id.startswith("product_decision_history:"):
            sku = button_id.split(":", 1)[1]
            return self._show_product_decision_history(sku)

        if button_id.startswith("product_decision_feedback:"):
            parts = button_id.split(":", 2)
            if len(parts) != 3:
                return {
                    "error": True,
                    "message": "Некорректная оценка решения"
                }
            return self._record_product_decision_feedback(
                feedback=parts[1],
                sku=parts[2]
            )

        if button_id.startswith("product_proposal:"):
            parts = button_id.split(":", 3)
            if len(parts) != 4:
                return {
                    "error": True,
                    "message": "Некорректное подтверждение шага",
                }
            return self._record_product_proposal_status(
                choice=parts[1],
                proposal_alias=parts[2],
                sku=parts[3],
            )

        if button_id.startswith(
            "product_decision:"
        ):

            sku = button_id.split(
                ":",
                1
            )[1]

            return (
                self._show_product_decision(
                    sku
                )
            )

        if button_id == "unit_economics":

            return (
                self._open_unit_economics_menu()
            )

        if button_id.startswith(
            "unit_economics:"
        ):

            sku = button_id.split(
                ":",
                1
            )[1]

            return (
                self._show_unit_economics(
                    sku
                )
            )

        if button_id == "analyze":

            self.prepare_context(
                user_id,
                "analyze",
                "Анализ продаж"
            )

            result = (
                self.assistant
                .ask(
                    "Что нужно сделать с продажами?",
                    user_id
                )
            )

            if (
                self.history_service
                and user_id
            ):

                self.history_service.add(
                    user_id,
                    "Выполнен анализ"
                )

            return result

        if button_id == "plan":

            self.prepare_context(
                user_id,
                "plan",
                "Создание плана действий"
            )

            result = (
                self.assistant
                .ask(
                    "Создай план действий",
                    user_id
                )
            )

            if (
                self.history_service
                and user_id
            ):

                self.history_service.add(
                    user_id,
                    "Создан план действий"
                )

            return result

        if button_id == "history":

            if (
                self.history_service
                and user_id
            ):

                return (
                    self.history_service
                    .get(
                        user_id
                    )
                )

            return {
                "error": False,
                "history": []
            }

        if button_id == "memory":

            if (
                self.memory_service
                and user_id
            ):

                return (
                    self.memory_service
                    .get_memory(
                        user_id
                    )
                )

            return {
                "error": False,
                "memory": {}
            }

        return {
            "error": True,
            "message": "Кнопка неизвестна"
        }


    def _open_product_decisions_menu(
        self,
        page=1
    ):

        if (
            not self.product_business_decision_query
            or not self.keyboard_service
        ):

            return {
                "error": True,
                "message": (
                    "Решения по товарам недоступны"
                )
            }

        overview = (
            self.product_business_decision_query
            .query_all()
        )
        decisions = overview.get("decisions") or []

        if not decisions:

            return {
                "error": False,
                "message": "Товары не найдены"
            }

        total_pages = max(
            1,
            (
                len(decisions)
                + self.PRODUCT_DECISIONS_PAGE_SIZE
                - 1
            ) // self.PRODUCT_DECISIONS_PAGE_SIZE
        )
        page = min(max(1, int(page)), total_pages)
        start = (page - 1) * self.PRODUCT_DECISIONS_PAGE_SIZE
        page_decisions = decisions[
            start:start + self.PRODUCT_DECISIONS_PAGE_SIZE
        ]

        items = [
            self._product_decision_keyboard_item(decision)
            for decision in page_decisions
        ]

        return {
            "error": False,
            "message": self._format_product_decisions_overview(
                overview,
                page=page,
                total_pages=total_pages
            ),
            "keyboard": (
                self.keyboard_service
                .build_product_decisions_keyboard(
                    items,
                    page=page,
                    total_pages=total_pages,
                    include_learning_summary=(
                        self._product_decision_history_service()
                        is not None
                    ),
                    include_task_drafts=(
                        self._product_action_task_draft_service()
                        is not None
                    ),
                )
            ),
            "overview": overview
        }

    def _format_product_decisions_overview(
        self,
        overview,
        page=1,
        total_pages=1
    ):
        counts = overview.get("counts") or {}
        return "\n".join([
            "🎯 Решения по товарам",
            "",
            "Всего товаров: " + str(overview.get("total", 0)),
            "Страница: " + str(page) + " из " + str(total_pages),
            (
                "Срочно пополнить: "
                + str(counts.get("REPLENISH_HIGH_PRIORITY", 0))
            ),
            (
                "Пополнить: "
                + str(counts.get("REPLENISH_NORMAL", 0))
            ),
            (
                "Проверить прибыль: "
                + str(counts.get("INVESTIGATE_LOW_PROFIT", 0))
            ),
            (
                "Низкая маржа: "
                + str(counts.get("WATCH_LOW_MARGIN", 0))
            ),
            (
            "Недостаточно данных: "
                + str(counts.get("INSUFFICIENT_DATA", 0))
            ),
            "Предложений к ручной проверке: "
            + str(overview.get("actionable_proposals_count", 0)),
            "",
            "Товары отсортированы по срочности.",
        ])

    def _product_decision_keyboard_item(self, decision):
        sku = str(decision.get("sku") or "—")
        priority = str(decision.get("priority") or "NONE").upper()
        decision_type = str(
            decision.get("decision_type")
            or "INSUFFICIENT_DATA"
        )
        icon = self.DECISION_BUTTON_ICONS.get(priority, "⚪")
        label = self.DECISION_BUTTON_LABELS.get(
            decision_type,
            "Открыть"
        )
        return {
            "sku": sku,
            "text": f"{icon} {sku} — {label}",
        }


    def _show_product_decision(
        self,
        sku
    ):

        if not self.product_business_decision_query:

            return {
                "error": True,
                "message": (
                    "Решения по товарам недоступны"
                )
            }

        result = (
            self.product_business_decision_query
            .query(
                sku
            )
        )
        result = self._with_latest_proposal_status(result, sku)

        response = {
            "error": result.get(
                "error",
                False
            ),
            "message": self._format_product_decision(
                result
            ),
            "decision": result
        }

        if (
            not response["error"]
            and result.get("decision_history_available")
            and self.keyboard_service
        ):
            response["keyboard"] = (
                self.keyboard_service
                .build_product_decision_feedback_keyboard(
                    sku,
                    proposal=result.get("action_proposal"),
                )
            )

        return response

    def _with_latest_proposal_status(self, result, sku):
        result = dict(result or {})
        proposal = dict(result.get("action_proposal") or {})
        history_service = getattr(
            self.product_business_decision_query,
            "decision_history_service",
            None,
        )
        if history_service is None or not proposal.get("proposal_type"):
            return result
        try:
            latest = history_service.latest(sku)
        except (OSError, ValueError, TypeError):
            return result
        if (
            latest
            and latest.get("proposal_type") == proposal.get("proposal_type")
        ):
            proposal["proposal_status"] = latest.get("proposal_status")
            result["action_proposal"] = proposal
        draft_service = self._product_action_task_draft_service()
        if draft_service is not None:
            try:
                draft = draft_service.latest_for_sku(sku)
            except (OSError, ValueError, TypeError):
                draft = None
            if (
                draft
                and draft.get("proposal_type") == proposal.get("proposal_type")
                and draft.get("decision_recorded_at")
                == result.get("decision_recorded_at")
            ):
                result["action_task_draft"] = draft
        return result

    def _record_product_proposal_status(
        self,
        choice,
        proposal_alias,
        sku,
    ):
        confirmation_service = getattr(
            self.product_business_decision_query,
            "action_proposal_confirmation_service",
            None,
        )
        if confirmation_service is None:
            return {
                "error": True,
                "message": "Подтверждение шагов недоступно",
            }

        status = {
            "yes": "CONFIRMED",
            "no": "DISMISSED",
        }.get(choice)
        proposal_type = self.ACTION_PROPOSAL_ALIASES.get(proposal_alias)
        if status is None or proposal_type is None:
            return {
                "error": True,
                "message": "Некорректное подтверждение шага",
            }

        result = confirmation_service.decide(
            sku=sku,
            expected_proposal_type=proposal_type,
            status=status,
        )
        if result.get("error"):
            messages = {
                "DECISION_HISTORY_NOT_FOUND": (
                    "Сначала откройте актуальное решение по товару"
                ),
                "STALE_PROPOSAL": (
                    "Предложенный шаг устарел. Откройте решение заново"
                ),
                "PROPOSAL_NOT_CONFIRMABLE": (
                    "Этот шаг не требует подтверждения"
                ),
            }
            return {
                "error": True,
                "message": messages.get(
                    result.get("code"),
                    "Не удалось сохранить статус шага",
                ),
                "executed": False,
            }

        verb = "подтверждён" if status == "CONFIRMED" else "отклонён"
        task_draft = result.get("task_draft")
        message = "Шаг " + verb + " и сохранён."
        if status == "CONFIRMED" and task_draft:
            message += " Создан безопасный черновик задачи."
        message += " Выполнение не запускалось."
        return {
            "error": False,
            "message": message,
            "proposal_status": status,
            "task_draft": task_draft,
            "saved": result.get("saved", False),
            "executed": False,
        }

    def _product_action_task_draft_service(self):
        return getattr(
            self.product_business_decision_query,
            "action_task_draft_service",
            None,
        )

    def _show_product_action_task_drafts(self):
        service = self._product_action_task_draft_service()
        if service is None:
            return {
                "error": True,
                "message": "Черновики задач недоступны",
            }
        summary = service.summary()
        counts = summary.get("counts") or {}
        lines = [
            "📋 Черновики задач по товарам",
            "",
            "Ожидают подготовки: " + str(counts.get("DRAFT", 0)),
            "Устарело: " + str(counts.get("STALE", 0)),
            "Отклонено: " + str(counts.get("DISMISSED", 0)),
            "В архиве: " + str(counts.get("ARCHIVED", 0)),
            "Выполнено: 0",
        ]
        drafts = summary.get("drafts") or []
        if drafts:
            lines.extend(["", "Последние черновики:"])
            for draft in drafts:
                proposal_type = draft.get("proposal_type")
                status = draft.get("status")
                lines.append(
                    "• "
                    + str(draft.get("sku") or "—")
                    + " — "
                    + self.ACTION_PROPOSAL_LABELS.get(
                        proposal_type,
                        str(proposal_type or "—"),
                    )
                    + " ("
                    + self.ACTION_TASK_DRAFT_STATUS_LABELS.get(
                        status,
                        str(status or "—"),
                    )
                    + ")"
                )
        lines.extend([
            "",
            "Черновики не выполняют действий и не изменяют данные Ozon.",
        ])
        response = {
            "error": False,
            "message": "\n".join(lines),
            "summary": summary,
            "executed": False,
        }
        if self.keyboard_service:
            response["keyboard"] = (
                self.keyboard_service.build_product_task_drafts_keyboard(
                    drafts
                )
            )
        return response

    def _archive_product_task_draft(self, draft_id):
        service = self._product_action_task_draft_service()
        if service is None:
            return {
                "error": True,
                "message": "Черновики задач недоступны",
                "executed": False,
            }
        result = service.archive(draft_id)
        if result.get("error"):
            return {
                "error": True,
                "message": "Черновик задачи не найден",
                "executed": False,
            }
        return {
            "error": False,
            "message": (
                "Черновик архивирован. Выполнение не запускалось."
            ),
            "task_draft": result.get("task_draft"),
            "saved": result.get("saved", False),
            "executed": False,
        }

    def _record_product_decision_feedback(self, feedback, sku):
        history_service = getattr(
            self.product_business_decision_query,
            "decision_history_service",
            None
        )
        if history_service is None:
            return {
                "error": True,
                "message": "История решений недоступна"
            }

        result = history_service.record_feedback(sku, feedback)
        if result.get("error"):
            if result.get("code") == "DECISION_HISTORY_NOT_FOUND":
                message = "Сначала откройте актуальное решение по товару"
            else:
                message = "Некорректная оценка решения"
            return {
                "error": True,
                "message": message,
                "feedback": result,
            }

        label = (
            "решение полезно"
            if result.get("feedback") == "USEFUL"
            else "решение неактуально"
        )
        return {
            "error": False,
            "message": "Оценка сохранена: " + label + ".",
            "feedback": result,
        }

    def _show_product_decision_learning_summary(self):
        history_service = self._product_decision_history_service()
        if history_service is None:
            return {
                "error": True,
                "message": "История решений недоступна"
            }

        summary = history_service.learning_summary()
        feedback = summary.get("feedback_counts") or {}
        outcomes = summary.get("outcome_counts") or {}
        message = "\n".join([
            "📚 Итоги обучения решений",
            "",
            "Товаров в памяти: "
            + str(summary.get("products_count", 0)),
            "Снимков решений: "
            + str(summary.get("decision_snapshots_count", 0)),
            "Оценок: " + str(summary.get("feedback_count", 0)),
            "👍 Полезно: " + str(feedback.get("USEFUL", 0)),
            "👎 Неактуально: "
            + str(feedback.get("NOT_RELEVANT", 0)),
            "",
            "Наблюдений после оценок: "
            + str(summary.get("outcome_count", 0)),
            "Срочность снизилась: "
            + str(outcomes.get("PRIORITY_DECREASED", 0)),
            "Срочность выросла: "
            + str(outcomes.get("PRIORITY_INCREASED", 0)),
            "Решение изменилось без смены приоритета: "
            + str(outcomes.get("DECISION_CHANGED", 0)),
            "",
            "Данные являются наблюдениями, а не доказательством причинности.",
        ])
        return {
            "error": False,
            "message": message,
            "learning_summary": summary,
        }

    def _show_product_decision_history(self, sku):
        history_service = self._product_decision_history_service()
        if history_service is None:
            return {
                "error": True,
                "message": "История решений недоступна"
            }

        records = history_service.history(sku, limit=5)
        if not records:
            return {
                "error": False,
                "message": "История решений по товару пока пуста",
                "decision_history": [],
            }

        lines = [
            "📚 История решений",
            "",
            "Артикул: " + str(sku),
        ]
        for index, record in enumerate(records, start=1):
            decision_type = record.get("decision_type")
            priority = record.get("priority")
            recorded_at = str(record.get("recorded_at") or "—")
            lines.extend([
                "",
                str(index) + ". " + recorded_at.split("T", 1)[0],
                self.DECISION_LABELS.get(
                    decision_type,
                    str(decision_type or "—")
                ),
                "Приоритет: "
                + self.PRIORITY_LABELS.get(
                    priority,
                    str(priority or "—")
                ),
            ])
            feedback = record.get("feedback")
            if feedback:
                lines.append(
                    "Оценка: "
                    + (
                        "Полезно"
                        if feedback == "USEFUL"
                        else "Неактуально"
                    )
                )
            outcome = record.get("outcome")
            if outcome:
                lines.append(
                    "Наблюдение: "
                    + self.DECISION_OUTCOME_LABELS.get(
                        outcome,
                        str(outcome)
                    )
                )

        return {
            "error": False,
            "message": "\n".join(lines),
            "decision_history": records,
        }

    def _product_decision_history_service(self):
        return getattr(
            self.product_business_decision_query,
            "decision_history_service",
            None
        )


    def _format_product_decision(
        self,
        result
    ):
        code = result.get("code")

        if code == "SKU_NOT_FOUND":
            return "Товар не найден"

        if (
            code == "INSUFFICIENT_DATA"
            or result.get("decision_type")
            == "INSUFFICIENT_DATA"
        ):
            return "Недостаточно данных для решения"

        sku = result.get("sku") or "—"
        decision_type = result.get("decision_type") or "—"
        priority = result.get("priority") or "—"
        confidence = result.get("confidence") or "—"
        decision_label = self.DECISION_LABELS.get(
            decision_type,
            decision_type
        )

        lines = [
            "🎯 Решение по товару",
            "",
            "Артикул:",
            str(sku),
            "",
            "Решение:",
            decision_label,
            "",
            "Приоритет:",
            self.PRIORITY_LABELS.get(priority, priority),
        ]

        if result.get("decision_changed"):
            previous_type = result.get("previous_decision_type")
            lines.extend([
                "",
                "Изменение решения:",
                (
                    self.DECISION_LABELS.get(
                        previous_type,
                        str(previous_type or "—")
                    )
                    + " → "
                    + decision_label
                ),
            ])

        outcome = result.get("decision_outcome")
        if outcome:
            lines.extend([
                "",
                "Наблюдение после прошлой оценки:",
                self.DECISION_OUTCOME_LABELS.get(
                    outcome,
                    str(outcome)
                ),
            ])

        proposal = result.get("action_proposal") or {}
        if proposal.get("available"):
            proposal_type = proposal.get("proposal_type")
            lines.extend([
                "",
                "Следующий шаг:",
                self.ACTION_PROPOSAL_LABELS.get(
                    proposal_type,
                    str(proposal_type)
                ),
            ])
            if proposal.get("requires_confirmation"):
                lines.append("⚠️ Требует ручного подтверждения.")
            proposal_status = proposal.get("proposal_status")
            if proposal_status:
                lines.extend([
                    "",
                    "Статус шага:",
                    self.ACTION_PROPOSAL_STATUS_LABELS.get(
                        proposal_status,
                        str(proposal_status),
                    ),
                ])

        task_draft = result.get("action_task_draft") or {}
        if task_draft:
            draft_status = task_draft.get("status")
            lines.extend([
                "",
                "Черновик задачи:",
                self.ACTION_TASK_DRAFT_STATUS_LABELS.get(
                    draft_status,
                    str(draft_status or "—"),
                ),
            ])

        lines.extend([
            "",
            "Показатели решения:",
            (
                "Скорость продаж: "
                + self._format_decision_number(
                    result.get("sales_velocity"),
                    " шт./день"
                )
            ),
            (
                "Остаток: "
                + self._format_decision_number(
                    result.get("current_stock"),
                    " шт."
                )
            ),
            (
                "Запас: "
                + self._format_decision_number(
                    result.get("days_of_stock"),
                    " дн."
                )
            ),
            (
                "Прибыль с 1 шт.: "
                + self._format_decision_money(
                    result.get("decision_profit_per_unit")
                )
            ),
            (
                "Маржа: "
                + self._format_decision_number(
                    result.get("decision_margin_percent"),
                    "%"
                )
            ),
        ])

        basis = result.get("economics_basis")
        if basis is not None:
            lines.extend([
                "",
                "Основа расчёта:",
                self.ECONOMICS_BASIS_LABELS.get(
                    basis,
                    str(basis)
                ),
            ])

            reserve = result.get("returns_reserve_per_unit")
            if reserve is not None:
                lines.append(
                    "Возвраты и невыкупы: "
                    + self._format_decision_money(reserve)
                )

            coverage = result.get("returns_coverage_percent")
            if coverage is not None:
                lines.append(
                    "Финансовое покрытие: "
                    + self._format_decision_number(
                        coverage,
                        "%"
                    )
                )

        lines.extend(["", "Причины:"])
        reasons = result.get("reasons") or []
        if reasons:
            for reason in reasons:
                lines.append(
                    "✓ "
                    + self.REASON_LABELS.get(
                        reason,
                        str(reason)
                    )
                )
        else:
            lines.append("—")

        lines.extend([
            "",
            "Уверенность:",
            self.CONFIDENCE_LABELS.get(
                confidence,
                confidence
            ),
        ])

        missing_data = result.get("missing_data") or []
        if missing_data:
            lines.extend(["", "Не учтено:"])
            for item in missing_data:
                lines.append(
                    "— "
                    + self.MISSING_DATA_LABELS.get(
                        item,
                        str(item)
                    )
                )

        return "\n".join(lines)


    def _format_decision_money(
        self,
        value
    ):
        if value is None:
            return "—"
        return f"{float(value):.2f} ₽"


    def _format_decision_number(
        self,
        value,
        suffix=""
    ):
        if value is None:
            return "—"
        number = float(value)
        text = (
            str(int(number))
            if number.is_integer()
            else f"{number:.2f}".rstrip("0").rstrip(".")
        )
        return text + suffix


    def _open_unit_economics_menu(
        self
    ):

        if (
            not self.unit_economics_query
            or not self.keyboard_service
        ):

            return {
                "error": True,
                "message": (
                    "Юнит-экономика недоступна"
                )
            }

        products = (
            self.unit_economics_query
            .product_service
            .load_products()
        )

        skus = []

        for product in (products or []):

            sku = self._extract_sku(
                product
            )

            if sku is not None:

                skus.append(
                    str(sku)
                )

        if not skus:

            return {
                "error": False,
                "message": "Товары не найдены"
            }

        return {
            "error": False,
            "message": "Выберите товар:",
            "keyboard": (
                self.keyboard_service
                .build_unit_economics_keyboard(
                    skus
                )
            )
        }


    def _show_unit_economics(
        self,
        sku
    ):

        if not self.unit_economics_query:

            return {
                "error": True,
                "message": (
                    "Юнит-экономика недоступна"
                )
            }

        result = (
            self.unit_economics_query
            .query(
                sku
            )
        )

        return {
            "error": result.get(
                "error",
                False
            ),
            "message": (
                self.unit_economics_query
                .format_response(
                    result
                )
            ),
            "unit_economics": result
        }


    def _extract_sku(
        self,
        product
    ):

        if isinstance(
            product,
            dict
        ):

            return (
                product.get("offer_id")
                if product.get("offer_id") is not None
                else product.get("sku")
            )

        try:

            offer_id = product[1]
            if offer_id is not None:
                return offer_id
            return product[2]

        except (
            TypeError,
            IndexError
        ):

            return None


    def _open_returns_finance_impact_menu(
        self
    ):

        if (
            not self.returns_finance_impact_query
            or not self.keyboard_service
        ):

            return {
                "error": True,
                "message": (
                    "Расходы на возвраты недоступны"
                )
            }

        products = (
            self.returns_finance_impact_query
            .product_service
            .load_products()
        )
        skus = []

        for product in (products or []):
            sku = (
                product.get("offer_id")
                if isinstance(product, dict)
                and product.get("offer_id") is not None
                else self._extract_sku(product)
            )
            if sku is not None:
                skus.append(str(sku))

        if not skus:
            return {
                "error": False,
                "message": "Товары не найдены"
            }

        return {
            "error": False,
            "message": "Выберите товар:",
            "keyboard": (
                self.keyboard_service
                .build_returns_finance_impact_keyboard(
                    skus
                )
            )
        }


    def _show_returns_finance_impact(
        self,
        sku
    ):

        if not self.returns_finance_impact_query:
            return {
                "error": True,
                "message": (
                    "Расходы на возвраты недоступны"
                )
            }

        result = self.returns_finance_impact_query.query(sku)

        return {
            "error": result.get("error", False),
            "message": (
                self._format_returns_finance_impact(result)
            ),
            "returns_finance_impact": result
        }


    def _format_returns_finance_impact(
        self,
        result
    ):

        if result.get("error"):
            return (
                result.get("message")
                or "Расходы на возвраты недоступны"
            )

        lines = [
            "↩️ Расходы на возвраты",
            "",
            "SKU:",
            str(result.get("requested_sku") or "—"),
            "",
            "Период:",
            str(result.get("period_days") or "—")
            + " полных дней",
        ]

        for key in (
            "customer_non_buyout",
            "customer_return",
        ):
            item = (
                (result.get("categories") or {}).get(key)
                or {}
            )
            lines.extend([
                "",
                str(item.get("label") or key) + ":",
                "События: "
                + str(item.get("event_posting_count", 0)),
                "Сопоставлено: "
                + str(item.get(
                    "finance_matched_posting_count",
                    0
                )),
                "Покрытие: "
                + self._format_percent(
                    item.get("finance_coverage_percent")
                ),
                "Наблюдаемые расходы: "
                + self._format_money(
                    item.get("observed_cost_total")
                ),
                "Среднее на сопоставленное событие: "
                + self._format_money(
                    item.get("observed_cost_average")
                ),
            ])

        lines.extend([
            "",
            "Скорректированная прибыль:",
            "—",
        ])

        if not result.get("complete"):
            lines.extend([
                "",
                "⚠️ Данные неполные. Показаны только "
                "наблюдаемые расходы; экстраполяция "
                "и пересчёт прибыли не выполнялись.",
            ])

        return "\n".join(lines)


    def _format_money(
        self,
        value
    ):

        if value is None:
            return "—"

        return f"{float(value):.2f} ₽"


    def _format_percent(
        self,
        value
    ):

        if value is None:
            return "—"

        return f"{float(value):.2f}%"
