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

    TASK_DRAFT_REVIEW_PRIORITY_LABELS = {
        "URGENT": "Срочно",
        "HIGH": "Высокий",
        "NORMAL": "Обычный",
        "LOW": "Низкий",
    }

    TASK_DRAFT_REVIEW_REASON_LABELS = {
        "CURRENT_DRAFT": "решение актуально",
        "STALE_DRAFT": "решение уже изменилось",
        "SOURCE_PRIORITY_CRITICAL": "критический приоритет товара",
        "SOURCE_PRIORITY_HIGH": "высокий приоритет товара",
        "SOURCE_PRIORITY_NORMAL": "обычный приоритет товара",
        "SOURCE_PRIORITY_LOW": "низкий приоритет товара",
        "SOURCE_PRIORITY_NONE": "приоритет товара не задан",
        "REPLENISHMENT_REVIEW": "проверка пополнения",
        "UNIT_ECONOMICS_REVIEW": "проверка юнит-экономики",
        "MARGIN_REVIEW": "проверка маржи",
    }

    TASK_DRAFT_EVENT_LABELS = {
        "CREATED": "Черновик создан",
        "REOPENED": "Черновик открыт повторно",
        "MARKED_STALE": "Черновик помечен устаревшим",
        "DISMISSED": "Предложение отклонено",
        "ARCHIVED": "Черновик архивирован",
    }

    TASK_DRAFT_READINESS_FIELD_LABELS = {
        "current_stock": "Текущий остаток",
        "sales_velocity": "Скорость продаж",
        "days_of_stock": "Дни запаса",
        "profit_per_unit": "Прибыль с единицы",
        "margin_percent": "Маржа",
        "economics_basis": "Источник юнит-экономики",
    }

    TASK_DRAFT_EXECUTION_BLOCKER_LABELS = {
        "EXECUTION_WORKFLOW_NOT_CONNECTED": (
            "исполнительный workflow не подключён"
        ),
        "REPLENISHMENT_QUANTITY_POLICY_MISSING": (
            "не утверждена политика количества пополнения"
        ),
        "SUPPLIER_LEAD_TIME_MISSING": (
            "не указан срок поставки"
        ),
        "ACTION_POLICY_NOT_DEFINED": (
            "не утверждена политика дальнейшего действия"
        ),
        "PRICE_CHANGE_POLICY_MISSING": (
            "не утверждена политика изменения цены"
        ),
        "TARGET_MARGIN_POLICY_MISSING": (
            "не задана целевая маржа"
        ),
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
        returns_finance_impact_query=None,
        product_decision_learning_health_builder=None,
        product_decision_learning_coverage_builder=None
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

        self.product_decision_learning_health_builder = (
            product_decision_learning_health_builder
        )

        self.product_decision_learning_coverage_builder = (
            product_decision_learning_coverage_builder
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

        if button_id == "product_decision_learning_health":
            return self._show_product_decision_learning_health()

        if button_id == "product_decision_learning_coverage":
            return self._show_product_decision_learning_coverage()

        if button_id == "product_action_task_drafts":
            return self._show_product_action_task_drafts()

        if button_id.startswith("product_task_draft:archive:"):
            draft_id = button_id.split(":", 2)[2]
            return self._archive_product_task_draft(draft_id)

        if button_id.startswith("product_task_draft:view:"):
            draft_id = button_id.split(":", 2)[2]
            return self._show_product_task_draft_detail(draft_id)

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
                    include_learning_health=(
                        self._product_decision_history_service()
                        is not None
                        and self.product_decision_learning_health_builder
                        is not None
                    ),
                    include_learning_coverage=(
                        self._product_decision_history_service()
                        is not None
                        and self.product_decision_learning_coverage_builder
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
        review_queue_service = getattr(
            self.product_business_decision_query,
            "task_draft_review_queue_service",
            None,
        )
        if review_queue_service is not None:
            queue = review_queue_service.prioritize(
                service.list_drafts(),
                limit=10,
            )
            drafts = queue.get("items") or []
        else:
            queue = None
            drafts = summary.get("drafts") or []
        readiness_service = getattr(
            self.product_business_decision_query,
            "task_draft_readiness_service",
            None,
        )
        if readiness_service is not None:
            readiness_summary = readiness_service.summarize(drafts)
            drafts = readiness_summary.get("items") or []
        else:
            readiness_summary = None
        if queue is not None:
            priority_counts = queue.get("priority_counts") or {}
            lines.extend([
                "",
                "Приоритет очереди:",
                "Срочно: " + str(priority_counts.get("URGENT", 0)),
                "Высокий: " + str(priority_counts.get("HIGH", 0)),
                "Обычный: " + str(priority_counts.get("NORMAL", 0)),
                "Низкий: " + str(priority_counts.get("LOW", 0)),
            ])
        if readiness_summary is not None:
            readiness_counts = readiness_summary.get("counts") or {}
            lines.extend([
                "",
                "Готовность к ручной проверке:",
                "Данных достаточно: "
                + str(readiness_counts.get("READY_FOR_REVIEW", 0)),
                "Нужны данные или обновление: "
                + str(
                    readiness_counts.get("NEEDS_DATA_OR_REFRESH", 0)
                ),
                "Готово к исполнению: 0",
            ])
        if drafts:
            lines.extend(["", "Очередь проверки:"])
            for draft in drafts:
                proposal_type = draft.get("proposal_type")
                status = draft.get("status")
                priority = draft.get("review_priority")
                priority_label = self.TASK_DRAFT_REVIEW_PRIORITY_LABELS.get(
                    priority,
                    str(priority or "Без приоритета"),
                )
                lines.append(
                    "• "
                    + str(draft.get("sku") or "—")
                    + " ["
                    + priority_label
                    + "] — "
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
                review_reasons = draft.get("review_reasons") or []
                if review_reasons:
                    lines.append(
                        "  Причины: "
                        + ", ".join(
                            self.TASK_DRAFT_REVIEW_REASON_LABELS.get(
                                reason,
                                str(reason),
                            )
                            for reason in review_reasons
                        )
                    )
                readiness = draft.get("readiness") or {}
                if readiness:
                    lines.append(
                        "  Готовность: "
                        + (
                            "данных достаточно для проверки"
                            if readiness.get("review_ready")
                            else "нужны данные или актуализация"
                        )
                    )
        lines.extend([
            "",
            "Черновики не выполняют действий и не изменяют данные Ozon.",
        ])
        response = {
            "error": False,
            "message": "\n".join(lines),
            "summary": summary,
            "review_queue": queue,
            "readiness_summary": readiness_summary,
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

    def _show_product_task_draft_detail(self, draft_id):
        service = self._product_action_task_draft_service()
        if service is None:
            return {
                "error": True,
                "message": "Черновики задач недоступны",
                "executed": False,
            }
        result = service.get(draft_id)
        if result.get("error"):
            return {
                "error": True,
                "message": "Черновик задачи не найден",
                "executed": False,
            }
        draft = result.get("task_draft") or {}
        readiness_service = getattr(
            self.product_business_decision_query,
            "task_draft_readiness_service",
            None,
        )
        readiness = (
            readiness_service.evaluate(draft)
            if readiness_service is not None
            else None
        )
        lines = [
            "📋 Черновик задачи",
            "",
            "Артикул: " + str(draft.get("sku") or "—"),
            "Статус: " + self.ACTION_TASK_DRAFT_STATUS_LABELS.get(
                draft.get("status"),
                str(draft.get("status") or "—"),
            ),
            "Шаг: " + self.ACTION_PROPOSAL_LABELS.get(
                draft.get("proposal_type"),
                str(draft.get("proposal_type") or "—"),
            ),
            "Приоритет решения: " + self.PRIORITY_LABELS.get(
                draft.get("priority"),
                str(draft.get("priority") or "—"),
            ),
            "Прибыль с 1 шт.: " + self._format_decision_money(
                draft.get("profit_per_unit")
            ),
            "Маржа: " + self._format_decision_number(
                draft.get("margin_percent"), "%"
            ),
            "Создан: " + str(draft.get("created_at") or "—"),
            "Обновлён: " + str(draft.get("updated_at") or "—"),
            "",
            "История изменений:",
        ]
        events = result.get("audit_events") or []
        if not events:
            lines.append("История до внедрения аудита недоступна.")
        for event in events:
            lines.append(
                "• "
                + str(event.get("occurred_at") or "—")
                + " — "
                + self.TASK_DRAFT_EVENT_LABELS.get(
                    event.get("event_type"),
                    str(event.get("event_type") or "—"),
                )
            )
        if readiness is not None:
            lines.extend([
                "",
                "Готовность к ручной проверке:",
                (
                    "Данных достаточно"
                    if readiness.get("review_ready")
                    else "Нужны данные или актуализация"
                ),
            ])
            missing_fields = readiness.get("missing_fields") or []
            if missing_fields:
                lines.append(
                    "Не хватает: "
                    + ", ".join(
                        self.TASK_DRAFT_READINESS_FIELD_LABELS.get(
                            field,
                            str(field),
                        )
                        for field in missing_fields
                    )
                )
            lines.extend([
                "",
                "Готовность к исполнению: нет",
                "Причины блокировки:",
            ])
            lines.extend(
                "• "
                + self.TASK_DRAFT_EXECUTION_BLOCKER_LABELS.get(
                    blocker,
                    str(blocker),
                )
                for blocker in readiness.get("execution_blockers") or []
            )
        lines.extend([
            "",
            "Исполнение: недоступно.",
            "Черновик не изменяет данные Ozon.",
        ])
        response = {
            "error": False,
            "message": "\n".join(lines),
            "task_draft": draft,
            "audit_events": events,
            "readiness": readiness,
            "executed": False,
        }
        if self.keyboard_service:
            response["keyboard"] = (
                self.keyboard_service
                .build_product_task_draft_detail_keyboard(draft)
            )
        return response

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

    def _show_product_decision_learning_health(self):
        history_service = self._product_decision_history_service()
        builder = self.product_decision_learning_health_builder
        if history_service is None or builder is None:
            return {
                "error": True,
                "message": "Качество данных обучения недоступно"
            }

        try:
            summary = history_service.learning_summary()
            health = builder(summary)
        except (OSError, TypeError, ValueError, KeyError):
            return {
                "error": True,
                "message": "Качество данных обучения недоступно"
            }

        valid_states = {
            "NO_FEEDBACK_EVIDENCE",
            "FEEDBACK_ONLY",
            "EARLY_POST_FEEDBACK_SAMPLE",
            "MULTI_PRODUCT_DESCRIPTIVE_SAMPLE",
        }
        valid_actions = {
            "COLLECT_USER_FEEDBACK",
            "WAIT_FOR_LATER_DECISION_OBSERVATIONS",
            "COLLECT_MORE_DESCRIPTIVE_OBSERVATIONS",
            "REVIEW_DESCRIPTIVE_PATTERNS",
        }
        if (
            not isinstance(health, dict)
            or health.get("status")
            != "PRODUCT_DECISION_LEARNING_HEALTH_READY"
            or health.get("error") is not False
            or health.get("evidence_scope")
            != "DESCRIPTIVE_DECISION_HISTORY_ONLY"
            or health.get("health_state") not in valid_states
            or health.get("next_action") not in valid_actions
            or health.get("causal_claim_allowed") is not False
            or health.get("success_rate_claim_allowed") is not False
            or health.get("profitability_claim_allowed") is not False
            or health.get("decision_rule_update_allowed") is not False
            or health.get("automatic_execution_allowed") is not False
            or health.get("executed") is not False
        ):
            return {
                "error": True,
                "message": "Качество данных обучения недоступно"
            }

        health_labels = {
            "NO_FEEDBACK_EVIDENCE": "Нет пользовательских оценок",
            "FEEDBACK_ONLY": "Есть оценки, но нет последующих наблюдений",
            "EARLY_POST_FEEDBACK_SAMPLE": "Ранняя описательная выборка",
            "MULTI_PRODUCT_DESCRIPTIVE_SAMPLE": (
                "Описательная выборка по нескольким товарам"
            ),
        }
        action_labels = {
            "COLLECT_USER_FEEDBACK": (
                "Собрать больше пользовательских оценок решений"
            ),
            "WAIT_FOR_LATER_DECISION_OBSERVATIONS": (
                "Дождаться следующих изменений решений после оценок"
            ),
            "COLLECT_MORE_DESCRIPTIVE_OBSERVATIONS": (
                "Накопить больше наблюдений по товарам"
            ),
            "REVIEW_DESCRIPTIVE_PATTERNS": (
                "Просмотреть описательные паттерны без причинных выводов"
            ),
        }

        message = "\n".join([
            "🩺 Качество данных обучения",
            "",
            "Товаров в истории: "
            + str(health.get("products_count", 0)),
            "Снимков решений: "
            + str(health.get("decision_snapshots_count", 0)),
            "Оценок пользователя: "
            + str(health.get("feedback_count", 0)),
            "👍 Полезно: "
            + str(health.get("useful_count", 0)),
            "👎 Неактуально: "
            + str(health.get("not_relevant_count", 0)),
            "",
            "Наблюдений после оценок: "
            + str(health.get("outcome_count", 0)),
            "Срочность снизилась: "
            + str(health.get("priority_decreased_count", 0)),
            "Срочность выросла: "
            + str(health.get("priority_increased_count", 0)),
            "Решение изменилось: "
            + str(health.get("decision_changed_count", 0)),
            "",
            "Состояние данных: "
            + health_labels.get(
                health.get("health_state"),
                str(health.get("health_state") or "—"),
            ),
            "Следующий шаг: "
            + action_labels.get(
                health.get("next_action"),
                str(health.get("next_action") or "—"),
            ),
            "",
            (
                "Это описательная статистика истории решений. "
                "Она не доказывает причинность, корректность решения "
                "или прибыльность."
            ),
        ])

        return {
            "error": False,
            "message": message,
            "learning_health": health,
            "executed": False,
        }

    def _show_product_decision_learning_coverage(self):
        history_service = self._product_decision_history_service()
        builder = self.product_decision_learning_coverage_builder
        query = self.product_business_decision_query
        product_service = getattr(query, "product_service", None)

        if (
            history_service is None
            or builder is None
            or product_service is None
        ):
            return {
                "error": True,
                "message": "Очередь сбора обратной связи недоступна"
            }

        try:
            products = product_service.load_products()
        except (OSError, TypeError, ValueError, KeyError):
            return {
                "error": True,
                "message": "Очередь сбора обратной связи недоступна"
            }

        if not isinstance(products, list):
            return {
                "error": True,
                "message": "Очередь сбора обратной связи недоступна"
            }

        rows = []
        seen = set()
        try:
            for product in products:
                if not isinstance(product, dict):
                    raise ValueError("invalid product")
                sku = str(
                    product.get("offer_id")
                    or product.get("sku")
                    or ""
                ).strip()
                if not sku or sku in seen:
                    raise ValueError("invalid product identity")
                seen.add(sku)
                rows.append({
                    "sku": sku,
                    "history": history_service.history(sku),
                })
            coverage = builder(rows)
        except (OSError, TypeError, ValueError, KeyError):
            return {
                "error": True,
                "message": "Очередь сбора обратной связи недоступна"
            }

        valid_states = {
            "NEEDS_USER_FEEDBACK",
            "NO_DECISION_HISTORY",
            "WAITING_FOR_LATER_OBSERVATION",
        }
        rank_by_state = {
            "NEEDS_USER_FEEDBACK": 1,
            "NO_DECISION_HISTORY": 2,
            "WAITING_FOR_LATER_OBSERVATION": 3,
        }
        if not isinstance(coverage, dict):
            return {
                "error": True,
                "message": "Очередь сбора обратной связи недоступна"
            }

        items = coverage.get("items")
        counts = coverage.get("counts")
        if (
            coverage.get("status")
            != "PRODUCT_DECISION_LEARNING_COVERAGE_QUEUE_READY"
            or coverage.get("error") is not False
            or coverage.get("evidence_scope")
            != "PERSISTED_DECISION_HISTORY_COVERAGE_ONLY"
            or coverage.get("business_priority_claimed") is not False
            or coverage.get("causal_claim_allowed") is not False
            or coverage.get("success_rate_claim_allowed") is not False
            or coverage.get("profitability_claim_allowed") is not False
            or coverage.get("decision_rule_update_allowed") is not False
            or coverage.get("automatic_execution_allowed") is not False
            or coverage.get("executed") is not False
            or not isinstance(items, list)
            or not isinstance(counts, dict)
            or set(counts) != valid_states
            or coverage.get("total") != len(items)
        ):
            return {
                "error": True,
                "message": "Очередь сбора обратной связи недоступна"
            }

        item_skus = []
        for item in items:
            if not isinstance(item, dict):
                return {
                    "error": True,
                    "message": "Очередь сбора обратной связи недоступна"
                }
            state = item.get("coverage_state")
            sku = str(item.get("sku") or "").strip()
            if (
                state not in valid_states
                or not sku
                or item.get("learning_attention_rank")
                != rank_by_state[state]
                or item.get("business_priority_claimed") is not False
                or item.get("causal_claim_allowed") is not False
                or item.get("success_rate_claim_allowed") is not False
                or item.get("profitability_claim_allowed") is not False
                or item.get("decision_rule_update_allowed") is not False
                or item.get("automatic_execution_allowed") is not False
                or item.get("executed") is not False
            ):
                return {
                    "error": True,
                    "message": "Очередь сбора обратной связи недоступна"
                }
            item_skus.append(sku)

        if (
            len(item_skus) != len(set(item_skus))
            or any(
                isinstance(counts.get(state), bool)
                or not isinstance(counts.get(state), int)
                or counts.get(state) < 0
                or counts.get(state)
                != sum(
                    item.get("coverage_state") == state
                    for item in items
                )
                for state in valid_states
            )
        ):
            return {
                "error": True,
                "message": "Очередь сбора обратной связи недоступна"
            }

        labels = {
            "NEEDS_USER_FEEDBACK": "Нужна оценка текущего решения",
            "NO_DECISION_HISTORY": "Нет сохранённой истории решения",
            "WAITING_FOR_LATER_OBSERVATION": (
                "Оценка сохранена — ждём следующее изменение решения"
            ),
        }
        lines = [
            "🧭 Очередь сбора обратной связи",
            "",
            "Нужна оценка: "
            + str(counts.get("NEEDS_USER_FEEDBACK", 0)),
            "Нет истории решения: "
            + str(counts.get("NO_DECISION_HISTORY", 0)),
            "Ждём следующего наблюдения: "
            + str(
                counts.get(
                    "WAITING_FOR_LATER_OBSERVATION",
                    0,
                )
            ),
            "",
        ]

        for index, item in enumerate(
            coverage.get("items")[:10],
            start=1,
        ):
            lines.append(
                str(index)
                + ". "
                + str(item.get("sku") or "—")
                + " — "
                + labels.get(
                    item.get("coverage_state"),
                    "Статус неизвестен",
                )
            )

        lines.extend([
            "",
            (
                "Это очередь сбора learning evidence, "
                "а не бизнес-приоритет товаров."
            ),
            (
                "Она не оценивает прибыльность и "
                "не запускает никаких действий."
            ),
        ])

        response = {
            "error": False,
            "message": "\n".join(lines),
            "learning_coverage": coverage,
            "executed": False,
        }

        keyboard_builder = getattr(
            self.keyboard_service,
            "build_product_decision_learning_coverage_keyboard",
            None,
        )
        if keyboard_builder is not None:
            navigation_items = [
                {
                    "sku": item["sku"],
                    "coverage_state": item["coverage_state"],
                }
                for item in items[:10]
            ]
            keyboard = keyboard_builder(navigation_items)
            expected_callbacks = [
                "product_decision:" + item["sku"]
                for item in navigation_items
            ] + ["product_decisions"]
            buttons = (
                keyboard.get("buttons")
                if isinstance(keyboard, dict)
                else None
            )
            callbacks = (
                [
                    button.get("callback")
                    for button in buttons
                    if isinstance(button, dict)
                ]
                if isinstance(buttons, list)
                else None
            )
            if (
                not isinstance(keyboard, dict)
                or keyboard.get("error") is not False
                or keyboard.get("type") != "inline_keyboard"
                or callbacks != expected_callbacks
                or len(callbacks) != len(buttons)
            ):
                return {
                    "error": True,
                    "message": "Очередь сбора обратной связи недоступна",
                    "executed": False,
                }
            response["keyboard"] = keyboard

        return response

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
