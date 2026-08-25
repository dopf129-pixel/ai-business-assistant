class AssistantButtonHandlerService:


    DECISION_LABELS = {
        "REPLENISH_HIGH_PRIORITY": "Высокий приоритет пополнения",
        "REPLENISH_NORMAL": "Рекомендуется пополнение",
        "WATCH_LOW_MARGIN": "Следить за низкой маржой",
        "INVESTIGATE_LOW_PROFIT": "Проверить низкую прибыльность",
        "HOLD_STOCK": "Удерживать текущий запас",
        "INSUFFICIENT_DATA": "Недостаточно данных для решения"
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
        self
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

        products = (
            self.product_business_decision_query
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
                .build_product_decisions_keyboard(
                    skus
                )
            )
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

        return {
            "error": result.get(
                "error",
                False
            ),
            "message": self._format_product_decision(
                result
            ),
            "decision": result
        }


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
            "SKU:",
            str(sku),
            "",
            "Решение:",
            decision_label,
            "",
            "Тип:",
            decision_type,
            "",
            "Приоритет:",
            priority,
            "",
            "Причины:"
        ]

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

        lines.extend(
            [
                "",
                "Уверенность:",
                confidence,
                "",
                "Не учтено:"
            ]
        )

        missing_data = result.get("missing_data") or []

        if missing_data:
            for item in missing_data:
                lines.append(
                    "— "
                    + self.MISSING_DATA_LABELS.get(
                        item,
                        str(item)
                    )
                )
        else:
            lines.append("—")

        return "\n".join(lines)


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

            return product.get(
                "sku"
            )

        try:

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
            sku = self._extract_sku(product)
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
