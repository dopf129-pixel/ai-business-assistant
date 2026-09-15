class TelegramOnboardingService:
    """Resume setup from production account and tax configuration sources."""

    TAX_MODES = {"NONE", "USN_INCOME", "USN_INCOME_MINUS_EXPENSES"}

    def __init__(self, account_service, tax_configuration_service):
        self.account_service = account_service
        self.tax_configuration_service = tax_configuration_service
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

    @staticmethod
    def _complete(main_keyboard, handled=False):
        result = {
            "error": False,
            "text": "Шаг 3 из 3 — укажите себестоимость товаров. Без неё прибыль за период будет неполной.\n\nНажмите «Указать себестоимость»: бот покажет товары без цены, а вы будете отправлять только сумму. Можно сделать это позже.",
            "message": "Шаг 3 из 3 — укажите себестоимость товаров. Без неё прибыль за период будет неполной.",
            "keyboard": {"error": False, "type": "inline_keyboard", "buttons": [{"text": "💰 Указать себестоимость", "callback": "seller_cost"}, {"text": "⏭ Сделать позже", "callback": "main_menu"}]},
            "onboarding_complete": True,
            "optional_steps": ["SELLER_COST", "HISTORICAL_COST"],
        }
        if handled:
            result["handled"] = True
        return result

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
