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

    DECISION_PRIORITY_CONTRACT = {
        "REPLENISH_HIGH_PRIORITY": "CRITICAL",
        "REPLENISH_NORMAL": "HIGH",
        "WATCH_LOW_MARGIN": "NORMAL",
        "INVESTIGATE_LOW_PROFIT": "HIGH",
        "HOLD_STOCK": "LOW",
        "INSUFFICIENT_DATA": "NONE",
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
        product_decision_learning_coverage_builder=None,
        product_decision_persistence_verifier=None,
        product_decision_user_action_guidance_builder=None,
        product_decision_user_action_checklist_builder=None
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

        self.product_decision_persistence_verifier = (
            product_decision_persistence_verifier
        )

        self.product_decision_user_action_guidance_builder = (
            product_decision_user_action_guidance_builder
        )

        self.product_decision_user_action_checklist_builder = (
            product_decision_user_action_checklist_builder
        )


    def prepare_context(
        self,
        user_id,
        action,
        task
    ):

        if (
            not self.task_context_service
            or not user_id
        ):

            return {
                "error": False,
                "prepared": False
            }

        try:

            last_action_result = (
                self.task_context_service
                .user_context_service
                .update(
                    user_id,
                    "last_action",
                    action
                )
            )

        except Exception:

            return {
                "error": True,
                "message":
                    "ASSISTANT_BUTTON_CONTEXT_UPDATE_FAILED",
                "assistant_started": False,
                "context_state_unknown": True
            }

        last_action_failure = (
            self._validate_context_update_result(
                last_action_result,
                partial=False
            )
        )

        if last_action_failure:

            return last_action_failure

        try:

            task_result = (
                self.task_context_service
                .update_task(
                    user_id,
                    task
                )
            )

        except Exception:

            return {
                "error": True,
                "message":
                    "ASSISTANT_BUTTON_CONTEXT_UPDATE_FAILED",
                "assistant_started": False,
                "context_partially_updated": True,
                "last_action_updated": True,
                "current_task_state_unknown": True
            }

        task_failure = (
            self._validate_context_update_result(
                task_result,
                partial=True
            )
        )

        if task_failure:

            return task_failure

        return {
            "error": False,
            "prepared": True
        }


    @staticmethod
    def _validate_context_update_result(
        result,
        partial
    ):

        if (
            not isinstance(
                result,
                dict
            )
            or type(
                result.get(
                    "error"
                )
            )
            is not bool
        ):

            failure = {
                "error": True,
                "message":
                    "INVALID_ASSISTANT_BUTTON_CONTEXT_RESULT",
                "assistant_started": False,
                "context_state_unknown": True
            }

            if partial:
                failure[
                    "context_partially_updated"
                ] = True
                failure[
                    "last_action_updated"
                ] = True

            return failure

        if result.get(
            "error"
        ) is True:

            failure = dict(
                result
            )
            failure[
                "assistant_started"
            ] = False

            if partial:
                failure[
                    "context_partially_updated"
                ] = True
                failure[
                    "last_action_updated"
                ] = True
                failure[
                    "current_task_updated"
                ] = False

            return failure

        if result.get(
            "updated"
        ) is not True:

            failure = {
                "error": True,
                "message":
                    "INVALID_ASSISTANT_BUTTON_CONTEXT_RESULT",
                "assistant_started": False,
                "context_state_unknown": True
            }

            if partial:
                failure[
                    "context_partially_updated"
                ] = True
                failure[
                    "last_action_updated"
                ] = True

            return failure

        return None


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

            context_result = (
                self.prepare_context(
                    user_id,
                    "analyze",
                    "Анализ продаж"
                )
            )

            if context_result.get(
                "error"
            ) is True:

                return context_result

            return self._run_assistant_button_with_history(
                prompt="Что нужно сделать с продажами?",
                user_id=user_id,
                history_event="Выполнен анализ"
            )

        if button_id == "plan":

            context_result = (
                self.prepare_context(
                    user_id,
                    "plan",
                    "Создание плана действий"
                )
            )

            if context_result.get(
                "error"
            ) is True:

                return context_result

            return self._run_assistant_button_with_history(
                prompt="Создай план действий",
                user_id=user_id,
                history_event="Создан план действий"
            )

        if button_id == "history":

            return self._show_history(
                user_id
            )

        if button_id == "memory":

            return self._show_memory(
                user_id
            )

        return {
            "error": True,
            "message": "Кнопка неизвестна"
        }


    def _show_history(
        self,
        user_id
    ):

        if not self.history_service:

            return {
                "error": True,
                "message":
                    "TELEGRAM_HISTORY_UNAVAILABLE"
            }

        if not user_id:

            return {
                "error": True,
                "message":
                    "TELEGRAM_USER_CONTEXT_REQUIRED"
            }

        try:

            result = (
                self.history_service
                .get(
                    user_id
                )
            )

        except Exception:

            return {
                "error": True,
                "message":
                    "TELEGRAM_HISTORY_READ_FAILED"
            }

        if (
            not isinstance(
                result,
                dict
            )
            or type(
                result.get(
                    "error"
                )
            )
            is not bool
        ):

            return {
                "error": True,
                "message":
                    "INVALID_TELEGRAM_HISTORY_RESULT"
            }

        if result.get(
            "error"
        ) is True:

            return result

        if not isinstance(
            result.get(
                "history"
            ),
            list
        ):

            return {
                "error": True,
                "message":
                    "INVALID_TELEGRAM_HISTORY_RESULT"
            }

        return result


    def _show_memory(
        self,
        user_id
    ):

        if not self.memory_service:

            return {
                "error": True,
                "message":
                    "TELEGRAM_MEMORY_UNAVAILABLE"
            }

        if not user_id:

            return {
                "error": True,
                "message":
                    "TELEGRAM_USER_CONTEXT_REQUIRED"
            }

        try:

            result = (
                self.memory_service
                .get_memory(
                    user_id
                )
            )

        except Exception:

            return {
                "error": True,
                "message":
                    "TELEGRAM_MEMORY_READ_FAILED"
            }

        if (
            not isinstance(
                result,
                dict
            )
            or type(
                result.get(
                    "error"
                )
            )
            is not bool
        ):

            return {
                "error": True,
                "message":
                    "INVALID_TELEGRAM_MEMORY_RESULT"
            }

        if result.get(
            "error"
        ) is True:

            return result

        if not isinstance(
            result.get(
                "memory"
            ),
            dict
        ):

            return {
                "error": True,
                "message":
                    "INVALID_TELEGRAM_MEMORY_RESULT"
            }

        return result


    def _run_assistant_button_with_history(
        self,
        prompt,
        user_id,
        history_event
    ):

        result = (
            self.assistant
            .ask(
                prompt,
                user_id
            )
        )

        if (
            not isinstance(
                result,
                dict
            )
            or type(
                result.get(
                    "error"
                )
            )
            is not bool
        ):

            return {
                "error": True,
                "message":
                    "INVALID_ASSISTANT_BUTTON_RESULT"
            }

        if result.get(
            "error"
        ) is True:

            return result

        if (
            not self.history_service
            or not user_id
        ):

            return result

        try:

            history_result = (
                self.history_service
                .add(
                    user_id,
                    history_event
                )
            )

        except Exception:

            return {
                "error": True,
                "message":
                    "ASSISTANT_BUTTON_HISTORY_WRITE_FAILED",
                "assistant_completed": True,
                "history_recorded": False,
                "persistence_state_unknown": True
            }

        if (
            not isinstance(
                history_result,
                dict
            )
            or type(
                history_result.get(
                    "error"
                )
            )
            is not bool
        ):

            return {
                "error": True,
                "message":
                    "INVALID_ASSISTANT_BUTTON_HISTORY_RESULT",
                "assistant_completed": True,
                "history_recorded": False,
                "persistence_state_unknown": True
            }

        if history_result.get(
            "error"
        ) is True:

            failure = dict(
                history_result
            )
            failure[
                "assistant_completed"
            ] = True
            failure[
                "history_recorded"
            ] = False

            return failure

        if history_result.get(
            "saved"
        ) is not True:

            return {
                "error": True,
                "message":
                    "INVALID_ASSISTANT_BUTTON_HISTORY_RESULT",
                "assistant_completed": True,
                "history_recorded": False,
                "persistence_state_unknown": True
            }

        return result


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

        overview_failure = (
            self._validate_product_decisions_overview(
                overview
            )
        )

        if overview_failure:

            return overview_failure

        decisions = overview["decisions"]

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

    @staticmethod
    def _invalid_product_decision_result(
        code
    ):

        return {
            "error": True,
            "message": code
        }


    def _validate_product_decisions_overview(
        self,
        overview
    ):

        if (
            not isinstance(overview, dict)
            or type(overview.get("error")) is not bool
        ):
            return self._invalid_product_decision_result(
                "INVALID_PRODUCT_DECISIONS_OVERVIEW_RESULT"
            )

        if overview.get("error") is True:
            failure = dict(overview)
            failure.setdefault(
                "message",
                "Не удалось получить решения по товарам"
            )
            return failure

        decisions = overview.get("decisions")
        counts = overview.get("counts")
        proposal_counts = overview.get("proposal_counts")
        total = overview.get("total")
        actionable = overview.get("actionable_proposals_count")

        if (
            not isinstance(decisions, list)
            or not isinstance(counts, dict)
            or not isinstance(proposal_counts, dict)
            or type(total) is not int
            or total < 0
            or total != len(decisions)
            or type(actionable) is not int
            or actionable < 0
            or actionable > total
        ):
            return self._invalid_product_decision_result(
                "INVALID_PRODUCT_DECISIONS_OVERVIEW_RESULT"
            )

        expected_counts = {}
        expected_proposal_counts = {}
        expected_actionable = 0
        seen_skus = set()

        for decision in decisions:
            if not isinstance(decision, dict):
                return self._invalid_product_decision_result(
                    "INVALID_PRODUCT_DECISIONS_OVERVIEW_RESULT"
                )

            sku = decision.get("sku")
            decision_type = decision.get("decision_type")
            priority = decision.get("priority")

            if (
                decision.get("error") is not False
                or not isinstance(sku, str)
                or not sku.strip()
                or sku in seen_skus
                or decision_type not in self.DECISION_PRIORITY_CONTRACT
                or priority
                != self.DECISION_PRIORITY_CONTRACT[decision_type]
            ):
                return self._invalid_product_decision_result(
                    "INVALID_PRODUCT_DECISIONS_OVERVIEW_RESULT"
                )

            seen_skus.add(sku)
            expected_counts[decision_type] = (
                expected_counts.get(decision_type, 0) + 1
            )

            proposal = decision.get("action_proposal")
            if proposal is None:
                continue

            if not isinstance(proposal, dict):
                return self._invalid_product_decision_result(
                    "INVALID_PRODUCT_DECISIONS_OVERVIEW_RESULT"
                )

            action_required = proposal.get("action_required")
            proposal_type = proposal.get("proposal_type")

            if (
                type(action_required) is not bool
                or proposal.get("execution_allowed") is not False
                or proposal.get("automation_status") != "PROHIBITED"
                or (
                    proposal_type is not None
                    and proposal_type not in self.ACTION_PROPOSAL_LABELS
                )
                or (
                    action_required is True
                    and proposal_type is None
                )
            ):
                return self._invalid_product_decision_result(
                    "INVALID_PRODUCT_DECISIONS_OVERVIEW_RESULT"
                )

            if proposal_type is not None:
                expected_proposal_counts[proposal_type] = (
                    expected_proposal_counts.get(proposal_type, 0) + 1
                )

            if action_required is True:
                expected_actionable += 1

        if not self._valid_positive_count_map(
            counts,
            allowed_keys=set(self.DECISION_PRIORITY_CONTRACT),
        ):
            return self._invalid_product_decision_result(
                "INVALID_PRODUCT_DECISIONS_OVERVIEW_RESULT"
            )

        if not self._valid_positive_count_map(
            proposal_counts,
            allowed_keys=set(self.ACTION_PROPOSAL_LABELS),
        ):
            return self._invalid_product_decision_result(
                "INVALID_PRODUCT_DECISIONS_OVERVIEW_RESULT"
            )

        if (
            counts != expected_counts
            or proposal_counts != expected_proposal_counts
            or actionable != expected_actionable
        ):
            return self._invalid_product_decision_result(
                "INVALID_PRODUCT_DECISIONS_OVERVIEW_RESULT"
            )

        return None


    @staticmethod
    def _valid_positive_count_map(values, allowed_keys):
        if not isinstance(values, dict):
            return False

        for key, value in values.items():
            if (
                key not in allowed_keys
                or type(value) is not int
                or value <= 0
            ):
                return False

        return True


    def _validate_product_decision_detail(
        self,
        result
    ):

        if (
            not isinstance(
                result,
                dict
            )
            or type(
                result.get(
                    "error"
                )
            )
            is not bool
        ):

            return self._invalid_product_decision_result(
                "INVALID_PRODUCT_DECISION_DETAIL_RESULT"
            )

        if result.get(
            "error"
        ) is True:

            return None

        if (
            result.get(
                "sku"
            )
            is None
            or not isinstance(
                result.get(
                    "decision_type"
                ),
                str
            )
            or not result.get(
                "decision_type"
            )
            or not isinstance(
                result.get(
                    "priority"
                ),
                str
            )
            or not result.get(
                "priority"
            )
            or not isinstance(
                result.get(
                    "reasons"
                ),
                list
            )
            or not isinstance(
                result.get(
                    "missing_data"
                ),
                list
            )
        ):

            return self._invalid_product_decision_result(
                "INVALID_PRODUCT_DECISION_DETAIL_RESULT"
            )

        return None


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

        result_failure = (
            self._validate_product_decision_detail(
                result
            )
        )

        if result_failure:

            return result_failure

        if result.get(
            "error"
        ) is True:

            return {
                "error": True,
                "message":
                    self._format_product_decision(
                        result
                    ),
                "decision": result
            }

        result = self._with_latest_proposal_status(result, sku)

        response = {
            "error": False,
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

        response = (
            self._with_verified_product_decision_user_action(
                response,
                result,
                sku,
            )
        )

        return response

    def _with_verified_product_decision_user_action(
        self,
        response,
        decision,
        sku,
    ):
        verifier = self.product_decision_persistence_verifier
        guidance_builder = (
            self.product_decision_user_action_guidance_builder
        )
        checklist_builder = (
            self.product_decision_user_action_checklist_builder
        )
        if (
            verifier is None
            or not callable(guidance_builder)
            or not callable(checklist_builder)
        ):
            return response

        verify_latest = getattr(
            verifier,
            "verify_latest",
            None,
        )
        if not callable(verify_latest):
            return response

        requested_sku = str(sku or "").strip()
        if not requested_sku:
            return response

        try:
            verification = verify_latest(requested_sku)
        except Exception:
            return response

        if not self._verified_product_decision_matches_current(
            verification,
            decision,
            requested_sku,
        ):
            return response

        try:
            guidance = guidance_builder(verification)
        except Exception:
            return response

        if not self._valid_verified_user_action_guidance(
            guidance,
            verification,
            requested_sku,
        ):
            return response

        try:
            checklist = checklist_builder(guidance)
        except Exception:
            return response

        if not self._valid_verified_user_action_checklist(
            checklist,
            guidance,
            requested_sku,
        ):
            return response

        enriched = dict(response)
        enriched["verified_user_action_guidance_available"] = True
        enriched["decision_persistence_verification"] = dict(
            verification
        )
        enriched["user_action_guidance"] = dict(guidance)
        enriched["user_action_checklist"] = dict(checklist)
        enriched["message"] = (
            str(response.get("message") or "")
            + "\n\n"
            + self._format_verified_user_action_checklist(checklist)
        )
        return enriched

    @staticmethod
    def _verified_product_decision_matches_current(
        verification,
        decision,
        sku,
    ):
        if (
            not isinstance(verification, dict)
            or verification.get("error") is not False
            or verification.get("status")
            != "PRODUCT_DECISION_PERSISTENCE_VERIFIED"
            or verification.get("verification_source")
            != "DURABLE_HISTORY_READBACK"
            or verification.get("decision_persistence_verified")
            is not True
            or verification.get("externally_verified") is not False
            or verification.get("persistent") is not True
            or verification.get("product_decision_persisted") is not True
            or verification.get("product_decision_mutated") is not False
            or verification.get("ozon_mutation_called") is not False
            or verification.get("execution_allowed") is not False
            or verification.get("execution_ready") is not False
            or verification.get("executed") is not False
            or not isinstance(decision, dict)
            or decision.get("error") is not False
        ):
            return False

        verified_snapshot = verification.get("verified_snapshot")
        if not isinstance(verified_snapshot, dict):
            return False

        verified_recorded_at = verification.get(
            "verified_recorded_at"
        )
        current_recorded_at = decision.get("decision_recorded_at")
        if (
            not isinstance(verified_recorded_at, str)
            or not verified_recorded_at.strip()
            or not isinstance(current_recorded_at, str)
            or current_recorded_at != verified_recorded_at
            or verification.get("sku") != sku
            or verified_snapshot.get("sku") != sku
            or decision.get("sku") != sku
        ):
            return False

        for field in (
            "decision_type",
            "priority",
            "confidence",
        ):
            if (
                decision.get(field)
                != verified_snapshot.get(field)
            ):
                return False

        current_reasons = decision.get("reasons")
        verified_reasons = verified_snapshot.get("reasons")
        return (
            isinstance(current_reasons, list)
            and isinstance(verified_reasons, list)
            and current_reasons == verified_reasons
        )

    @staticmethod
    def _valid_verified_user_action_guidance(
        guidance,
        verification,
        sku,
    ):
        if (
            not isinstance(guidance, dict)
            or guidance.get("error") is not False
            or guidance.get("status")
            != "PRODUCT_DECISION_USER_ACTION_GUIDANCE_READY"
            or guidance.get("sku") != sku
            or guidance.get("decision_persistence_verification_id")
            != verification.get(
                "decision_persistence_verification_id"
            )
            or guidance.get("decision_persistence_application_id")
            != verification.get(
                "decision_persistence_application_id"
            )
            or guidance.get("verified_recorded_at")
            != verification.get("verified_recorded_at")
            or guidance.get("decision_persistence_verified")
            is not True
            or guidance.get("externally_verified") is not False
            or guidance.get("persistent") is not True
            or guidance.get("user_execution_required") is not True
            or guidance.get("automatic_execution_prohibited")
            is not True
            or guidance.get("ozon_mutation_called") is not False
            or guidance.get("execution_allowed") is not False
            or guidance.get("execution_ready") is not False
            or guidance.get("executed") is not False
            or not isinstance(guidance.get("title"), str)
            or not guidance["title"].strip()
            or not isinstance(guidance.get("steps"), list)
            or not guidance["steps"]
            or any(
                not isinstance(step, str) or not step.strip()
                for step in guidance["steps"]
            )
        ):
            return False
        return True

    @staticmethod
    def _valid_verified_user_action_checklist(
        checklist,
        guidance,
        sku,
    ):
        if (
            not isinstance(checklist, dict)
            or checklist.get("error") is not False
            or checklist.get("status")
            != "PRODUCT_DECISION_USER_ACTION_CHECKLIST_READY"
            or checklist.get("sku") != sku
            or checklist.get("user_action_guidance_id")
            != guidance.get("user_action_guidance_id")
            or checklist.get("decision_persistence_verification_id")
            != guidance.get(
                "decision_persistence_verification_id"
            )
            or checklist.get("decision_persistence_application_id")
            != guidance.get(
                "decision_persistence_application_id"
            )
            or checklist.get("verified_recorded_at")
            != guidance.get("verified_recorded_at")
            or checklist.get("decision_persistence_verified")
            is not True
            or checklist.get("externally_verified") is not False
            or checklist.get("persistent") is not True
            or checklist.get("completion_recording_allowed")
            is not False
            or checklist.get("user_execution_required") is not True
            or checklist.get("automatic_execution_prohibited")
            is not True
            or checklist.get("ozon_mutation_called") is not False
            or checklist.get("execution_allowed") is not False
            or checklist.get("execution_ready") is not False
            or checklist.get("executed") is not False
        ):
            return False

        items = checklist.get("items")
        item_count = checklist.get("item_count")
        if (
            not isinstance(items, list)
            or not items
            or type(item_count) is not int
            or item_count != len(items)
            or checklist.get("completed_count") != 0
        ):
            return False

        for position, item in enumerate(items, start=1):
            if (
                not isinstance(item, dict)
                or item.get("position") != position
                or item.get("completion_source") != "USER"
                or item.get("completed") is not False
                or not isinstance(item.get("instruction"), str)
                or not item["instruction"].strip()
            ):
                return False
        return True

    @staticmethod
    def _format_verified_user_action_checklist(checklist):
        lines = [
            "✅ Проверенный ручной чек-лист",
            "",
            str(checklist["title"]),
        ]
        for item in checklist["items"]:
            lines.append(
                str(item["position"])
                + ". "
                + item["instruction"]
            )
        lines.extend([
            "",
            "Автоматическое выполнение отключено.",
        ])
        return "\n".join(lines)

    def _with_latest_proposal_status(self, result, sku):
        result = dict(result or {})
        proposal = dict(result.get("action_proposal") or {})
        history_service = getattr(
            self.product_business_decision_query,
            "decision_history_service",
            None,
        )
        if (
            result.get("decision_history_error") is True
            or history_service is None
            or not proposal.get("proposal_type")
        ):
            return result

        try:
            latest = history_service.latest(sku)
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return result

        if latest is not None and not isinstance(latest, dict):
            return result

        if (
            isinstance(latest, dict)
            and latest.get("sku") == sku
            and latest.get("proposal_type")
            == proposal.get("proposal_type")
            and latest.get("proposal_status")
            in {None, "CONFIRMED", "DISMISSED"}
        ):
            proposal_status = latest.get("proposal_status")
            if proposal_status is not None:
                proposal["proposal_status"] = proposal_status
                result["action_proposal"] = proposal

        draft_service = self._product_action_task_draft_service()
        if draft_service is not None:
            try:
                draft = draft_service.latest_for_sku(sku)
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                draft = None

            if (
                isinstance(draft, dict)
                and draft.get("sku") == sku
                and draft.get("proposal_type")
                == proposal.get("proposal_type")
                and draft.get("decision_recorded_at")
                == result.get("decision_recorded_at")
                and draft.get("executed") is False
                and draft.get("execution_allowed") is False
            ):
                result["action_task_draft"] = dict(draft)

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
        if (
            not isinstance(result, dict)
            or type(result.get("error")) is not bool
        ):
            return {
                "error": True,
                "message": "Не удалось сохранить статус шага",
                "executed": False,
                "execution_allowed": False,
            }
        if result["error"] is True:
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
                "execution_allowed": False,
            }

        task_draft = result.get("task_draft")
        if (
            type(result.get("saved")) is not bool
            or str(result.get("sku") or "").strip()
            != str(sku or "").strip()
            or str(result.get("proposal_type") or "").strip().upper()
            != proposal_type
            or str(result.get("proposal_status") or "").strip().upper()
            != status
            or result.get("executed") is not False
            or result.get("execution_allowed") is not False
            or (
                task_draft is not None
                and (
                    not isinstance(task_draft, dict)
                    or str(task_draft.get("sku") or "").strip()
                    != str(sku or "").strip()
                    or str(
                        task_draft.get("proposal_type") or ""
                    ).strip().upper()
                    != proposal_type
                    or task_draft.get("executed") is not False
                    or task_draft.get("execution_allowed") is not False
                )
            )
        ):
            return {
                "error": True,
                "message": "Не удалось сохранить статус шага",
                "executed": False,
                "execution_allowed": False,
            }

        verb = "подтверждён" if status == "CONFIRMED" else "отклонён"
        message = "Шаг " + verb + " и сохранён."
        if status == "CONFIRMED" and task_draft:
            message += " Создан безопасный черновик задачи."
        message += " Выполнение не запускалось."
        return {
            "error": False,
            "message": message,
            "proposal_status": status,
            "task_draft": task_draft,
            "saved": result["saved"],
            "executed": False,
            "execution_allowed": False,
        }

    def _product_action_task_draft_service(self):
        return getattr(
            self.product_business_decision_query,
            "action_task_draft_service",
            None,
        )

    @staticmethod
    def _task_draft_result_failure(
        code
    ):

        return {
            "error": True,
            "message": code,
            "executed": False,
        }


    @staticmethod
    def _valid_task_draft_item(
        draft
    ):

        if not isinstance(
            draft,
            dict
        ):

            return False

        draft_id = str(
            draft.get(
                "draft_id"
            )
            or ""
        ).strip()
        sku = str(
            draft.get(
                "sku"
            )
            or ""
        ).strip()
        status = draft.get(
            "status"
        )

        return (
            bool(
                draft_id
            )
            and bool(
                sku
            )
            and status in {
                "DRAFT",
                "STALE",
                "DISMISSED",
                "ARCHIVED",
            }
        )


    def _validate_task_draft_summary(
        self,
        summary
    ):

        if (
            not isinstance(
                summary,
                dict
            )
            or type(
                summary.get(
                    "error"
                )
            )
            is not bool
        ):

            return self._task_draft_result_failure(
                "INVALID_PRODUCT_TASK_DRAFT_SUMMARY_RESULT"
            )

        if summary.get(
            "error"
        ) is True:

            return {
                "error": True,
                "message": (
                    summary.get(
                        "message"
                    )
                    or "Черновики задач недоступны"
                ),
                "executed": False,
            }

        counts = summary.get(
            "counts"
        )
        drafts = summary.get(
            "drafts"
        )
        total = summary.get(
            "total"
        )
        executed_count = summary.get(
            "executed_count"
        )
        statuses = {
            "DRAFT",
            "STALE",
            "DISMISSED",
            "ARCHIVED",
        }

        if (
            type(
                total
            )
            is not int
            or total < 0
            or not isinstance(
                counts,
                dict
            )
            or set(
                counts
            )
            != statuses
            or any(
                type(
                    counts.get(
                        status
                    )
                )
                is not int
                or counts.get(
                    status
                )
                < 0
                for status in statuses
            )
            or sum(
                counts.values()
            )
            != total
            or not isinstance(
                drafts,
                list
            )
            or len(
                drafts
            )
            > total
            or any(
                not self._valid_task_draft_item(
                    draft
                )
                for draft in drafts
            )
            or type(
                executed_count
            )
            is not int
            or executed_count != 0
        ):

            return self._task_draft_result_failure(
                "INVALID_PRODUCT_TASK_DRAFT_SUMMARY_RESULT"
            )

        return None


    def _validate_task_draft_list(
        self,
        drafts
    ):

        if (
            not isinstance(
                drafts,
                list
            )
            or any(
                not self._valid_task_draft_item(
                    draft
                )
                for draft in drafts
            )
        ):

            return self._task_draft_result_failure(
                "INVALID_PRODUCT_TASK_DRAFT_LIST_RESULT"
            )

        return None


    def _validate_task_draft_review_queue(
        self,
        queue
    ):

        if (
            not isinstance(
                queue,
                dict
            )
            or type(
                queue.get(
                    "error"
                )
            )
            is not bool
        ):

            return self._task_draft_result_failure(
                "INVALID_PRODUCT_TASK_DRAFT_REVIEW_QUEUE_RESULT"
            )

        if queue.get(
            "error"
        ) is True:

            return {
                "error": True,
                "message": (
                    queue.get(
                        "message"
                    )
                    or "Очередь проверки черновиков недоступна"
                ),
                "executed": False,
            }

        items = queue.get(
            "items"
        )
        counts = queue.get(
            "priority_counts"
        )
        total = queue.get(
            "total_reviewable"
        )
        executed_count = queue.get(
            "executed_count"
        )
        priorities = {
            "URGENT",
            "HIGH",
            "NORMAL",
            "LOW",
        }

        if (
            type(
                total
            )
            is not int
            or total < 0
            or not isinstance(
                counts,
                dict
            )
            or set(
                counts
            )
            != priorities
            or any(
                type(
                    counts.get(
                        priority
                    )
                )
                is not int
                or counts.get(
                    priority
                )
                < 0
                for priority in priorities
            )
            or sum(
                counts.values()
            )
            != total
            or not isinstance(
                items,
                list
            )
            or len(
                items
            )
            > total
            or type(
                executed_count
            )
            is not int
            or executed_count != 0
        ):

            return self._task_draft_result_failure(
                "INVALID_PRODUCT_TASK_DRAFT_REVIEW_QUEUE_RESULT"
            )

        for item in items:

            if (
                not self._valid_task_draft_item(
                    item
                )
                or item.get(
                    "status"
                )
                not in {
                    "DRAFT",
                    "STALE",
                }
                or item.get(
                    "review_priority"
                )
                not in priorities
                or not isinstance(
                    item.get(
                        "review_reasons"
                    ),
                    list
                )
                or any(
                    not isinstance(
                        reason,
                        str
                    )
                    or not reason
                    for reason in item.get(
                        "review_reasons"
                    )
                )
                or item.get(
                    "execution_allowed"
                )
                is not False
                or item.get(
                    "executed"
                )
                is not False
            ):

                return self._task_draft_result_failure(
                    "INVALID_PRODUCT_TASK_DRAFT_REVIEW_QUEUE_RESULT"
                )

        return None


    def _validate_task_draft_readiness(
        self,
        readiness
    ):

        if (
            not isinstance(
                readiness,
                dict
            )
            or type(
                readiness.get(
                    "error"
                )
            )
            is not bool
            or readiness.get(
                "error"
            )
            is not False
            or readiness.get(
                "review_status"
            )
            not in {
                "READY_FOR_REVIEW",
                "NEEDS_DATA_OR_REFRESH",
            }
            or type(
                readiness.get(
                    "review_ready"
                )
            )
            is not bool
            or not isinstance(
                readiness.get(
                    "missing_fields"
                ),
                list
            )
            or any(
                not isinstance(
                    field,
                    str
                )
                or not field
                for field in readiness.get(
                    "missing_fields"
                )
            )
            or readiness.get(
                "execution_ready"
            )
            is not False
            or not isinstance(
                readiness.get(
                    "execution_blockers"
                ),
                list
            )
            or any(
                not isinstance(
                    blocker,
                    str
                )
                or not blocker
                for blocker in readiness.get(
                    "execution_blockers"
                )
            )
            or readiness.get(
                "executed"
            )
            is not False
        ):

            return self._task_draft_result_failure(
                "INVALID_PRODUCT_TASK_DRAFT_READINESS_RESULT"
            )

        return None


    def _validate_task_draft_readiness_summary(
        self,
        summary
    ):

        if (
            not isinstance(
                summary,
                dict
            )
            or type(
                summary.get(
                    "error"
                )
            )
            is not bool
        ):

            return self._task_draft_result_failure(
                "INVALID_PRODUCT_TASK_DRAFT_READINESS_SUMMARY_RESULT"
            )

        if summary.get(
            "error"
        ) is True:

            return {
                "error": True,
                "message": (
                    summary.get(
                        "message"
                    )
                    or "Готовность черновиков недоступна"
                ),
                "executed": False,
            }

        counts = summary.get(
            "counts"
        )
        items = summary.get(
            "items"
        )
        states = {
            "READY_FOR_REVIEW",
            "NEEDS_DATA_OR_REFRESH",
        }

        if (
            not isinstance(
                counts,
                dict
            )
            or set(
                counts
            )
            != states
            or any(
                type(
                    counts.get(
                        state
                    )
                )
                is not int
                or counts.get(
                    state
                )
                < 0
                for state in states
            )
            or not isinstance(
                items,
                list
            )
            or sum(
                counts.values()
            )
            != len(
                items
            )
            or summary.get(
                "execution_ready_count"
            )
            != 0
            or summary.get(
                "executed_count"
            )
            != 0
        ):

            return self._task_draft_result_failure(
                "INVALID_PRODUCT_TASK_DRAFT_READINESS_SUMMARY_RESULT"
            )

        for item in items:

            if not self._valid_task_draft_item(
                item
            ):

                return self._task_draft_result_failure(
                    "INVALID_PRODUCT_TASK_DRAFT_READINESS_SUMMARY_RESULT"
                )

            readiness_error = (
                self._validate_task_draft_readiness(
                    item.get(
                        "readiness"
                    )
                )
            )

            if readiness_error:

                return self._task_draft_result_failure(
                    "INVALID_PRODUCT_TASK_DRAFT_READINESS_SUMMARY_RESULT"
                )

        return None


    def _validate_task_draft_detail_result(
        self,
        result,
        draft_id
    ):

        if (
            not isinstance(
                result,
                dict
            )
            or type(
                result.get(
                    "error"
                )
            )
            is not bool
        ):

            return self._task_draft_result_failure(
                "INVALID_PRODUCT_TASK_DRAFT_DETAIL_RESULT"
            )

        if result.get(
            "error"
        ) is True:

            return None

        draft = result.get(
            "task_draft"
        )
        events = result.get(
            "audit_events"
        )

        if (
            not self._valid_task_draft_item(
                draft
            )
            or str(
                draft.get(
                    "draft_id"
                )
            )
            != str(
                draft_id
            )
            or not isinstance(
                events,
                list
            )
            or any(
                not isinstance(
                    event,
                    dict
                )
                for event in events
            )
            or type(
                result.get(
                    "legacy_history_unavailable"
                )
            )
            is not bool
            or result.get(
                "executed"
            )
            is not False
            or result.get(
                "execution_allowed"
            )
            is not False
        ):

            return self._task_draft_result_failure(
                "INVALID_PRODUCT_TASK_DRAFT_DETAIL_RESULT"
            )

        return None


    def _validate_task_draft_archive_result(
        self,
        result,
        draft_id
    ):

        if (
            not isinstance(
                result,
                dict
            )
            or type(
                result.get(
                    "error"
                )
            )
            is not bool
        ):

            return self._task_draft_result_failure(
                "INVALID_PRODUCT_TASK_DRAFT_ARCHIVE_RESULT"
            )

        if result.get(
            "error"
        ) is True:

            return None

        draft = result.get(
            "task_draft"
        )

        if (
            not self._valid_task_draft_item(
                draft
            )
            or str(
                draft.get(
                    "draft_id"
                )
            )
            != str(
                draft_id
            )
            or draft.get(
                "status"
            )
            != "ARCHIVED"
            or type(
                result.get(
                    "saved"
                )
            )
            is not bool
            or result.get(
                "executed"
            )
            is not False
            or result.get(
                "execution_allowed"
            )
            is not False
        ):

            return self._task_draft_result_failure(
                "INVALID_PRODUCT_TASK_DRAFT_ARCHIVE_RESULT"
            )

        return None


    def _show_product_action_task_drafts(self):
        service = self._product_action_task_draft_service()
        if service is None:
            return {
                "error": True,
                "message": "Черновики задач недоступны",
            }
        summary = service.summary()

        summary_error = (
            self._validate_task_draft_summary(
                summary
            )
        )

        if summary_error:

            return summary_error

        counts = summary[
            "counts"
        ]
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

            source_drafts = (
                service.list_drafts()
            )

            source_error = (
                self._validate_task_draft_list(
                    source_drafts
                )
            )

            if source_error:

                return source_error

            queue = review_queue_service.prioritize(
                source_drafts,
                limit=10,
            )

            queue_error = (
                self._validate_task_draft_review_queue(
                    queue
                )
            )

            if queue_error:

                return queue_error

            drafts = queue[
                "items"
            ]
        else:
            queue = None
            drafts = summary[
                "drafts"
            ]
        readiness_service = getattr(
            self.product_business_decision_query,
            "task_draft_readiness_service",
            None,
        )
        if readiness_service is not None:

            readiness_summary = (
                readiness_service.summarize(
                    drafts
                )
            )

            readiness_error = (
                self._validate_task_draft_readiness_summary(
                    readiness_summary
                )
            )

            if readiness_error:

                return readiness_error

            drafts = readiness_summary[
                "items"
            ]
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
        result = service.archive(
            draft_id
        )

        validation_error = (
            self._validate_task_draft_archive_result(
                result,
                draft_id,
            )
        )

        if validation_error:

            return validation_error

        if result[
            "error"
        ] is True:

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
            "task_draft": result[
                "task_draft"
            ],
            "saved": result[
                "saved"
            ],
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
        result = service.get(
            draft_id
        )

        validation_error = (
            self._validate_task_draft_detail_result(
                result,
                draft_id,
            )
        )

        if validation_error:

            return validation_error

        if result[
            "error"
        ] is True:

            return {
                "error": True,
                "message": "Черновик задачи не найден",
                "executed": False,
            }

        draft = result[
            "task_draft"
        ]
        readiness_service = getattr(
            self.product_business_decision_query,
            "task_draft_readiness_service",
            None,
        )
        readiness = (
            readiness_service.evaluate(
                draft
            )
            if readiness_service is not None
            else None
        )

        if readiness is not None:

            readiness_error = (
                self._validate_task_draft_readiness(
                    readiness
                )
            )

            if readiness_error:

                return readiness_error

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
        events = result[
            "audit_events"
        ]
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
        if (
            not isinstance(result, dict)
            or type(result.get("error")) is not bool
        ):
            return {
                "error": True,
                "message": "Не удалось сохранить оценку решения",
            }
        if result["error"] is True:
            if result.get("code") == "DECISION_HISTORY_NOT_FOUND":
                message = "Сначала откройте актуальное решение по товару"
            else:
                message = "Некорректная оценка решения"
            return {
                "error": True,
                "message": message,
                "feedback": result,
            }

        expected_feedback = str(feedback or "").strip().upper()
        if (
            expected_feedback not in {"USEFUL", "NOT_RELEVANT"}
            or str(result.get("sku") or "").strip()
            != str(sku or "").strip()
            or result.get("feedback") != expected_feedback
            or type(result.get("saved")) is not bool
        ):
            return {
                "error": True,
                "message": "Не удалось сохранить оценку решения",
            }

        label = (
            "решение полезно"
            if result["feedback"] == "USEFUL"
            else "решение неактуально"
        )
        return {
            "error": False,
            "message": "Оценка сохранена: " + label + ".",
            "feedback": result,
        }

    @staticmethod
    def _valid_learning_count(value):
        return type(value) is int and value >= 0

    def _valid_product_decision_learning_summary(self, summary):
        if (
            not isinstance(summary, dict)
            or summary.get("error") is not False
        ):
            return False

        feedback_counts = summary.get("feedback_counts")
        outcome_counts = summary.get("outcome_counts")
        if (
            not isinstance(feedback_counts, dict)
            or set(feedback_counts) != {"USEFUL", "NOT_RELEVANT"}
            or not isinstance(outcome_counts, dict)
            or set(outcome_counts)
            != {
                "PRIORITY_DECREASED",
                "PRIORITY_INCREASED",
                "DECISION_CHANGED",
            }
        ):
            return False

        counts = [
            summary.get("products_count"),
            summary.get("decision_snapshots_count"),
            summary.get("feedback_count"),
            summary.get("outcome_count"),
            feedback_counts.get("USEFUL"),
            feedback_counts.get("NOT_RELEVANT"),
            outcome_counts.get("PRIORITY_DECREASED"),
            outcome_counts.get("PRIORITY_INCREASED"),
            outcome_counts.get("DECISION_CHANGED"),
        ]
        if not all(self._valid_learning_count(value) for value in counts):
            return False

        snapshots = summary["decision_snapshots_count"]
        return (
            summary["feedback_count"]
            == feedback_counts["USEFUL"] + feedback_counts["NOT_RELEVANT"]
            and summary["outcome_count"]
            == (
                outcome_counts["PRIORITY_DECREASED"]
                + outcome_counts["PRIORITY_INCREASED"]
                + outcome_counts["DECISION_CHANGED"]
            )
            and summary["products_count"] <= snapshots
            and summary["feedback_count"] <= snapshots
            and summary["outcome_count"] <= snapshots
        )

    def _show_product_decision_learning_summary(self):
        history_service = self._product_decision_history_service()
        if history_service is None:
            return {
                "error": True,
                "message": "История решений недоступна"
            }

        try:
            summary = history_service.learning_summary()
        except (OSError, TypeError, ValueError, KeyError):
            return {
                "error": True,
                "message": "Итоги обучения решений недоступны",
            }

        if (
            not isinstance(summary, dict)
            or type(summary.get("error")) is not bool
            or summary["error"] is True
            or not self._valid_product_decision_learning_summary(summary)
        ):
            return {
                "error": True,
                "message": "Итоги обучения решений недоступны",
            }

        feedback = summary["feedback_counts"]
        outcomes = summary["outcome_counts"]
        message = "\n".join([
            "📚 Итоги обучения решений",
            "",
            "Товаров в памяти: "
            + str(summary["products_count"]),
            "Снимков решений: "
            + str(summary["decision_snapshots_count"]),
            "Оценок: " + str(summary["feedback_count"]),
            "👍 Полезно: " + str(feedback["USEFUL"]),
            "👎 Неактуально: "
            + str(feedback["NOT_RELEVANT"]),
            "",
            "Наблюдений после оценок: "
            + str(summary["outcome_count"]),
            "Срочность снизилась: "
            + str(outcomes["PRIORITY_DECREASED"]),
            "Срочность выросла: "
            + str(outcomes["PRIORITY_INCREASED"]),
            "Решение изменилось без смены приоритета: "
            + str(outcomes["DECISION_CHANGED"]),
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

        requested_sku = str(sku or "").strip()
        if not requested_sku:
            return {
                "error": True,
                "message": "История решений недоступна",
            }

        try:
            records = history_service.history(requested_sku, limit=5)
        except (OSError, TypeError, ValueError, KeyError):
            return {
                "error": True,
                "message": "История решений недоступна",
            }

        if not isinstance(records, list):
            return {
                "error": True,
                "message": "История решений недоступна",
            }
        if not records:
            return {
                "error": False,
                "message": "История решений по товару пока пуста",
                "decision_history": [],
            }
        if len(records) > 5:
            return {
                "error": True,
                "message": "История решений недоступна",
            }

        for record in records:
            if not isinstance(record, dict):
                return {
                    "error": True,
                    "message": "История решений недоступна",
                }
            record_sku = str(record.get("sku") or "").strip()
            decision_type = record.get("decision_type")
            priority = record.get("priority")
            recorded_at = record.get("recorded_at")
            feedback = record.get("feedback")
            outcome = record.get("outcome")
            if (
                record_sku != requested_sku
                or decision_type not in self.DECISION_LABELS
                or decision_type == "INSUFFICIENT_DATA"
                or priority not in self.PRIORITY_LABELS
                or not isinstance(recorded_at, str)
                or not recorded_at.strip()
                or feedback not in {None, "USEFUL", "NOT_RELEVANT"}
                or (
                    outcome is not None
                    and outcome not in self.DECISION_OUTCOME_LABELS
                )
            ):
                return {
                    "error": True,
                    "message": "История решений недоступна",
                }

        lines = [
            "📚 История решений",
            "",
            "Артикул: " + requested_sku,
        ]
        for index, record in enumerate(records, start=1):
            decision_type = record["decision_type"]
            priority = record["priority"]
            recorded_at = record["recorded_at"]
            lines.extend([
                "",
                str(index) + ". " + recorded_at.split("T", 1)[0],
                self.DECISION_LABELS[decision_type],
                "Приоритет: " + self.PRIORITY_LABELS[priority],
            ])
            feedback = record.get("feedback")
            if feedback is not None:
                lines.append(
                    "Оценка: "
                    + (
                        "Полезно"
                        if feedback == "USEFUL"
                        else "Неактуально"
                    )
                )
            outcome = record.get("outcome")
            if outcome is not None:
                lines.append(
                    "Наблюдение: "
                    + self.DECISION_OUTCOME_LABELS[outcome]
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

        if code == "PRODUCT_DECISION_ACTION_PROPOSAL_RESULT_INVALID":
            return "Не удалось подготовить безопасный следующий шаг"

        if code == "PRODUCT_DECISION_RESULT_INVALID":
            return "Не удалось проверить решение по товару"

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

        validation_error = (
            self._validate_unit_economics_result(
                result
            )
        )

        if validation_error:

            return validation_error

        return {
            "error": result[
                "error"
            ],
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

        result = (
            self.returns_finance_impact_query
            .query(
                sku
            )
        )

        validation_error = (
            self._validate_returns_finance_impact_result(
                result
            )
        )

        if validation_error:

            return validation_error

        return {
            "error": result[
                "error"
            ],
            "message": (
                self._format_returns_finance_impact(
                    result
                )
            ),
            "returns_finance_impact": result
        }


    @staticmethod
    def _invalid_financial_telegram_result(
        code
    ):

        return {
            "error": True,
            "message": code
        }


    def _validate_unit_economics_result(
        self,
        result
    ):

        if (
            not isinstance(
                result,
                dict
            )
            or type(
                result.get(
                    "error"
                )
            )
            is not bool
        ):

            return self._invalid_financial_telegram_result(
                "INVALID_UNIT_ECONOMICS_RESULT"
            )

        if result.get(
            "error"
        ) is True:

            return None

        source = result.get(
            "source"
        )
        sku = result.get(
            "sku"
        )
        available = result.get(
            "available"
        )
        missing_fields = result.get(
            "missing_fields"
        )

        if (
            type(
                available
            )
            is not bool
            or source not in {
                "current",
                "historical",
            }
            or sku is None
            or not str(
                sku
            ).strip()
            or not isinstance(
                missing_fields,
                list
            )
            or any(
                not isinstance(
                    field,
                    str
                )
                or not field
                for field in missing_fields
            )
        ):

            return self._invalid_financial_telegram_result(
                "INVALID_UNIT_ECONOMICS_RESULT"
            )

        return None


    def _validate_returns_finance_impact_result(
        self,
        result
    ):

        if (
            not isinstance(
                result,
                dict
            )
            or type(
                result.get(
                    "error"
                )
            )
            is not bool
        ):

            return self._invalid_financial_telegram_result(
                "INVALID_RETURNS_FINANCE_IMPACT_RESULT"
            )

        if result.get(
            "error"
        ) is True:

            return None

        requested_sku = result.get(
            "requested_sku"
        )
        period_days = result.get(
            "period_days"
        )
        complete = result.get(
            "complete"
        )
        categories = result.get(
            "categories"
        )
        missing_data = result.get(
            "missing_data"
        )

        if (
            not isinstance(
                requested_sku,
                str
            )
            or not requested_sku.strip()
            or type(
                period_days
            )
            is not int
            or period_days <= 0
            or type(
                complete
            )
            is not bool
            or not isinstance(
                categories,
                dict
            )
            or any(
                not isinstance(
                    item,
                    dict
                )
                for item in categories.values()
            )
            or not isinstance(
                missing_data,
                list
            )
            or any(
                not isinstance(
                    field,
                    str
                )
                or not field
                for field in missing_data
            )
        ):

            return self._invalid_financial_telegram_result(
                "INVALID_RETURNS_FINANCE_IMPACT_RESULT"
            )

        return None


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
