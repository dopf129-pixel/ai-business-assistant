class TelegramOnboardingService:
    """Resume setup from production account and tax configuration sources."""

    TAX_MODES = {"NONE", "USN_INCOME", "USN_INCOME_MINUS_EXPENSES"}

    def __init__(
        self,
        account_service,
        tax_configuration_service,
        seller_cost_service=None,
        performance_account_service=None,
    ):
        self.account_service = account_service
        self.tax_configuration_service = tax_configuration_service
        self.seller_cost_service = seller_cost_service
        self.performance_account_service = performance_account_service
        self._pending = {}

    def start(self, user_id, main_keyboard):
        user_key = self._user_key(user_id)
        if user_key is None:
            return self._error("ONBOARDING_USER_INVALID")
        account = self.account_service.status(user_key)
        if not isinstance(account, dict) or type(account.get("error")) is not bool:
            return self._error("ONBOARDING_OZON_STATUS_INVALID")
        if account.get("error") is True:
            return self._error("ONBOARDING_OZON_STATUS_UNAVAILABLE")
        if account.get("connected") is not True:
            self._pending[user_key] = "OZON"
            return {"error": False, "text": "Я помогу считать прибыль и находить риски по данным Ozon.\n\nШаг 1 из 3 — подключите кабинет Ozon. Отправьте одной строкой CLIENT_ID и API_KEY через пробел. Ключ будет проверен только READ-ONLY запросом, зашифрован и никогда не показан обратно.", "onboarding": True, "required_step": "OZON_CREDENTIALS", "read_only_ozon": True, "executed_ozon": False}
        return self._tax_or_complete(user_key, main_keyboard)

    def handle_text(self, user_id, text, main_keyboard):
        user_key = self._user_key(user_id)
        stage = self._pending.get(user_key)
        if stage == "OZON":
            parts = str(text or "").strip().split(maxsplit=1)
            if len(parts) != 2:
                return self._handled("Отправьте CLIENT_ID и API_KEY одной строкой через пробел.")
            result = self.account_service.connect(user_key, parts[0], parts[1])
            if not isinstance(result, dict) or result.get("error") is not False:
                return self._handled("Не удалось проверить и сохранить подключение. Проверьте данные и повторите.")
            return self._tax_or_complete(user_key, main_keyboard, handled=True)
        if stage == "PERFORMANCE":
            parts = str(text or "").strip().split(maxsplit=1)
            if len(parts) != 2:
                return self._handled(
                    "Отправьте Performance Client ID и Client Secret одной "
                    "строкой через пробел. Обычный Seller API Key не подходит."
                )
            result = self.performance_account_service.connect(
                user_key, parts[0], parts[1]
            )
            if not isinstance(result, dict) or result.get("error") is not False:
                return self._handled(
                    "Не удалось проверить рекламный доступ. Проверьте "
                    "Performance Client ID и Client Secret."
                )
            if result.get("status") != "OZON_PERFORMANCE_CONNECTED":
                return {**result, "handled": True, "onboarding": True}
            self._pending.pop(user_key, None)
            completed = self._complete(main_keyboard, handled=True)
            completed["message"] = result["message"]
            completed["text"] = result["message"]
            return completed
        if stage and stage.startswith("TAX_RATE:"):
            mode = stage.split(":", 1)[1]
            try:
                rate = float(str(text or "").strip().replace(",", "."))
            except (TypeError, ValueError, OverflowError):
                return self._handled("Введите налоговую ставку числом от 0 до 100.")
            saved = self.tax_configuration_service.save_policy(mode, tax_rate=rate)
            if not isinstance(saved, dict) or saved.get("error") is not False:
                return self._handled("Не удалось сохранить налоговую ставку. Введите число от 0 до 100.")
            self._pending.pop(user_key, None)
            return self._complete(main_keyboard, handled=True)
        return {"error": False, "handled": False}

    def handle_callback(self, user_id, callback, main_keyboard):
        value = str(callback or "").strip()
        if value == "onboarding_ads_help":
            user_key = self._user_key(user_id)
            if user_key is None or self.performance_account_service is None:
                return self._error("ONBOARDING_PERFORMANCE_UNAVAILABLE")
            self._pending[user_key] = "PERFORMANCE"
            return {
                "error": False,
                "message": (
                    "Откройте Ozon Seller → Настройки → API-ключи → "
                    "Performance API и создайте отдельные рекламные реквизиты.\n\n"
                    "Отправьте одной строкой:\n"
                    "PERFORMANCE_CLIENT_ID CLIENT_SECRET\n\n"
                    "Это не обычный Seller API Key. Секрет будет сохранён "
                    "зашифрованно и не появится в ответах бота."
                ),
                "onboarding": True,
                "required_step": "OZON_PERFORMANCE_CREDENTIALS",
            }
        prefix = "onboarding_tax:"
        if not value.startswith(prefix):
            return None
        user_key = self._user_key(user_id)
        mode = value[len(prefix):].upper()
        if user_key is None or mode not in self.TAX_MODES:
            return self._error("ONBOARDING_TAX_SELECTION_INVALID")
        if mode == "NONE":
            saved = self.tax_configuration_service.save_policy("NONE")
            if not isinstance(saved, dict) or saved.get("error") is not False:
                return self._error("ONBOARDING_TAX_SAVE_FAILED")
            self._pending.pop(user_key, None)
            return self._complete(main_keyboard)
        self._pending[user_key] = "TAX_RATE:" + mode
        return {"error": False, "message": "Введите вашу налоговую ставку в процентах, например 6.", "onboarding": True, "required_step": "TAX_RATE"}

    def _tax_or_complete(self, user_key, main_keyboard, handled=False):
        policy = self.tax_configuration_service.get_policy()
        if not isinstance(policy, dict) or policy.get("error") is True:
            return self._error("ONBOARDING_TAX_STATUS_UNAVAILABLE")
        if policy.get("configured") is True:
            self._pending.pop(user_key, None)
            return self._complete(main_keyboard, handled=handled)
        self._pending[user_key] = "TAX_MODE"
        result = {"error": False, "message": "Шаг 2 из 3 — выберите налоговый режим:", "keyboard": {"error": False, "type": "inline_keyboard", "buttons": [{"text": "УСН Доходы", "callback": "onboarding_tax:USN_INCOME"}, {"text": "УСН Доходы − расходы", "callback": "onboarding_tax:USN_INCOME_MINUS_EXPENSES"}, {"text": "Без налога", "callback": "onboarding_tax:NONE"}]}, "onboarding": True, "required_step": "TAX_CONFIGURATION"}
        if handled:
            result["handled"] = True
        return result

    def _complete(self, main_keyboard, handled=False):
        cost_menu = self._seller_cost_menu()
        coverage = (
            cost_menu.get("cost_coverage")
            if isinstance(cost_menu, dict) and cost_menu.get("error") is False
            else None
        )
        if (
            isinstance(coverage, dict)
            and self._non_negative_integer(coverage.get("total")) is not None
            and self._non_negative_integer(coverage.get("missing")) == 0
        ):
            result = {
                "error": False,
                "text": (
                    "✅ Настройка завершена. Себестоимость заполнена для всех "
                    "товаров каталога."
                ),
                "message": (
                    "✅ Настройка завершена. Себестоимость заполнена для всех "
                    "товаров каталога."
                ),
                "keyboard": main_keyboard,
                "onboarding_complete": True,
                "cost_coverage": dict(coverage),
                "optional_steps": ["HISTORICAL_COST_REFINEMENT"],
            }
            self._append_performance_step(result)
            if handled:
                result["handled"] = True
            return result
        result = {
            "error": False,
            "text": "Шаг 3 из 3 — укажите себестоимость товаров. Без неё прибыль за период будет неполной.\n\nНажмите «Указать себестоимость»: бот покажет товары без цены, а вы будете отправлять только сумму. Первую указанную себестоимость бот применит ко всей доступной истории продаж, чтобы вы сразу могли смотреть прибыль за прошлые периоды. Если раньше себестоимость отличалась, историю можно будет уточнить позже. Можно сделать это позже.",
            "message": "Шаг 3 из 3 — укажите себестоимость товаров. Первую цену применим ко всей доступной истории продаж.",
            "keyboard": {"error": False, "type": "inline_keyboard", "buttons": [{"text": "💰 Указать себестоимость", "callback": "seller_cost"}, {"text": "⏭ Сделать позже", "callback": "main_menu"}]},
            "onboarding_complete": True,
            "optional_steps": ["SELLER_COST", "HISTORICAL_COST_REFINEMENT"],
        }
        self._append_performance_step(result)
        if handled:
            result["handled"] = True
        return result

    def _append_performance_step(self, result):
        service = self.performance_account_service
        if service is None:
            return
        try:
            status = service.status(self._current_user_for_status())
        except Exception:
            status = None
        if isinstance(status, dict) and status.get("connected") is True:
            result.setdefault("optional_steps", []).append("OZON_PERFORMANCE")
            return
        note = (
            "\n\n📣 Чтобы прибыль по SKU учитывала рекламу, подключите "
            "отдельный Performance API."
        )
        result["text"] = str(result.get("text") or result.get("message") or "") + note
        result["message"] = str(result.get("message") or result.get("text") or "") + note
        keyboard = dict(result.get("keyboard") or {})
        buttons = list(keyboard.get("buttons") or [])
        buttons.append({
            "text": "📣 Подключить учёт рекламы",
            "callback": "onboarding_ads_help",
        })
        keyboard.update({"error": False, "type": "inline_keyboard", "buttons": buttons})
        result["keyboard"] = keyboard
        result.setdefault("optional_steps", []).append("OZON_PERFORMANCE")

    def _current_user_for_status(self):
        # start()/handle_text() have already established the active tenant in
        # TelegramBotService; repository lookup therefore resolves its store.
        from services.tenant_context import get_current_tenant_user_id
        return get_current_tenant_user_id()

    def _seller_cost_menu(self):
        opener = getattr(self.seller_cost_service, "open_menu", None)
        if not callable(opener):
            return None
        try:
            return opener()
        except Exception:
            return None

    @staticmethod
    def _non_negative_integer(value):
        if isinstance(value, bool):
            return None
        try:
            number = int(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return number if number >= 0 else None

    @staticmethod
    def _handled(message):
        return {"error": False, "handled": True, "message": message, "onboarding": True}

    @staticmethod
    def _user_key(user_id):
        if user_id is None or isinstance(user_id, bool):
            return None
        value = str(user_id).strip()
        return value or None

    @staticmethod
    def _error(code):
        return {"error": True, "message": "ONBOARDING_UNAVAILABLE", "code": code}
