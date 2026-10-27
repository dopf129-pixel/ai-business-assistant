"""Bounded Telegram flow for confirming a manual FBO commission schedule."""

from copy import deepcopy
from datetime import date, datetime, timezone
from secrets import token_hex
from threading import RLock
from time import monotonic

from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id
from services.unit_price_tariff_input_parser import UnitPriceTariffInputParser


class TelegramUnitPriceTariffProfileRuntimeService:
    PENDING_TTL_SECONDS = 600
    SESSION_TTL_SECONDS = 3600
    MAX_PENDING = 64
    MAX_SESSION_PROFILES = 128

    def __init__(self, repository, calculator_runtime, keyboard_service,
                 clock=None, parser=UnitPriceTariffInputParser):
        self.repository = repository
        self.calculator_runtime = calculator_runtime
        self.keyboard_service = keyboard_service
        self.clock = clock or monotonic
        self.parser = parser
        self._pending = {}
        self._session_profiles = {}
        self._lock = RLock()

    def handle_callback(self, callback, user_id=None):
        value = str(callback or "")
        parts = value.split(":")
        if len(parts) == 4 and parts[:2] == ["upt", "start"]:
            return self._start(parts[2], parts[3], user_id)
        if len(parts) == 4 and parts[:2] == ["upt", "d"]:
            return self._draft_action(parts[2], parts[3], user_id)
        return self._error("UNIT_PRICE_TARIFF_ACTION_STALE")

    def handle_text(self, text, user_id=None):
        context = self._active_context(user_id)
        if context.get("error"):
            stale = self._clear_pending_for_user(str(user_id or "").strip())
            return self._error(context["code"]) if stale else None
        key = (context["user_id"], context["tenant_scope"])
        with self._lock:
            ticket = deepcopy(self._pending.get(key))
        if ticket is None:
            if self._clear_pending_for_other_scopes(context["user_id"], context["tenant_scope"]):
                return self._error("UNIT_PRICE_TARIFF_CONTEXT_CHANGED")
            return None
        if not self._ticket_matches(ticket, context):
            self._remove_pending(key, ticket.get("draft_id"))
            return self._error("UNIT_PRICE_TARIFF_ACTION_STALE")

        parsed = self.parser.parse(text, default_date=date.today())
        if parsed.get("error"):
            return self._input_prompt(
                ticket,
                "Не удалось разобрать тариф. Укажите строку «100 ₽ = 14%» "
                "или диапазон «100–199,99 ₽ = 12%». Можно добавить «Действует с: ГГГГ-ММ-ДД».",
            )
        profile = self._profile_payload(context, parsed)
        if not profile:
            self._remove_pending(key, ticket.get("draft_id"))
            return self._error("UNIT_PRICE_TARIFF_IDENTITY_UNAVAILABLE")
        previous_draft_id = ticket.get("draft_id")
        ticket["payload"] = profile
        ticket["stage"] = "preview"
        ticket["draft_id"] = token_hex(6)
        ticket["previous_draft_id"] = previous_draft_id
        ticket["updated_at"] = self.clock()
        with self._lock:
            current = self._pending.get(key)
            if not isinstance(current, dict) or current.get("draft_id") != ticket.get("previous_draft_id"):
                return self._error("UNIT_PRICE_TARIFF_ACTION_STALE")
            self._pending[key] = deepcopy(ticket)
        return self._preview(ticket)

    def get_session_profile(self, scenario_id, user_id=None):
        context = self._active_context(user_id)
        if context.get("error") or context.get("scenario_id") != str(scenario_id or ""):
            return None
        key = (context["user_id"], context["tenant_scope"], context["scenario_id"])
        with self._lock:
            entry = self._session_profiles.get(key)
            if not isinstance(entry, dict) or self.clock() - entry.get("created_at", 0) > self.SESSION_TTL_SECONDS:
                self._session_profiles.pop(key, None)
                return None
            if entry.get("identity") != context.get("identity"):
                self._session_profiles.pop(key, None)
                return None
            return deepcopy(entry["profile"])

    def clear_pending(self, user_id):
        self._clear_pending_for_user(str(user_id or "").strip())

    def clear_user_state(self, user_id):
        user = str(user_id or "").strip()
        with self._lock:
            for key in [key for key in self._pending if key[0] == user]:
                self._pending.pop(key, None)
            for key in [key for key in self._session_profiles if key[0] == user]:
                self._session_profiles.pop(key, None)

    def _start(self, scenario_id, version_text, user_id):
        try:
            version = int(version_text)
        except (TypeError, ValueError):
            return self._error("UNIT_PRICE_TARIFF_ACTION_STALE")
        context = self._active_context(user_id, scenario_id, version)
        if context.get("error"):
            return self._error(context["code"])
        if context.get("scheme") != "FBO":
            return self._error("UNIT_PRICE_TARIFF_FBO_ONLY")
        if any(not context["identity"].get(field) for field in ("product_id", "offer_id", "sku")):
            return self._error("UNIT_PRICE_TARIFF_IDENTITY_UNAVAILABLE")
        self._clear_pending_for_other_scopes(context["user_id"], context["tenant_scope"])
        key = (context["user_id"], context["tenant_scope"])
        ticket = {
            "user_id": context["user_id"],
            "tenant_scope": context["tenant_scope"],
            "owner_id": context["owner_id"],
            "store_id": context["store_id"],
            "scenario_id": context["scenario_id"],
            "scenario_version": version,
            "identity": context["identity"],
            "scheme": context["scheme"],
            "draft_id": token_hex(6),
            "stage": "input",
            "created_at": self.clock(),
            "updated_at": self.clock(),
        }
        with self._lock:
            self._pending[key] = ticket
            while len(self._pending) > self.MAX_PENDING:
                self._pending.pop(next(iter(self._pending)))
        return self._input_prompt(ticket)

    def _draft_action(self, draft_id, action, user_id):
        context = self._active_context(user_id)
        if context.get("error"):
            return self._error("UNIT_PRICE_TARIFF_ACTION_STALE")
        key = (context["user_id"], context["tenant_scope"])
        with self._lock:
            ticket = deepcopy(self._pending.get(key))
        if (not isinstance(ticket, dict) or ticket.get("draft_id") != draft_id
                or ticket.get("stage") not in {"input", "preview"}
                or not self._ticket_matches(ticket, context)):
            return self._error("UNIT_PRICE_TARIFF_ACTION_STALE")
        if action == "refresh":
            if not self._remove_pending(key, draft_id):
                return self._error("UNIT_PRICE_TARIFF_ACTION_STALE")
            refreshed = self.calculator_runtime.handle_callback(
                f"upc:r:{ticket['scenario_id']}:{ticket['scenario_version']}", user_id=user_id
            )
            return self._prepend_notice(refreshed, "Данные Ozon обновлены; проверьте актуальную цену. Источник подтверждает текущую точку, но не всю сетку ставок.")
        if action == "cancel":
            if not self._remove_pending(key, draft_id):
                return self._error("UNIT_PRICE_TARIFF_ACTION_STALE")
            return self._return_to_scenario(ticket, user_id, "Ввод тарифа отменён.")
        if ticket.get("stage") != "preview":
            return self._error("UNIT_PRICE_TARIFF_ACTION_STALE")
        if action == "edit":
            with self._lock:
                current = self._pending.get(key)
                if (not isinstance(current, dict) or current.get("draft_id") != draft_id
                        or current.get("stage") != "preview"):
                    return self._error("UNIT_PRICE_TARIFF_ACTION_STALE")
                current["draft_id"] = token_hex(6)
                current["stage"] = "input"
                current.pop("payload", None)
                current["updated_at"] = self.clock()
                ticket = deepcopy(current)
            return self._input_prompt(ticket, "Отправьте исправленные ставки.")
        if action not in {"save", "session"}:
            return self._error("UNIT_PRICE_TARIFF_ACTION_STALE")
        with self._lock:
            current = self._pending.get(key)
            if not isinstance(current, dict) or current.get("draft_id") != draft_id or current.get("stage") != "preview":
                return self._error("UNIT_PRICE_TARIFF_ACTION_STALE")
            current["stage"] = "confirming"
            payload = deepcopy(current.get("payload"))
            ticket = deepcopy(current)
        if action == "session":
            profile = self._session_profile(payload, ticket)
            result = {"error": False, "status": "UNIT_PRICE_TARIFF_SESSION_ONLY", "profile": profile}
        else:
            result = self._save_profile(ticket, payload)
        if result.get("error"):
            with self._lock:
                current = self._pending.get(key)
                if isinstance(current, dict) and current.get("draft_id") == draft_id:
                    current["stage"] = "preview"
            if result.get("code") in {"PLANNING_STORAGE_UNAVAILABLE", "PLANNING_TARIFF_PROFILE_QUOTA_REACHED"}:
                return self._preview(ticket, notice="Постоянное сохранение недоступно. Вы можете применить тариф только к этой сессии.")
            return self._error(result.get("code", "UNIT_PRICE_TARIFF_SAVE_FAILED"))
        self._remove_pending(key, draft_id)
        if action == "session":
            cache_key = (ticket["user_id"], ticket["tenant_scope"], ticket["scenario_id"])
            with self._lock:
                self._session_profiles[cache_key] = {
                    "identity": deepcopy(ticket["identity"]),
                    "profile": deepcopy(result["profile"]),
                    "created_at": self.clock(),
                }
                while len(self._session_profiles) > self.MAX_SESSION_PROFILES:
                    self._session_profiles.pop(next(iter(self._session_profiles)))
            notice = "Тариф действует только в этой сессии и не сохранён между перезапусками."
        else:
            notice = f"Тариф сохранён: редакция {result['revision']}. Источник — ручное подтверждение продавца."
        return self._return_to_scenario(ticket, user_id, notice)

    def _save_profile(self, ticket, payload):
        listed = self.repository.list_tariff_profiles(
            identity=payload["identity"], owner_id=ticket["owner_id"], store_id=ticket["store_id"],
        )
        if listed.get("error"):
            return listed
        items = listed.get("items") or []
        if len(items) > 1:
            return {"error": True, "code": "PLANNING_TARIFF_PROFILE_IDENTITY_CONFLICT"}
        key = "upt-tariff-" + ticket["draft_id"]
        if not items:
            return self.repository.create_tariff_profile(
                payload, idempotency_key=key, owner_id=ticket["owner_id"], store_id=ticket["store_id"],
            )
        profile = self.repository.get_tariff_profile(
            items[0]["profile_id"], owner_id=ticket["owner_id"], store_id=ticket["store_id"],
        )
        if profile.get("error"):
            return profile
        return self.repository.update_tariff_profile(
            items[0]["profile_id"], payload,
            expected_revision=profile["revision"],
            expected_state_revision=profile["state_revision"],
            idempotency_key=key, owner_id=ticket["owner_id"], store_id=ticket["store_id"],
        )

    def _profile_payload(self, context, parsed):
        identity = context.get("identity") or {}
        required = ("product_id", "offer_id", "sku")
        if any(not isinstance(identity.get(key), str) or not identity[key].strip() for key in required):
            return None
        return {
            "profile_schema_version": 1,
            "identity": {key: identity[key] for key in required},
            "sale_schema": "FBO",
            "price_basis": "SELLER_PRICE_RUB",
            "currency": "RUB",
            "origin": "MANUAL_SELLER_ASSUMPTION",
            "confirmed_by_owner": True,
            "effective_from": parsed["effective_from"],
            "effective_to": None,
            "bands": deepcopy(parsed["bands"]),
        }

    def _session_profile(self, payload, ticket):
        return {
            **deepcopy(payload),
            "profile_id": "session-" + ticket["draft_id"],
            "owner_id": ticket["owner_id"],
            "store_id": ticket["store_id"],
            "revision": 1,
            "state_revision": 1,
            "origin": "MANUAL_SELLER_ASSUMPTION",
            "confirmed_by_owner": True,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }

    def _active_context(self, user_id, scenario_id=None, version=None):
        user = str(user_id or "").strip()
        tenant_scope = str(get_current_tenant_user_id() or "").strip()
        owner, store = split_store_tenant_scope(tenant_scope)
        if not user or not owner or owner != user or not store:
            return {"error": True, "code": "UNIT_PRICE_SCENARIO_TENANT_MISMATCH"}
        active = self.calculator_runtime.active_scenario_identity(user)
        if not isinstance(active, dict):
            return {"error": True, "code": "UNIT_PRICE_TARIFF_ACTION_STALE"}
        selected_id = str(scenario_id if scenario_id is not None else active.get("scenario_id") or "")
        try:
            selected_version = int(version if version is not None else active.get("version"))
        except (TypeError, ValueError):
            return {"error": True, "code": "UNIT_PRICE_TARIFF_ACTION_STALE"}
        if (active.get("scenario_id") != selected_id or active.get("version") != selected_version
                or active.get("tenant_scope") != tenant_scope):
            return {"error": True, "code": "UNIT_PRICE_TARIFF_ACTION_STALE"}
        result = self.calculator_runtime.get_sensitivity_context(selected_id, selected_version, user_id=user)
        if not isinstance(result, dict) or result.get("error"):
            return {"error": True, "code": "UNIT_PRICE_TARIFF_ACTION_STALE"}
        identity = result.get("identity") or {}
        snapshot = result.get("snapshot") or {}
        product = snapshot.get("product") or {}
        if identity.get("tenant_scope") != tenant_scope:
            return {"error": True, "code": "UNIT_PRICE_SCENARIO_TENANT_MISMATCH"}
        return {
            "error": False, "user_id": user, "tenant_scope": tenant_scope,
            "owner_id": owner, "store_id": store, "scenario_id": selected_id,
            "scenario_version": selected_version,
            "identity": {key: str(identity.get(key) or "") for key in ("product_id", "offer_id", "sku")},
            "scheme": str(product.get("scheme") or "").upper(),
            "result": result,
        }

    def _ticket_matches(self, ticket, context):
        if not isinstance(ticket, dict):
            return False
        if self.clock() - ticket.get("updated_at", 0) > self.PENDING_TTL_SECONDS:
            return False
        return all(ticket.get(key) == context.get(key) for key in (
            "user_id", "tenant_scope", "owner_id", "store_id", "scenario_id", "scenario_version", "identity", "scheme",
        ))

    def _input_prompt(self, ticket, notice=None):
        text = ["Укажите комиссию Ozon для цены продавца в рублях.",
                "Можно одной строкой: 100 ₽ = 14%.",
                "Или несколько диапазонов по строкам: 0,01–99,99 ₽ = 12%; 100–199,99 ₽ = 14%.",
                "Для интервалов укажите точные границы в копейках без пересечений.",
                "При желании первой строкой задайте дату: Действует с: 2026-10-27.",
                "Тариф будет помечен как вручную подтверждённый. Введите данные одним сообщением."]
        if notice:
            text.insert(0, notice)
        return self._response("UNIT_PRICE_TARIFF_INPUT", "\n".join(text), self._input_keyboard(ticket))

    def _input_keyboard(self, ticket):
        return {"error": False, "type": "inline_keyboard", "buttons": [
            {"text": "Отмена", "callback": f"upt:d:{ticket['draft_id']}:cancel"},
            {"text": "Обновить цену Ozon", "callback": f"upt:d:{ticket['draft_id']}:refresh"},
        ]}

    def _preview(self, ticket, notice=None):
        payload = ticket.get("payload") or {}
        bands = payload.get("bands") or []
        lines = ["Проверьте ручной тариф комиссии Ozon:",
                 f"SKU {payload.get('identity', {}).get('sku')} · FBO · цена продавца · действует с {payload.get('effective_from')}."]
        for band in bands:
            lower = self._price(band["price_from_cents"])
            upper = self._price(band["price_to_cents"])
            span = lower if band["price_from_cents"] == band["price_to_cents"] else f"{lower}–{upper}"
            lines.append(f"• {span} ₽: {band['commission_rate']}%")
        lines.append("Источник: вручную введено и подтверждается продавцом; это не тариф, подтверждённый Ozon API.")
        if notice:
            lines.insert(0, notice)
        buttons = [
            {"text": "✅ Сохранить для SKU", "callback": f"upt:d:{ticket['draft_id']}:save"},
            {"text": "Только для этой сессии", "callback": f"upt:d:{ticket['draft_id']}:session"},
            {"text": "Изменить", "callback": f"upt:d:{ticket['draft_id']}:edit"},
            {"text": "Обновить цену Ozon", "callback": f"upt:d:{ticket['draft_id']}:refresh"},
            {"text": "Отмена", "callback": f"upt:d:{ticket['draft_id']}:cancel"},
        ]
        return self._response("UNIT_PRICE_TARIFF_PREVIEW", "\n".join(lines), {"error": False, "type": "inline_keyboard", "buttons": buttons})

    def _return_to_scenario(self, ticket, user_id, notice):
        result = self.calculator_runtime.handle_callback(
            f"upc:v:{ticket['scenario_id']}:{ticket['scenario_version']}", user_id=user_id
        )
        return self._prepend_notice(result, notice)

    @staticmethod
    def _prepend_notice(result, notice):
        if not isinstance(result, dict):
            return result
        output = dict(result)
        output["message"] = (str(notice) + "\n\n" + str(output.get("message") or ""))[:3500]
        return output

    @staticmethod
    def _price(cents):
        whole, fraction = divmod(int(cents), 100)
        return str(whole) if fraction == 0 else f"{whole}.{fraction:02d}"

    def _remove_pending(self, key, draft_id):
        with self._lock:
            current = self._pending.get(key)
            if isinstance(current, dict) and current.get("draft_id") == draft_id:
                self._pending.pop(key, None)
                return True
        return False

    def _clear_pending_for_user(self, user):
        removed = False
        with self._lock:
            for key in [key for key in self._pending if key[0] == user]:
                self._pending.pop(key, None)
                removed = True
        return removed

    def _clear_pending_for_other_scopes(self, user, scope):
        removed = False
        with self._lock:
            for key in [key for key in self._pending if key[0] == user and key[1] != scope]:
                self._pending.pop(key, None)
                removed = True
        return removed

    @staticmethod
    def _response(status, message, keyboard):
        return {"error": False, "status": status, "message": message, "keyboard": keyboard,
                "read_only": True, "executed": False}

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "message": "Действие с тарифом устарело или сейчас недоступно. Начните ввод заново.",
                "read_only": True, "executed": False}
