class AssistantKeyboardService:


    def build_main_keyboard(
        self
    ):

        return {
            "error": False,

            "type": "inline_keyboard",

            "buttons": [
                {"text": "🏪 Выбрать магазин", "callback": "ozon_stores"},
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
                    "text": "💵 Прибыль за период",
                    "callback": "period_profit"
                },
                {
                    "text": "💸 Внешние расходы",
                    "callback": "external_expenses",
                },
                {
                    "text": "🧪 Экспериментальные расчёты",
                    "callback": "experimental_calculations"
                },
                {
                    "text": "💰 Себестоимость",
                    "callback": "seller_cost"
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
                    "text": "🔎 На что обратить внимание",
                    "callback": "seller_attention",
                },
                {
                    "text": "↩️ Расходы на возвраты",
                    "callback": "returns_finance_impact"
                },
                {
                    "text": "❓ Помощь и команды",
                    "callback": "help"
                }
            ]
        }


    def build_experimental_calculations_keyboard(self):
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {
                    "text": "🏪 Экономика магазина за период",
                    "callback": "experimental_store_economics",
                },
                {
                    "text": "↩️ Главное меню",
                    "callback": "main_menu",
                },
            ],
        }

    def build_external_expenses_period_keyboard(self):
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {"text": label, "callback": "external_expenses:period:" + code}
                for label, code in (
                    ("Сегодня", "TODAY"),
                    ("7 дней", "7D"),
                    ("28 дней", "28D"),
                    ("56 дней", "56D"),
                    ("90 дней", "90D"),
                )
            ]
            + [
                {
                    "text": "📅 Указать период",
                    "callback": "external_expenses:period:custom",
                },
                {
                    "text": "↩️ Главное меню",
                    "callback": "main_menu",
                },
            ],
        }

    def build_external_expenses_period_input_keyboard(self):
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {
                    "text": "↩️ К выбору периода",
                    "callback": "external_expenses",
                },
                {
                    "text": "↩️ Главное меню",
                    "callback": "main_menu",
                },
            ],
        }

    def build_external_expenses_period_view_keyboard(self, view_id):
        token = str(view_id or "")
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {
                    "text": "➕ Добавить расход",
                    "callback": "external_expenses:add:" + token,
                },
                {
                    "text": "✅ Подтвердить полноту периода",
                    "callback": "external_expenses:coverage:" + token,
                },
                {
                    "text": "📅 Выбрать другой период",
                    "callback": "external_expenses",
                },
                {
                    "text": "↩️ Главное меню",
                    "callback": "main_menu",
                },
            ],
        }

    def build_external_expense_input_keyboard(
        self,
        draft_id,
        skip_description=False,
    ):
        token = str(draft_id or "")
        buttons = []
        if skip_description:
            buttons.append({
                "text": "Пропустить описание",
                "callback": "external_expenses:skip-description:" + token,
            })
        buttons.extend([
            {
                "text": "Отмена",
                "callback": "external_expenses:cancel:" + token,
            },
            {
                "text": "↩️ Главное меню",
                "callback": "main_menu",
            },
        ])
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": buttons,
        }

    def build_external_expense_preview_keyboard(
        self,
        draft_id,
        coverage=False,
    ):
        token = str(draft_id or "")
        action = (
            "external_expenses:coverage-confirm:"
            if coverage
            else "external_expenses:expense-confirm:"
        )
        label = (
            "✅ Подтвердить полноту"
            if coverage
            else "✅ Сохранить расход"
        )
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {"text": label, "callback": action + token},
                {
                    "text": "Отмена",
                    "callback": "external_expenses:cancel:" + token,
                },
            ],
        }

    def build_experimental_store_economics_period_keyboard(self):
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {"text": label, "callback": "experimental_store_economics:" + code}
                for label, code in (
                    ("Сегодня", "TODAY"),
                    ("7 дней", "7D"),
                    ("28 дней", "28D"),
                    ("56 дней", "56D"),
                    ("90 дней", "90D"),
                )
            ]
            + [
                {
                    "text": "📅 Указать период",
                    "callback": "experimental_store_economics:custom",
                },
                {
                    "text": "↩️ Эксперименты",
                    "callback": "experimental_calculations",
                },
            ],
        }

    def build_experimental_store_economics_result_keyboard(self):
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {
                    "text": "🔎 Проверить Analytics через API",
                    "callback": "experimental_analytics_api_diagnostic",
                },
                {
                    "text": "🔎 Проверить возвраты через API",
                    "callback": "experimental_returns_api_diagnostic",
                },
                {
                    "text": "📋 Подробности",
                    "callback": "experimental_store_economics_details",
                },
                {
                    "text": "↩️ Эксперименты",
                    "callback": "experimental_calculations",
                },
                {
                    "text": "↩️ Главное меню",
                    "callback": "main_menu",
                },
            ],
        }

    def build_experimental_store_economics_details_keyboard(self):
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {
                    "text": "↩️ К отчёту",
                    "callback": "experimental_store_economics_summary",
                },
                {
                    "text": "↩️ Эксперименты",
                    "callback": "experimental_calculations",
                },
                {
                    "text": "↩️ Главное меню",
                    "callback": "main_menu",
                },
            ],
        }


    def build_period_profit_keyboard(
        self,
        buttons
    ):

        normalized = []

        for item in (buttons or []):
            if not isinstance(item, dict):
                continue

            text = item.get("text")
            callback = item.get("callback_data")

            if not text or not callback:
                continue

            normalized.append({
                "text": str(text),
                "callback": str(callback)
            })

        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": normalized
        }

    def build_period_profit_result_keyboard(self, report_view_id):
        token = str(report_view_id or "").strip()
        if not token:
            return {"error": True, "type": "inline_keyboard", "buttons": []}
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {
                    "text": "📊 Аналитика периода",
                    "callback": "period_profit_analytics:" + token,
                },
                {
                    "text": "🔎 Полнота данных",
                    "callback": "period_profit_completeness:" + token,
                },
            ],
        }

    def build_period_profit_analytics_keyboard(self, report_view_id):
        token = str(report_view_id or "").strip()
        if not token:
            return {"error": True, "type": "inline_keyboard", "buttons": []}
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {"text": "📅 Сравнение периодов", "callback": "period_profit_comparison:" + token},
                {"text": "🧾 Что изменило прибыль", "callback": "period_profit_bridge:" + token},
                {"text": "🛍 Вклад товаров", "callback": "period_profit_sku_contribution:" + token},
                {"text": "🔎 Полнота данных", "callback": "period_profit_completeness:" + token},
                {"text": "↩️ К расчёту", "callback": "period_profit_report:" + token},
                {"text": "Главное меню", "callback": "main_menu"},
            ],
        }

    def build_period_profit_analytics_detail_keyboard(self, report_view_id):
        token = str(report_view_id or "").strip()
        if not token:
            return {"error": True, "type": "inline_keyboard", "buttons": []}
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {"text": "↩️ Аналитика", "callback": "period_profit_analytics:" + token},
                {"text": "↩️ К расчёту", "callback": "period_profit_report:" + token},
                {"text": "Главное меню", "callback": "main_menu"},
            ],
        }

    def build_period_profit_sku_contribution_keyboard(self, report_view_id):
        token = str(report_view_id or "").strip()
        if not token:
            return {"error": True, "type": "inline_keyboard", "buttons": []}
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {"text": "🔎 Выбрать товар", "callback": "period_profit_sku"},
                {"text": "↩️ Аналитика", "callback": "period_profit_analytics:" + token},
                {"text": "↩️ К расчёту", "callback": "period_profit_report:" + token},
                {"text": "Главное меню", "callback": "main_menu"},
            ],
        }

    def build_period_profit_completeness_keyboard(self, report_view_id, actions):
        token = str(report_view_id or "").strip()
        if not token:
            return {"error": True, "type": "inline_keyboard", "buttons": []}
        labels = {
            "cost": ("💰 Себестоимость", "seller_cost"),
            "sku": ("🔎 Проверить SKU", "period_profit_sku"),
            "return_inventory": ("↩️ Состояние возврата", "return_inventory"),
            "external_expenses": ("💸 Внешние расходы", "external_expenses"),
        }
        buttons = []
        for action in actions or []:
            item = labels.get(str(action))
            if item is not None:
                buttons.append({"text": item[0], "callback": item[1]})
        buttons.append({
            "text": "📊 Аналитика периода",
            "callback": "period_profit_analytics:" + token,
        })
        buttons.append({
            "text": "↩️ К расчёту",
            "callback": "period_profit_report:" + token,
        })
        buttons.append({"text": "Главное меню", "callback": "main_menu"})
        return {"error": False, "type": "inline_keyboard", "buttons": buttons}


    def build_unit_economics_keyboard(
        self,
        skus,
        calculator_callback=None,
        product_callbacks=None,
    ):
        buttons = []
        if calculator_callback:
            buttons.append({
                "text": "🧮 Калькулятор цены",
                "callback": str(calculator_callback),
            })
        callbacks = list(product_callbacks or [])
        buttons.extend([
            {
                "text": str(sku),
                "callback": (
                    str(callbacks[index])
                    if index < len(callbacks) and callbacks[index]
                    else "unit_economics:" + str(sku)
                )
            }
            for index, sku in enumerate(skus or [])
        ])
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": buttons,
        }

    def build_unit_economics_detail_keyboard(self, calculator_button=None):
        buttons = []
        if isinstance(calculator_button, dict):
            buttons.append(dict(calculator_button))
        buttons.append({"text": "Юнит-экономика", "callback": "unit_economics"})
        buttons.append({"text": "Главное меню", "callback": "main_menu"})
        return {"error": False, "type": "inline_keyboard", "buttons": buttons}

    def build_unit_price_scenario_keyboard(
        self,
        scenario_id,
        version,
        include_return_mean=False,
        include_price_planning=False,
    ):
        sid = str(scenario_id)
        ver = str(version)
        fields = (
            ("Цена", "price"),
            ("Себестоимость", "cost"),
            ("Комиссия %", "commission_rate"),
            ("Реклама %", "advertising_rate"),
            ("Баллы %", "discount_points_rate"),
        )
        buttons = [
            {"text": label, "callback": f"upc:e:{sid}:{ver}:{field}"}
            for label, field in fields
        ]
        buttons.append({"text": "Параметры расходов", "callback": f"upc:f:{sid}:{ver}"})
        buttons.append({"text": "Реклама 0%", "callback": f"upc:z:{sid}:{ver}"})
        if include_return_mean:
            buttons.append({"text": "Вернуть среднее баллов", "callback": f"upc:b:{sid}:{ver}"})
        if include_price_planning:
            buttons.extend([
                {"text": "Цена для целевой маржи", "callback": f"upc:g:{sid}:{ver}"},
                {"text": "Сравнить цены", "callback": f"upc:q:{sid}:{ver}"},
            ])
        buttons.extend([
            {"text": "Обновить данные", "callback": f"upc:r:{sid}:{ver}"},
            {"text": "Допущения и источники", "callback": f"upc:a:{sid}:{ver}"},
            {"text": "Другой товар", "callback": "upc:m"},
            {"text": "Главное меню", "callback": "main_menu"},
        ])
        return {"error": False, "type": "inline_keyboard", "buttons": buttons}

    def build_unit_price_fee_keyboard(self, scenario_id, version):
        sid = str(scenario_id)
        ver = str(version)
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {"text": "Логистика, ₽/шт.", "callback": f"upc:e:{sid}:{ver}:logistics_per_unit"},
                {"text": "Последняя миля, ₽/шт.", "callback": f"upc:e:{sid}:{ver}:last_mile_per_unit"},
                {"text": "Эквайринг, ₽/шт.", "callback": f"upc:e:{sid}:{ver}:acquiring_per_unit"},
                {"text": "Назад к расчёту", "callback": f"upc:v:{sid}:{ver}"},
                {"text": "Главное меню", "callback": "main_menu"},
            ],
        }

    def build_unit_price_planning_result_keyboard(
        self,
        scenario_id,
        version,
        mode,
        planning_result=None,
        allow_apply=True,
    ):
        sid = str(scenario_id)
        ver = str(version)
        next_action = "q" if mode == "target_margin" else "g"
        next_label = "Сравнить другие цены" if next_action == "q" else "Цена для целевой маржи"
        result = planning_result if isinstance(planning_result, dict) else {}
        buttons = []
        if allow_apply and mode == "target_margin":
            target = result.get("target") or {}
            if target.get("status") == "FOUND" and target.get("goal_reached") is True:
                buttons.append({
                    "text": "Подставить цену для цели",
                    "callback": f"upc:u:{sid}:{ver}:t",
                })
        elif allow_apply and mode == "price_options":
            for index, row in enumerate(result.get("rows") or []):
                if row.get("available") is True:
                    buttons.append({
                        "text": f"Подставить вариант {index + 1}",
                        "callback": f"upc:u:{sid}:{ver}:{index}",
                    })
        buttons.extend([
            {"text": next_label, "callback": f"upc:{next_action}:{sid}:{ver}"},
            {"text": "Назад к расчёту", "callback": f"upc:v:{sid}:{ver}"},
            {"text": "Главное меню", "callback": "main_menu"},
        ])
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": buttons,
        }

    def build_unit_price_cancel_keyboard(self, scenario_id, version):
        sid = str(scenario_id)
        ver = str(version)
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [
                {"text": "Отмена", "callback": f"upc:c:{sid}:{ver}"},
                {"text": "Главное меню", "callback": "main_menu"},
            ],
        }


    def build_product_decisions_keyboard(
        self,
        items,
        page=1,
        total_pages=1,
        include_learning_summary=False,
        include_learning_health=False,
        include_learning_coverage=False,
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

        if include_learning_health:
            buttons.append({
                "text": "🩺 Качество данных обучения",
                "callback": "product_decision_learning_health",
            })

        if include_learning_coverage:
            buttons.append({
                "text": "🧭 Что оценить дальше",
                "callback": "product_decision_learning_coverage",
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

    def build_seller_attention_keyboard(self, priority_skus, missing_skus):
        buttons = []
        seen = set()
        for label, skus in (
            ("Приоритет", priority_skus),
            ("Проверить данные", missing_skus),
        ):
            for sku in skus or []:
                value = str(sku or "").strip()
                callback = "product_decision:" + value
                if (
                    not value
                    or callback in seen
                    or len(callback.encode("utf-8")) > 64
                ):
                    continue
                seen.add(callback)
                buttons.append({
                    "text": ("🔎 " if label == "Приоритет" else "🧩 ")
                    + value,
                    "callback": callback,
                })
        buttons.extend([
            {"text": "🎯 Все решения по товарам", "callback": "product_decisions"},
            {"text": "💵 Прибыль за период", "callback": "period_profit"},
        ])
        return {"error": False, "type": "inline_keyboard", "buttons": buttons}

    def build_product_decision_learning_coverage_keyboard(
        self,
        items,
        limit=10,
    ):
        buttons = []
        if (
            not isinstance(items, list)
            or isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit < 0
        ):
            return {
                "error": True,
                "type": "inline_keyboard",
                "buttons": [],
            }

        valid_states = {
            "NEEDS_USER_FEEDBACK",
            "NO_DECISION_HISTORY",
            "WAITING_FOR_LATER_OBSERVATION",
        }
        labels = {
            "NEEDS_USER_FEEDBACK": "Оценить решение",
            "NO_DECISION_HISTORY": "Открыть решение",
            "WAITING_FOR_LATER_OBSERVATION": "Проверить решение",
        }

        for item in (items or [])[:limit]:
            if not isinstance(item, dict):
                return {
                    "error": True,
                    "type": "inline_keyboard",
                    "buttons": [],
                }
            sku = str(item.get("sku") or "").strip()
            state = item.get("coverage_state")
            if not sku or state not in valid_states:
                return {
                    "error": True,
                    "type": "inline_keyboard",
                    "buttons": [],
                }
            buttons.append({
                "text": labels[state] + " — " + sku,
                "callback": "product_decision:" + sku,
            })

        buttons.append({
            "text": "🎯 Все решения",
            "callback": "product_decisions",
        })
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": buttons,
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
            icon = {
                "URGENT": "🔴",
                "HIGH": "🟠",
                "NORMAL": "🟡",
                "LOW": "⚪",
            }.get(draft.get("review_priority"), "⚪")
            buttons.append({
                "text": icon + " Открыть " + str(draft.get("sku") or "—"),
                "callback": "product_task_draft:view:" + draft_id,
            })
            buttons.append({
                "text": (
                    icon
                    + " Архивировать "
                    + str(draft.get("sku") or "—")
                ),
                "callback": "product_task_draft:archive:" + draft_id,
            })
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": buttons,
        }

    def build_product_task_draft_detail_keyboard(self, draft):
        draft = dict(draft or {})
        if draft.get("status") == "ARCHIVED" or not draft.get("draft_id"):
            buttons = []
        else:
            buttons = [{
                "text": "🗄 Архивировать черновик",
                "callback": (
                    "product_task_draft:archive:"
                    + str(draft.get("draft_id"))
                ),
            }]
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
