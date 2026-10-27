"""Bounded Telegram flow for confirming a manual FBO commission schedule."""

from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from secrets import token_hex
from threading import RLock
from time import monotonic

from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id
from services.unit_price_tariff_input_parser import UnitPriceTariffInputParser
from services.unit_price_tariff_resolver import UnitPriceTariffResolver
from services.unit_price_tariff_source import UnitPriceTariffSource
from services.unit_price_tariff_snapshot_adapter import UnitPriceTariffSnapshotAdapter


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
        self.tariff_resolver = UnitPriceTariffResolver()
        self.tariff_source = UnitPriceTariffSource()
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

    def resolve_for_scenario(self, scenario_id, version, seller_price, user_id=None,
                             *, session_profile_only=False):
        """Resolve the tariff for one exact active scenario price, without API reads."""
        if type(session_profile_only) is not bool:
            return {"error": True, "code": "UNIT_PRICE_TARIFF_ACTION_STALE"}
        context = self._active_context(user_id, scenario_id, version)
        if context.get("error"):
            return {"error": True, "code": context["code"]}
        cents = self._price_to_cents(seller_price)
        if cents is None:
            return {"error": True, "code": "UNIT_PRICE_TARIFF_PRICE_INVALID"}
        result = context["result"]
        snapshot = result.get("snapshot") or {}
        identity = {
            "owner_id": context["owner_id"],
            "store_id": context["store_id"],
            **context["identity"],
        }
        current_point = self.tariff_source.from_scenario_snapshot(snapshot)
        source_fresh = (
            type(result.get("source_age_seconds")) in {int, float}
            and type(result.get("source_ttl_seconds")) in {int, float}
            and result.get("source_ttl_seconds", 0) > 0
            and result.get("source_age_seconds", float("inf")) < result.get("source_ttl_seconds", 0)
        )
        profiles = (
            list(current_point.get("profiles") or [])
            if source_fresh and not session_profile_only else []
        )
        source_price_cents = current_point.get("current_price_cents")
        current_date = self._effective_date(
            (snapshot.get("source_periods") or {}).get("seller_price_as_of")
        ) if source_fresh and cents == source_price_cents else None
        effective_date = current_date or date.today().isoformat()

        if not session_profile_only:
            listed = self.repository.list_tariff_profiles(
                identity=context["identity"], owner_id=context["owner_id"],
                store_id=context["store_id"], limit=self.repository.MAX_TARIFF_PAGE_SIZE,
            )
            if listed.get("error"):
                return {"error": True, "code": listed.get("code") or "PLANNING_STORAGE_UNAVAILABLE"}
            if listed.get("has_more"):
                return {
                    "error": False, "available": False, "status": "SOURCE_UNAVAILABLE",
                    "reason": "PROFILE_LIMIT", "commission_rate": None,
                    "price_basis": "SELLER_PRICE_RUB", "seller_price_cents": cents,
                    "effective_date": effective_date, "selected_profile": None,
                    "candidate_profiles": profiles,
                }
            for item in listed.get("items") or []:
                record = self.repository.get_tariff_profile(
                    item.get("profile_id"), owner_id=context["owner_id"],
                    store_id=context["store_id"],
                )
                if record.get("error") or record.get("status") != "ACTIVE":
                    return {
                        "error": False, "available": False, "status": "SOURCE_UNAVAILABLE",
                        "reason": "PROFILE_SOURCE_UNAVAILABLE", "commission_rate": None,
                        "price_basis": "SELLER_PRICE_RUB", "seller_price_cents": cents,
                        "effective_date": effective_date, "selected_profile": None,
                        "candidate_profiles": profiles,
                    }
                profiles.append(record.get("profile"))
        session_profile = self.get_session_profile(scenario_id, user_id=user_id)
        if (session_profile is not None and not any(
                isinstance(item, dict)
                and item.get("profile_id") == session_profile.get("profile_id")
                and item.get("revision") == session_profile.get("revision")
                and item.get("state_revision") == session_profile.get("state_revision")
                for item in profiles)):
            profiles.append(session_profile)
        if session_profile_only and session_profile is None:
            return {
                "error": False, "available": False, "status": "UNKNOWN",
                "reason": "NO_APPLICABLE_PROFILE", "commission_rate": None,
                "price_basis": "SELLER_PRICE_RUB", "seller_price_cents": cents,
                "effective_date": effective_date, "selected_profile": None,
                "candidate_profiles": [], "read_only": True, "executed": False,
            }

        # An explicit legacy commission edit is a user-confirmed point for
        # this exact price. It must never be extrapolated to adjacent prices.
        inputs = result.get("inputs") or {}
        provenance = result.get("provenance") or {}
        manual_rate = inputs.get("commission_rate")
        selected_profile_id = (
            session_profile.get("profile_id") if session_profile else None
        )
        selected_revision = session_profile.get("revision") if session_profile else None
        selected_state_revision = session_profile.get("state_revision") if session_profile else None
        if (provenance.get("commission_rate") in {
                "manual", "manual_seller_assumption", "manual_unit_economics_input"
        } and manual_rate is not None):
            now = datetime.now(timezone.utc).isoformat()
            manual_point = {
                "profile_id": "manual-scenario-" + str(scenario_id),
                "revision": 1,
                "state_revision": 1,
                "owner_id": context["owner_id"],
                "store_id": context["store_id"],
                "identity": context["identity"],
                "sale_schema": "FBO",
                "price_basis": "SELLER_PRICE_RUB",
                "currency": "RUB",
                "origin": "MANUAL_SELLER_ASSUMPTION",
                "source_ref": "MANUAL_SCENARIO_COMMISSION_OVERRIDE",
                "recorded_at": now,
                "confirmed_by_owner": True,
                "effective_from": date.today().isoformat(),
                "effective_to": date.today().isoformat(),
                "bands": [{
                    "price_from_cents": cents, "price_to_cents": cents,
                    "commission_rate": str(manual_rate),
                }],
            }
            profiles.append(manual_point)
            selected_profile_id = manual_point["profile_id"]
            selected_revision = manual_point["revision"]
            selected_state_revision = manual_point["state_revision"]

        resolution = self.tariff_resolver.resolve(
            seller_price_cents=cents,
            identity=identity,
            sale_schema=context.get("scheme"),
            effective_date=effective_date,
            profiles=profiles,
            selected_profile_id=selected_profile_id,
            selected_revision=selected_revision,
            selected_state_revision=selected_state_revision,
        )
        if resolution.get("error"):
            return {
                "error": False, "available": False, "status": "SOURCE_UNAVAILABLE",
                "reason": resolution.get("reason") or resolution.get("code") or "TARIFF_INVALID",
                "commission_rate": None, "price_basis": "SELLER_PRICE_RUB",
                "seller_price_cents": cents, "effective_date": effective_date,
                "selected_profile": None, "candidate_profiles": profiles,
            }
        selected = None
        if resolution.get("available") is True:
            profile_meta = resolution.get("profile") or {}
            selected = next((
                item for item in profiles
                if item.get("profile_id") == profile_meta.get("profile_id")
                and item.get("revision") == profile_meta.get("revision")
                and item.get("state_revision") == profile_meta.get("state_revision")
            ), None)
        return {
            **resolution,
            "effective_date": effective_date,
            "selected_profile": deepcopy(selected),
            "candidate_profiles": deepcopy(profiles),
            "read_only": True,
            "executed": False,
        }

    def resolve_for_product(self, identity, seller_price, source_snapshot,
                            source_age_seconds, source_ttl_seconds, user_id=None):
        """Resolve and freeze a product tariff for a non-single-plan consumer.

        Reuses the same tenant-scoped persisted profiles and current-price
        evidence as the single scenario, without requiring an active scenario
        or making another Ozon request.
        """
        scope_value = str(self.tenant_scope_provider() or "").strip()
        scope_owner, scope_store = split_store_tenant_scope(scope_value)
        owner = str(user_id or "").strip()
        if (not isinstance(identity, dict) or not owner or scope_owner != owner
                or not scope_store or not isinstance(source_snapshot, dict)):
            return {"error": True, "code": "UNIT_PRICE_TARIFF_IDENTITY_INVALID"}
        normalized_identity = {
            "owner_id": owner,
            "store_id": str(identity.get("store_id") or ""),
            "product_id": str(identity.get("product_id") or ""),
            "offer_id": str(identity.get("offer_id") or ""),
            "sku": str(identity.get("sku") or ""),
            "tenant_scope": str(identity.get("tenant_scope") or ""),
        }
        snapshot_identity = source_snapshot.get("identity") or {}
        if (normalized_identity["store_id"] != scope_store
                or normalized_identity["tenant_scope"] != scope_value
                or any(not normalized_identity[field] for field in (
                    "product_id", "offer_id", "sku",
                ))
                or any(str(snapshot_identity.get(field) or "") != normalized_identity[field]
                       for field in ("store_id", "tenant_scope", "product_id", "offer_id", "sku"))):
            return {"error": True, "code": "UNIT_PRICE_TARIFF_IDENTITY_INVALID"}
        cents = self._price_to_cents(seller_price)
        if cents is None:
            return {"error": True, "code": "UNIT_PRICE_TARIFF_PRICE_INVALID"}
        fresh = (
            type(source_age_seconds) in {int, float}
            and type(source_ttl_seconds) in {int, float}
            and source_age_seconds >= 0
            and 0 < source_ttl_seconds <= 600
            and source_age_seconds < source_ttl_seconds
        )
        current_point = self.tariff_source.from_scenario_snapshot(source_snapshot)
        profiles = list(current_point.get("profiles") or []) if fresh else []
        source_price_cents = current_point.get("current_price_cents") if fresh else None
        source_day = self._effective_date(
            (source_snapshot.get("source_periods") or {}).get("seller_price_as_of")
        ) if fresh and source_price_cents == cents else None
        effective_date = source_day or date.today().isoformat()
        identity_for_resolver = {
            key: normalized_identity[key]
            for key in ("owner_id", "store_id", "product_id", "offer_id", "sku")
        }

        listed = self.repository.list_tariff_profiles(
            identity={key: normalized_identity[key] for key in ("product_id", "offer_id", "sku")},
            owner_id=owner, store_id=scope_store,
            limit=self.repository.MAX_TARIFF_PAGE_SIZE,
        )
        storage_unavailable = listed.get("error") is True or listed.get("has_more") is True
        if not storage_unavailable:
            for item in listed.get("items") or []:
                record = self.repository.get_tariff_profile(
                    item.get("profile_id"), owner_id=owner, store_id=scope_store,
                )
                if record.get("error") or record.get("status") != "ACTIVE":
                    storage_unavailable = True
                    break
                profile = record.get("profile")
                if not isinstance(profile, dict):
                    storage_unavailable = True
                    break
                profiles.append(profile)
                if len(profiles) > UnitPriceTariffResolver.MAX_PROFILES:
                    storage_unavailable = True
                    break

        if storage_unavailable:
            resolution = {
                "error": False, "available": False, "status": "SOURCE_UNAVAILABLE",
                "reason": "PROFILE_SOURCE_UNAVAILABLE", "commission_rate": None,
                "price_basis": "SELLER_PRICE_RUB", "seller_price_cents": cents,
                "effective_date": effective_date, "selected_profile": None,
            }
        else:
            resolution = self.tariff_resolver.resolve(
                seller_price_cents=cents, identity=identity_for_resolver,
                sale_schema=(source_snapshot.get("product") or {}).get("scheme") or "FBO",
                effective_date=effective_date, profiles=profiles,
            )
        if resolution.get("error") is True:
            resolution = {
                "error": False, "available": False, "status": "SOURCE_UNAVAILABLE",
                "reason": resolution.get("reason") or resolution.get("code") or "TARIFF_INVALID",
                "commission_rate": None, "price_basis": "SELLER_PRICE_RUB",
                "seller_price_cents": cents, "effective_date": effective_date,
                "selected_profile": None,
            }
        selected_meta = resolution.get("profile") or {}
        selected_profile = next((
            profile for profile in profiles
            if isinstance(profile, dict)
            and profile.get("profile_id") == selected_meta.get("profile_id")
            and profile.get("revision") == selected_meta.get("revision")
            and profile.get("state_revision") == selected_meta.get("state_revision")
        ), None)
        frozen = UnitPriceTariffSnapshotAdapter.freeze(
            resolution, selected_profile, candidate_profiles=profiles,
            effective_date=effective_date,
        )
        if frozen is None:
            return {"error": True, "code": "UNIT_PRICE_TARIFF_SNAPSHOT_INVALID"}
        return {
            "error": False,
            "resolution": resolution,
            "frozen_tariff_resolution": frozen,
            "read_only": True,
            "executed": False,
        }

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
        cache_key = (ticket["user_id"], ticket["tenant_scope"], ticket["scenario_id"])
        with self._lock:
            self._session_profiles[cache_key] = {
                "identity": deepcopy(ticket["identity"]),
                "profile": deepcopy(result["profile"]),
                "created_at": self.clock(),
            }
            while len(self._session_profiles) > self.MAX_SESSION_PROFILES:
                self._session_profiles.pop(next(iter(self._session_profiles)))
        if action == "session":
            notice = "Тариф действует только в этой сессии и не сохранён между перезапусками."
        else:
            notice = f"Тариф сохранён: редакция {result['revision']}. Источник — ручное подтверждение продавца."
        return self._return_to_scenario(ticket, user_id, notice, refresh_tariff=True)

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

    @staticmethod
    def _price_to_cents(value):
        if isinstance(value, bool) or value is None:
            return None
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if (not amount.is_finite() or amount <= 0
                or amount * 100 != (amount * 100).to_integral_value()):
            return None
        cents = int(amount * 100)
        return cents if cents <= UnitPriceTariffResolver.MAX_PRICE_CENTS else None

    @staticmethod
    def _effective_date(value):
        if not isinstance(value, str) or len(value) > 40:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value if len(value) == 10 and UnitPriceTariffProfileRuntimeService._valid_date(value) else None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.date().isoformat()

    @staticmethod
    def _valid_date(value):
        try:
            return date.fromisoformat(value).isoformat() == value
        except (TypeError, ValueError):
            return False

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

    def _return_to_scenario(self, ticket, user_id, notice, *, refresh_tariff=False):
        refresher = getattr(self.calculator_runtime, "refresh_tariff_profile_snapshot", None)
        if refresh_tariff and callable(refresher):
            result = refresher(
                ticket["scenario_id"], ticket["scenario_version"], user_id=user_id,
            )
        else:
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
