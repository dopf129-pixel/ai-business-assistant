"""Bounded Telegram flow for explicit save and management of planning plans."""

from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from secrets import token_hex
from threading import RLock
from time import monotonic
from uuid import uuid4

from period_profit_plan_fact_comparison import PeriodProfitPlanFactComparisonService
from services.ozon_account_repository import split_store_tenant_scope
from services.planning_plan_readiness_service import PlanningPlanReadinessService
from services.planning_plan_comparison_service import PlanningPlanComparisonService
from services.scoped_transient_snapshot_store import ScopedTransientSnapshotStore
from services.tenant_context import get_current_tenant_user_id


class TelegramSavedPlanningPlanRuntimeService:
    PENDING_TTL_SECONDS = 600
    ACTION_TTL_SECONDS = 900
    MAX_PENDING = 64
    MAX_ACTIONS = 512
    PAGE_SIZE = 10
    COMPARISON_PAGE_SIZE = 8

    def __init__(self, planning_service, single_runtime, batch_runtime,
                 keyboard_service, clock=None, sales_mix_planning_service=None,
                 period_profit_sku_runtime=None, analytics_export_service=None,
                 comparison_snapshot_store=None, plan_fact_comparison_service=None,
                 readiness_service=None, plan_comparison_service=None):
        self.planning_service = planning_service
        self.single_runtime = single_runtime
        self.batch_runtime = batch_runtime
        self.keyboard_service = keyboard_service
        self.advertising_cap_service = getattr(single_runtime, "advertising_cap_service", None)
        self.sales_mix_planning_service = sales_mix_planning_service
        self.period_profit_sku_runtime = period_profit_sku_runtime
        self.analytics_export_service = analytics_export_service
        self.comparison_snapshot_store = comparison_snapshot_store or ScopedTransientSnapshotStore()
        self.plan_fact_comparison_service = plan_fact_comparison_service or (
            PeriodProfitPlanFactComparisonService(sales_mix_planning_service)
            if sales_mix_planning_service is not None
            else None
        )
        self.readiness_service = readiness_service or PlanningPlanReadinessService()
        self.plan_comparison_service = plan_comparison_service or (
            PlanningPlanComparisonService(sales_mix_planning_service)
            if sales_mix_planning_service is not None else None
        )
        self.clock = clock or monotonic
        self._pending = OrderedDict()
        self._actions = OrderedDict()
        self._plan_edit_contexts = OrderedDict()
        self._lock = RLock()
        self._plan_fact_inflight = set()

    def handle_callback(self, callback, user_id=None):
        scope = self._scope(user_id)
        if scope is None:
            return self._error("PLANNING_TENANT_SCOPE_MISMATCH")
        value = str(callback or "")
        if value != "upp:c" and not value.startswith("upp:a:"):
            with self._lock:
                self._pending.pop(scope["key"], None)
        if value == "upp:m" or value.startswith("upp:l:"):
            self._clear_plan_edit_contexts(scope)
            parts = value.split(":")
            include_archived = len(parts) > 2 and parts[2] == "a"
            offset = 0
            if len(parts) == 4:
                try:
                    offset = max(0, int(parts[3]))
                except ValueError:
                    return self._stale()
            return self._list_screen(scope, include_archived=include_archived, offset=offset)
        if value.startswith("upp:s:"):
            parts = value.split(":")
            if len(parts) != 4:
                return self._stale()
            capture = self.single_runtime.get_saved_plan_capture(parts[2], parts[3], user_id=user_id)
            return self._begin_title(scope, "save_single", capture)
        if value.startswith("upp:b:"):
            parts = value.split(":")
            if len(parts) != 4:
                return self._stale()
            capture = self.batch_runtime.get_saved_plan_capture(parts[2], parts[3], user_id=user_id)
            return self._begin_title(scope, "save_batch", capture)
        if value == "upp:c":
            self.clear_pending(user_id)
            return self._result("PLANNING_INPUT_CANCELLED", "Сохранение отменено. План не изменён.", self._main_keyboard())
        if value.startswith("upp:a:"):
            parts = value.split(":")
            if len(parts) != 3:
                return self._stale()
            action = self._consume_action(parts[2], scope)
            if action is None:
                return self._stale()
            if action.get("kind") != "save_update":
                self._clear_plan_edit_contexts(scope)
            if action.get("kind") not in {"sales_mix_skip", "sales_mix_confirm"}:
                with self._lock:
                    self._pending.pop(scope["key"], None)
            if action.get("kind") == "advertising_cap":
                return self._show_historical_advertising_cap(scope, action)
            return self._execute_action(action, scope, user_id)
        return self._stale()

    def handle_text(self, text, user_id=None):
        scope = self._scope(user_id)
        if scope is None:
            self.clear_pending(user_id)
            return self._error("PLANNING_TENANT_SCOPE_MISMATCH")
        with self._lock:
            pending = deepcopy(self._pending.get(scope["key"]))
        if pending is None:
            self._clear_other_scopes(scope)
            return None
        if self.clock() - pending.get("created_at", 0) > self.PENDING_TTL_SECONDS:
            self.clear_pending(user_id)
            return self._stale()
        if pending.get("kind") == "sales_mix":
            return self._handle_sales_mix_text(text, scope, pending)
        title = self._normalize_title(text)
        if title is None:
            return self._result(
                "PLANNING_TITLE_INVALID", "Название должно содержать от 1 до 80 символов. Попробуйте ещё раз.",
                self._cancel_keyboard(),
            )
        with self._lock:
            current = self._pending.get(scope["key"])
            if not isinstance(current, dict) or current.get("ticket") != pending.get("ticket"):
                return self._stale()
            self._pending.pop(scope["key"], None)
        if pending["kind"] in {"save_single", "save_batch"}:
            capture = self._recapture(pending, user_id)
            original = pending.get("capture") or {}
            expected_id = original.get("scenario_id") if pending["kind"] == "save_single" else original.get("batch_id")
            actual_id = capture.get("scenario_id") if isinstance(capture, dict) and pending["kind"] == "save_single" else (
                capture.get("batch_id") if isinstance(capture, dict) else None
            )
            if (
                not isinstance(capture, dict)
                or capture.get("error") is not False
                or not isinstance(capture.get("payload"), dict)
                or capture.get("tenant_scope") != scope["tenant_scope"]
                or actual_id != expected_id
                or capture.get("version") != original.get("version")
            ):
                return self._stale()
            result = self.planning_service.save_capture(
                title, capture, idempotency_key=pending["idempotency_key"],
            )
            if result.get("error") is True:
                return self._error(result.get("code"))
            return self._result(
                result.get("status", "PLANNING_DOCUMENT_SAVED"),
                result.get("message", "План сохранён локально."), self._saved_keyboard(),
                local_write=True, document_id=result.get("document_id"),
            )
        if pending["kind"] == "rename":
            result = self.planning_service.rename(
                pending["document_id"], title,
                expected_revision=pending["revision"],
                expected_state_revision=pending["state_revision"],
                idempotency_key=pending["idempotency_key"],
            )
        elif pending["kind"] == "copy":
            result = self.planning_service.copy_document(
                pending["document_id"], title=title,
                revision=pending.get("revision"),
                idempotency_key=pending["idempotency_key"],
            )
        else:
            return self._stale()
        if result.get("error") is True:
            return self._error(result.get("code"))
        return self._result(
            "PLANNING_DOCUMENT_UPDATED" if pending["kind"] == "rename" else "PLANNING_DOCUMENT_COPIED",
            "Сохранённый план обновлён локально." if pending["kind"] == "rename" else "Создана локальная копия плана.",
            self._saved_keyboard(), local_write=True, document_id=result.get("document_id"),
        )

    def clear_pending(self, user_id):
        self.clear_pending_for_navigation(user_id, preserve_editor_context=False)

    def clear_pending_for_navigation(self, user_id, *, preserve_editor_context):
        owner = str(user_id or "").strip()
        if not owner:
            return
        with self._lock:
            for key in [key for key in self._pending if key[0] == owner]:
                self._pending.pop(key, None)
            if not preserve_editor_context:
                for key in [key for key in self._plan_edit_contexts if key[0] == owner]:
                    self._plan_edit_contexts.pop(key, None)
            for token, action in list(self._actions.items()):
                if action.get("owner_id") == owner:
                    self._actions.pop(token, None)

    def should_preserve_batch_editor_for_callback(self, callback, user_id):
        value = str(callback or "")
        parts = value.split(":")
        if len(parts) != 3 or parts[:2] != ["upp", "a"]:
            return False
        scope = self._scope(user_id)
        if scope is None:
            return False
        with self._lock:
            action = deepcopy(self._actions.get(parts[2]))
        return bool(
            isinstance(action, dict)
            and action.get("kind") == "save_update"
            and action.get("plan_kind") == "batch"
            and action.get("owner_id") == scope["owner_id"]
            and action.get("tenant_scope") == scope["tenant_scope"]
        )

    def clear_user_state(self, user_id):
        self.clear_pending(user_id)
        owner = str(user_id or "").strip()
        with self._lock:
            for key in [key for key in self._plan_edit_contexts if key[0] == owner]:
                self._plan_edit_contexts.pop(key, None)
        self.comparison_snapshot_store.clear_owner(user_id, kind="plan_fact")
        self.comparison_snapshot_store.clear_owner(user_id, kind="plan_comparison")

    def decorate_plan_editor_result(self, result, user_id=None):
        """Attach revision-CAS save controls to the exact editor opened from readiness."""
        if not isinstance(result, dict) or result.get("error") is True:
            return result
        scope = self._scope(user_id)
        if scope is None:
            return result
        editor = result.get("plan_editor")
        if not isinstance(editor, dict):
            scenario_id = result.get("scenario_id") or self._scenario_id_from_result(result)
            scenario_version = result.get("scenario_version") or self._scenario_version_from_result(result)
            if scenario_id and scenario_version:
                editor = {"kind": "single", "id": scenario_id, "version": scenario_version}
            else:
                batch = result.get("batch_plan")
                if isinstance(batch, dict):
                    editor = {"kind": "batch", "id": batch.get("batch_id"), "version": batch.get("version")}
        if not isinstance(editor, dict):
            return result
        key = (scope["owner_id"], scope["tenant_scope"], editor.get("kind"), str(editor.get("id") or ""))
        with self._lock:
            context = deepcopy(self._plan_edit_contexts.get(key))
        if not isinstance(context, dict):
            return result
        if self.clock() - context.get("created_at", 0) > self.ACTION_TTL_SECONDS:
            with self._lock:
                self._plan_edit_contexts.pop(key, None)
            return result
        buttons = (result.get("keyboard") or {}).get("buttons") or []
        if not any(button.get("text") == "💾 Сохранить план" for button in buttons if isinstance(button, dict)):
            return result
        return self._add_update_controls(
            result, scope, plan_kind=editor["kind"],
            document_id=context["document_id"], revision=context["revision"],
            state_revision=context["state_revision"],
            scenario_id=editor.get("id") if editor["kind"] == "single" else None,
            version=editor.get("version"),
            batch_id=editor.get("id") if editor["kind"] == "batch" else None,
        )

    def _remember_plan_edit_context(self, scope, kind, editor_id, editor_version,
                                    document_id, revision, state_revision):
        if kind not in {"single", "batch"} or not editor_id or type(editor_version) is not int:
            return
        key = (scope["owner_id"], scope["tenant_scope"], kind, str(editor_id))
        with self._lock:
            self._plan_edit_contexts[key] = {
                "document_id": str(document_id), "revision": int(revision),
                "state_revision": int(state_revision),
                "editor_version": editor_version, "created_at": self.clock(),
            }
            self._plan_edit_contexts.move_to_end(key)
            while len(self._plan_edit_contexts) > 64:
                self._plan_edit_contexts.popitem(last=False)

    def _drop_plan_edit_context(self, scope, kind, editor_id):
        if kind not in {"single", "batch"} or not editor_id:
            return
        key = (scope["owner_id"], scope["tenant_scope"], kind, str(editor_id))
        with self._lock:
            self._plan_edit_contexts.pop(key, None)

    def _begin_title(self, scope, kind, capture):
        if not isinstance(capture, dict) or capture.get("error") is True:
            return self._stale()
        if capture.get("tenant_scope") != scope["tenant_scope"]:
            return self._stale()
        pending = {
            "ticket": token_hex(12), "kind": kind, "capture": deepcopy(capture),
            "idempotency_key": uuid4().hex, "created_at": self.clock(),
        }
        with self._lock:
            self._pending[scope["key"]] = pending
            self._pending.move_to_end(scope["key"])
            while len(self._pending) > self.MAX_PENDING:
                self._pending.popitem(last=False)
        return self._result(
            "PLANNING_TITLE_REQUIRED",
            "Введите название локального плана (1–80 символов). Пока вы вводите название, старая версия сценария должна оставаться активной.",
            self._cancel_keyboard(), local_write=False,
        )

    def _recapture(self, pending, user_id):
        capture = pending.get("capture") or {}
        if pending["kind"] == "save_single":
            return self.single_runtime.get_saved_plan_capture(
                capture.get("scenario_id"), capture.get("version"), user_id=user_id,
            )
        return self.batch_runtime.get_saved_plan_capture(
            capture.get("batch_id"), capture.get("version"), user_id=user_id,
        )

    def _list_screen(self, scope, *, include_archived=False, offset=0, notice=None):
        result = self.planning_service.list_documents(
            include_archived=include_archived, limit=self.PAGE_SIZE, offset=offset,
        )
        if result.get("error") is True:
            return self._error(result.get("code"))
        lines = ["📚 Мои планы", "Архивные планы" if include_archived else "Активные планы", ""]
        buttons = []
        for item in result.get("items", []):
            token = self._register_action(scope, "open", document_id=item["document_id"], revision=item["revision"])
            label = f"{item['title'][:42]} · v{item['revision']}"
            buttons.append({"text": label, "callback": f"upp:a:{token}"})
        if not result.get("items"):
            lines.append("Пока нет сохранённых планов.")
        if result.get("has_more"):
            next_offset = result.get("next_offset")
            buttons.append({"text": "Следующая страница", "callback": f"upp:l:{'a' if include_archived else 'n'}:{next_offset}"})
        buttons.append({"text": "Показать архив" if not include_archived else "Активные планы",
                        "callback": "upp:l:a:0" if not include_archived else "upp:l:n:0"})
        buttons.extend([{"text": "Главное меню", "callback": "main_menu"}])
        if notice:
            lines.extend(["", notice])
        return self._result("PLANNING_DOCUMENT_LIST", "\n".join(lines), self._keyboard(buttons))

    def _execute_action(self, action, scope, user_id):
        kind = action.get("kind")
        doc_id = action.get("document_id")
        revision = action.get("revision")
        if kind == "sales_mix":
            return self._begin_sales_mix(scope, action)
        if kind == "sales_mix_skip":
            return self._skip_sales_mix_quantity(scope, action)
        if kind == "sales_mix_confirm":
            return self._confirm_sales_mix(scope, action)
        if kind == "plan_fact_refresh":
            return self._refresh_plan_fact(scope, action, user_id)
        if kind == "readiness":
            return self._show_readiness(scope, action)
        if kind == "readiness_edit":
            return self._edit_readiness_field(scope, action, user_id)
        if kind == "sales_mix_quantity_edit":
            return self._begin_sales_mix_quantity_edit(scope, action)
        if kind == "compare_start":
            return self._comparison_picker(scope, action)
        if kind == "compare_page":
            return self._comparison_picker(scope, action, offset=action.get("offset", 0))
        if kind == "compare_pick":
            return self._compare_saved_documents(scope, action)
        if kind in {"plan_comparison_view", "plan_comparison_export"}:
            return self._read_plan_comparison_snapshot(scope, action, kind)
        if kind in {"export_saved_plan", "export_sales_mix", "export_advertising_cap"}:
            return self._export_saved_document(scope, action, kind)
        if kind in {"plan_fact_details", "plan_fact_view", "plan_fact_export"}:
            return self._read_plan_fact_snapshot(scope, action, kind)
        if kind == "open":
            result = self.planning_service.get_document(doc_id, revision=revision)
            return self._detail_screen(scope, result)
        if kind == "revisions":
            result = self.planning_service.list_revisions(doc_id)
            if result.get("error") is True:
                return self._error(result.get("code"))
            buttons = []
            for item in result.get("items", [])[:20]:
                token = self._register_action(scope, "open", document_id=doc_id, revision=item["revision"])
                buttons.append({"text": f"Версия {item['revision']} · {item['created_at'][:16]}", "callback": f"upp:a:{token}"})
            buttons.append({"text": "Назад к плану", "callback": self._action_callback(scope, "open", document_id=doc_id, revision=revision)})
            return self._result("PLANNING_REVISION_LIST", "История сохранённых версий. Просмотр не обращается к Ozon.", self._keyboard(buttons))
        if kind in {"rename_prompt", "copy_prompt"}:
            with self._lock:
                self._pending[scope["key"]] = {
                    "ticket": token_hex(12), "kind": "rename" if kind == "rename_prompt" else "copy",
                    "document_id": doc_id, "revision": revision,
                    "state_revision": action.get("state_revision"),
                    "idempotency_key": uuid4().hex, "created_at": self.clock(),
                }
            prompt = "Введите новое название плана (1–80 символов)." if kind == "rename_prompt" else "Введите название копии (1–80 символов)."
            return self._result("PLANNING_TITLE_REQUIRED", prompt, self._cancel_keyboard())
        if kind == "archive":
            result = self.planning_service.archive(
                doc_id, expected_revision=revision,
                expected_state_revision=action.get("state_revision"),
                idempotency_key=uuid4().hex,
            )
            if result.get("error") is True:
                return self._error(result.get("code"))
            return self._list_screen(scope, notice="План перемещён в архив. Его версии сохранены.")
        if kind == "restore":
            result = self.planning_service.restore(
                doc_id, expected_revision=revision,
                expected_state_revision=action.get("state_revision"),
                idempotency_key=uuid4().hex,
            )
            if result.get("error") is True:
                return self._error(result.get("code"))
            return self._list_screen(scope, notice="План восстановлен из архива.")
        if kind == "delete_prompt":
            token = self._register_action(
                scope, "delete_confirm", document_id=doc_id, revision=revision,
                state_revision=action.get("state_revision"), title=action.get("title"),
            )
            return self._result("PLANNING_DELETE_CONFIRMATION_REQUIRED",
                                f"Физически удалить план «{action.get('title') or 'Сохранённый план'}» · состояние {action.get('state_revision')} и его версии? Это действие необратимо.",
                                self._keyboard([{"text": "Удалить план и версии", "callback": f"upp:a:{token}"},
                                                {"text": "Отмена", "callback": self._action_callback(scope, "open", document_id=doc_id, revision=revision)}]))
        if kind == "delete_confirm":
            result = self.planning_service.delete(
                doc_id, expected_revision=revision,
                expected_state_revision=action.get("state_revision"),
                confirmed=True, idempotency_key=uuid4().hex,
            )
            if result.get("error") is True:
                return self._error(result.get("code"))
            return self._list_screen(scope, notice="Документ и его версии удалены по подтверждению.")
        if kind == "continue":
            result = self.planning_service.get_document(doc_id, revision=revision)
            if result.get("error") is True:
                return self._error(result.get("code"))
            document = result["document"]
            payload = document["payload"]
            if payload.get("plan_kind") == "single":
                return self.single_runtime.restore_saved_plan(payload, user_id=user_id)
            return self.batch_runtime.restore_saved_plan(payload, user_id=user_id)
        if kind == "refresh":
            result = self.planning_service.get_document(doc_id, revision=revision)
            if result.get("error") is True:
                return self._error(result.get("code"))
            document = result["document"]
            payload = document["payload"]
            if payload.get("plan_kind") == "single":
                opened = self.single_runtime.restore_saved_plan(payload, user_id=user_id)
                sid = opened.get("scenario_id")
                version = opened.get("scenario_version")
                if sid and version:
                    refreshed = self.single_runtime.handle_callback(f"upc:r:{sid}:{version}", user_id=user_id)
                    refreshed_id = (
                        refreshed.get("scenario_id") or self._scenario_id_from_result(refreshed)
                    )
                    refreshed_version = (
                        refreshed.get("scenario_version") or self._scenario_version_from_result(refreshed)
                    )
                    result = self._add_update_controls(
                        refreshed, scope, plan_kind="single", document_id=doc_id,
                        revision=revision, state_revision=document["state_revision"],
                        scenario_id=refreshed_id, version=refreshed_version,
                    )
                    if result.get("error") is not True and any(
                        button.get("text") == "💾 Сохранить изменения в этот план"
                        for button in ((result.get("keyboard") or {}).get("buttons") or [])
                        if isinstance(button, dict)
                    ):
                        self._remember_plan_edit_context(
                            scope, "single", refreshed_id, refreshed_version,
                            doc_id, revision, document["state_revision"],
                        )
                    return result
                return opened
            opened = self.batch_runtime.restore_saved_plan(payload, user_id=user_id)
            refresh_callback = self._find_button_callback(opened.get("keyboard"), "Обновить источники")
            if refresh_callback:
                refreshed = self.batch_runtime.handle_callback(refresh_callback, user_id=user_id)
                batch = refreshed.get("batch_plan") if isinstance(refreshed, dict) else None
                editor = refreshed.get("plan_editor") if isinstance(refreshed, dict) else None
                refreshed_id = (
                    editor.get("id") if isinstance(editor, dict)
                    else batch.get("batch_id") if isinstance(batch, dict) else None
                )
                refreshed_version = (
                    editor.get("version") if isinstance(editor, dict)
                    else batch.get("version") if isinstance(batch, dict) else None
                )
                result = self._add_update_controls(
                    refreshed, scope, plan_kind="batch", document_id=doc_id,
                    revision=revision, state_revision=document["state_revision"],
                    batch_id=refreshed_id, version=refreshed_version,
                )
                if result.get("error") is not True and any(
                    button.get("text") == "💾 Сохранить изменения в этот план"
                    for button in ((result.get("keyboard") or {}).get("buttons") or [])
                    if isinstance(button, dict)
                ):
                    self._remember_plan_edit_context(
                        scope, "batch", refreshed_id, refreshed_version,
                        doc_id, revision, document["state_revision"],
                    )
                return result
            return opened
        if kind == "save_update":
            plan_kind = action.get("plan_kind")
            if plan_kind == "single":
                capture = self.single_runtime.get_saved_plan_capture(
                    action.get("scenario_id"), action.get("version"), user_id=user_id,
                )
            elif plan_kind == "batch":
                capture = self.batch_runtime.get_saved_plan_capture(
                    action.get("batch_id"), action.get("version"), user_id=user_id,
                )
            else:
                return self._stale()
            if (
                not isinstance(capture, dict) or capture.get("error") is not False
                or capture.get("tenant_scope") != scope["tenant_scope"]
            ):
                return self._stale()
            current = self.planning_service.get_document(doc_id)
            document = current.get("document") if isinstance(current, dict) else None
            if (
                not isinstance(document, dict)
                or document.get("current_revision") != revision
                or document.get("state_revision") != action.get("state_revision")
                or document.get("status") != "ACTIVE"
            ):
                return self._error("PLANNING_DOCUMENT_STATE_CONFLICT")
            merged_capture = self._preserve_saved_plan_context(document, capture)
            if merged_capture.get("error") is True:
                return self._error(merged_capture.get("code"))
            saved = self.planning_service.save_capture(
                document.get("title"), merged_capture,
                document_id=doc_id, expected_revision=revision,
                expected_state_revision=action.get("state_revision"),
                idempotency_key=uuid4().hex,
            )
            if saved.get("error") is True:
                return self._error(saved.get("code"))
            editor_id = action.get("scenario_id") if plan_kind == "single" else action.get("batch_id")
            self._drop_plan_edit_context(scope, plan_kind, editor_id)
            return self._result(
                "PLANNING_DOCUMENT_UPDATED",
                f"Сохранена новая версия плана {saved.get('revision')}. Предыдущие версии сохранены.",
                self._saved_keyboard(), local_write=True, document_id=doc_id,
                revision=saved.get("revision"),
            )
        return self._stale()

    def _show_readiness(self, scope, action):
        result = self.planning_service.get_document(
            action.get("document_id"), revision=action.get("revision"),
        )
        if result.get("error") is True:
            return self._error(result.get("code"))
        document = result.get("document") or {}
        readiness = self.readiness_service.project(
            result, active_owner=scope["owner_id"], active_store=scope["store_id"],
        )
        if readiness.get("error") is True:
            return self._error(readiness.get("code"))
        counts = readiness["counts"]
        lines = [
            "Готовность плана · версия " + str(readiness["revision"]),
            f"Расчёт по допущениям: готово {counts['calculations_ready']}/{counts['items']} SKU.",
            "Допущения: исторические; просмотр не обновляет источники.",
            "Сверка с фактом: не проверялась.",
        ]
        if readiness["sales_mix_status"] == "NOT_STARTED":
            lines.append("Объём продаж за период ещё не задан.")
        else:
            lines.append(
                f"Количество успешных продаж: подтверждено {counts['quantities_confirmed']}/{counts['items']} SKU."
            )
        buttons = []
        can_edit = (
            document.get("status") == "ACTIVE"
            and document.get("revision") == document.get("current_revision")
        )
        for item in readiness.get("items", []):
            lines.append(
                f"• {item['label']}: расчёт {item['calculation_status']}; "
                f"identity {item['identity_status']}; количество {item['quantity_status']}."
            )
            field = item.get("editable_field")
            if can_edit and field:
                buttons.append({
                    "text": "Исправить · " + item["label"][:32],
                    "callback": self._action_callback(
                        scope, "readiness_edit", document_id=document["document_id"],
                        revision=document["revision"], state_revision=document["state_revision"],
                        row_id=item["row_id"], field=field,
                    ),
                })
            if (can_edit and readiness["sales_mix_status"] != "NOT_STARTED"
                    and item["quantity_status"] == "UNKNOWN"):
                buttons.append({
                    "text": "Задать количество · " + item["label"][:28],
                    "callback": self._action_callback(
                        scope, "sales_mix_quantity_edit", document_id=document["document_id"],
                        revision=document["revision"], state_revision=document["state_revision"],
                        row_id=item["row_id"],
                    ),
                })
        if can_edit and readiness["sales_mix_status"] == "NOT_STARTED":
            buttons.insert(0, {
                "text": "Задать объём продаж",
                "callback": self._action_callback(
                    scope, "sales_mix", document_id=document["document_id"],
                    revision=document["revision"], state_revision=document["state_revision"],
                ),
            })
        if not can_edit:
            lines.append("Это архивная или старая ревизия. Сначала откройте актуальную версию или создайте копию.")
        buttons.extend([
            {"text": "К карточке плана", "callback": self._action_callback(
                scope, "open", document_id=document["document_id"], revision=document["revision"],
            )},
            {"text": "Мои планы", "callback": "upp:m"},
            {"text": "Главное меню", "callback": "main_menu"},
        ])
        return self._result(
            "PLANNING_READINESS_READY", "\n".join(lines)[:3500], self._keyboard(buttons),
            readiness=readiness,
        )

    def _edit_readiness_field(self, scope, action, user_id):
        result = self.planning_service.get_document(
            action.get("document_id"), revision=action.get("revision"),
        )
        if result.get("error") is True:
            return self._error(result.get("code"))
        document = result.get("document") or {}
        if (
            document.get("owner_id") != scope["owner_id"]
            or document.get("store_id") != scope["store_id"]
            or document.get("revision") != document.get("current_revision")
            or document.get("state_revision") != action.get("state_revision")
            or document.get("status") != "ACTIVE"
        ):
            return self._error("PLANNING_DOCUMENT_REVISION_CONFLICT")
        payload = document.get("payload") or {}
        items = payload.get("items") or []
        matches = [
            item for item in items if isinstance(item, dict)
            and str(item.get("row_id") or (item.get("identity") or {}).get("sku") or "")
            == str(action.get("row_id") or "")
        ]
        if len(matches) != 1:
            return self._stale()
        field = action.get("field")
        if payload.get("plan_kind") == "single":
            result = self.single_runtime.edit_saved_plan_field(payload, field, user_id=user_id)
        elif payload.get("plan_kind") == "batch":
            result = self.batch_runtime.edit_saved_plan_field(
                payload, action.get("row_id"), field, user_id=user_id,
            )
        else:
            return self._error("PLANNING_READINESS_EDIT_UNAVAILABLE")
        editor = result.get("plan_editor") if isinstance(result, dict) else None
        if isinstance(editor, dict):
            self._remember_plan_edit_context(
                scope, editor.get("kind"), editor.get("id"), editor.get("version"),
                document["document_id"], document["revision"], document["state_revision"],
            )
        return result

    def _begin_sales_mix_quantity_edit(self, scope, action):
        if self.sales_mix_planning_service is None:
            return self._error("SALES_MIX_PLANNING_UNAVAILABLE")
        result = self.planning_service.get_document(
            action.get("document_id"), revision=action.get("revision"),
        )
        if result.get("error") is True:
            return self._error(result.get("code"))
        document = result.get("document") or {}
        if (
            document.get("owner_id") != scope["owner_id"]
            or document.get("store_id") != scope["store_id"]
            or document.get("status") != "ACTIVE"
            or document.get("revision") != document.get("current_revision")
            or document.get("state_revision") != action.get("state_revision")
        ):
            return self._error("PLANNING_DOCUMENT_REVISION_CONFLICT")
        payload = document.get("payload") or {}
        items = payload.get("items")
        mix = payload.get("sales_mix")
        if not isinstance(items, list) or not isinstance(mix, dict):
            return self._error("SALES_MIX_REQUIRED")
        row_id = str(action.get("row_id") or "")
        matches = [item for item in items if isinstance(item, dict)
                   and str(item.get("row_id") or (item.get("identity") or {}).get("sku") or "") == row_id]
        quantities = mix.get("quantities")
        period_label = mix.get("period_label")
        if (len(matches) != 1 or not isinstance(quantities, dict)
                or set(quantities) != {
                    str(item.get("row_id") or (item.get("identity") or {}).get("sku") or "")
                    for item in items
                }
                or not self.sales_mix_planning_service._valid_period(period_label)):
            return self._error("SALES_MIX_SCOPE_UNSUPPORTED")
        pending = {
            "ticket": token_hex(12), "kind": "sales_mix", "stage": "quantity_edit",
            "document_id": document["document_id"], "revision": document["revision"],
            "state_revision": document["state_revision"],
            "payload": deepcopy(payload), "created_at": self.clock(),
            "period_label": period_label, "quantities": deepcopy(quantities),
            "row_id": row_id, "expenses": deepcopy(mix.get("expenses") or []),
            "expenses_confirmed": mix.get("confirmed") is True,
        }
        with self._lock:
            self._pending[scope["key"]] = pending
        item = matches[0]
        identity = item.get("identity") or {}
        prompt = self._result(
            "SALES_MIX_QUANTITY_EDIT_REQUIRED",
            f"Введите новое число успешных продаж для {identity.get('product_name') or identity.get('offer_id') or row_id}. Ноль означает подтверждённые 0 продаж. Изменения попадут в новую ревизию только после проверки и подтверждения.",
            self._cancel_keyboard(),
            document_id=document["document_id"], revision=document["revision"],
        )
        return prompt

    def _detail_screen(self, scope, result):
        if result.get("error") is True:
            return self._error(result.get("code"))
        document = result.get("document") or {}
        payload = document.get("payload") or {}
        lines = [
            f"📄 {document.get('title', 'Сохранённый план')}",
            f"Версия {document.get('revision')} · {'архив' if document.get('status') == 'ARCHIVED' else 'активен'}",
            "Допущения сохранены на " + str(document.get("revision_created_at") or document.get("updated_at") or "неизвестную дату"),
            "Источник: исторический снимок; просмотр не обновляет Ozon.",
            "",
        ]
        for index, item in enumerate(payload.get("items") or [], start=1):
            identity = item.get("identity") or {}
            projection = item.get("projection") or {}
            name = str(identity.get("product_name") or "Товар").replace("\r", " ").replace("\n", " ")[:55]
            lines.append(f"{index}. {name} · SKU {identity.get('sku', '—')}")
            if projection.get("available") is True:
                lines.append(f"   Выручка {projection.get('revenue')} ₽; прибыль {projection.get('profit')} ₽; маржа {projection.get('margin_percent')}% по сохранённым допущениям.")
            elif projection.get("missing_inputs"):
                lines.append("   Черновик; не заполнено: " + ", ".join(projection["missing_inputs"][:8]))
            else:
                lines.append("   Расчёт сохранён как историческая проекция.")
        lines.extend(["", "Сохранённый расчёт не переоценивается автоматически и не считается фактом магазина."])
        saved_mix = payload.get("sales_mix")
        if saved_mix is not None:
            current_calc_version = getattr(
                getattr(self.sales_mix_planning_service, "scenario_service", None),
                "VERSION", None,
            )
            if (self.sales_mix_planning_service is None
                    or payload.get("calculation_version") != current_calc_version):
                lines.extend(["", "План объёма продаж сохранён, но его текущая проекция недоступна."])
            else:
                projection = self.sales_mix_planning_service.calculate(
                    payload.get("items"), quantities=saved_mix.get("quantities"),
                    period_label=saved_mix.get("period_label"), expenses=saved_mix.get("expenses"),
                    expenses_confirmed=saved_mix.get("confirmed") is True,
                )
                lines.extend(["", "Экономика заданного объёма · сохранённые ручные допущения"])
                if projection.get("error") is True:
                    lines.append("Проекция недоступна: " + str(projection.get("code")) + ".")
                else:
                    lines.append(f"Период {projection.get('period')}; задано успешных продаж: {projection.get('total_quantity')} шт.")
                    if projection.get("coverage_complete") is True:
                        lines.append(f"Выручка {projection['components']['revenue']} ₽; прибыль {projection.get('profit') or 'не рассчитана'} ₽; маржа {projection.get('margin_percent') or 'не определена'}%.")
                    else:
                        lines.append("Показан подтверждённый subtotal; итоговая прибыль и маржа набора недоступны.")
                    if projection.get("tax_status") == "MIXED_TAX_POLICIES":
                        lines.append("У строк различаются налоговые режимы; общий налог не рассчитан.")
                    lines.append("Это сохранённый план, не фактический результат магазина.")
        buttons = [
            {"text": "Готовность плана", "callback": self._action_callback(
                scope, "readiness", document_id=document["document_id"],
                revision=document["revision"],
            )},
            {"text": "Продолжить по сохранённым допущениям", "callback": self._action_callback(scope, "continue", document_id=document["document_id"], revision=document["revision"])},
            {"text": "Обновить источники", "callback": self._action_callback(scope, "refresh", document_id=document["document_id"], revision=document["revision"])},
            {"text": "Сохранить копию", "callback": self._action_callback(scope, "copy_prompt", document_id=document["document_id"], revision=document["revision"])},
            {"text": "Переименовать", "callback": self._action_callback(
                scope, "rename_prompt", document_id=document["document_id"],
                revision=document["current_revision"], state_revision=document["state_revision"],
            )},
            {"text": "История версий", "callback": self._action_callback(scope, "revisions", document_id=document["document_id"], revision=document["revision"])},
        ]
        if self.plan_comparison_service is not None:
            buttons.insert(0, {
                "text": "Сравнить варианты",
                "callback": self._action_callback(
                    scope, "compare_start", document_id=document["document_id"],
                    revision=document["revision"],
                ),
            })
        if self.analytics_export_service is not None:
            buttons.extend([
                {"text": "Экспорт плана · CSV", "callback": self._action_callback(
                    scope, "export_saved_plan", document_id=document["document_id"],
                    revision=document["revision"], file_format="csv",
                )},
                {"text": "Экспорт плана · JSON", "callback": self._action_callback(
                    scope, "export_saved_plan", document_id=document["document_id"],
                    revision=document["revision"], file_format="json",
                )},
            ])
            if isinstance(saved_mix, dict):
                for file_format in ("csv", "json"):
                    buttons.append({
                        "text": "Экспорт объёма · " + file_format.upper(),
                        "callback": self._action_callback(
                            scope, "export_sales_mix", document_id=document["document_id"],
                            revision=document["revision"], file_format=file_format,
                        ),
                    })
        if self.advertising_cap_service is not None:
            buttons.insert(1, {
                "text": "Рекламный предел (сохранённые допущения)",
                "callback": self._action_callback(
                    scope, "advertising_cap", document_id=document["document_id"],
                    revision=document["revision"],
                ),
            })
        if self.sales_mix_planning_service is not None:
            buttons.insert(2, {
                "text": "План объёма продаж",
                "callback": self._action_callback(
                    scope, "sales_mix", document_id=document["document_id"],
                    revision=document["revision"], state_revision=document["state_revision"],
                ),
            })
        if (
            self.plan_fact_comparison_service is not None
            and self.period_profit_sku_runtime is not None
            and isinstance(saved_mix, dict)
        ):
            buttons.insert(3, {
                "text": "Сравнить план с фактом",
                "callback": self._action_callback(
                    scope, "plan_fact_refresh", document_id=document["document_id"],
                    revision=document["revision"], current_revision=document["current_revision"],
                ),
            })
        if document.get("status") == "ARCHIVED":
            buttons.append({"text": "Восстановить", "callback": self._action_callback(
                scope, "restore", document_id=document["document_id"],
                revision=document["current_revision"], state_revision=document["state_revision"],
            )})
        else:
            buttons.append({"text": "В архив", "callback": self._action_callback(
                scope, "archive", document_id=document["document_id"],
                revision=document["current_revision"], state_revision=document["state_revision"],
            )})
        buttons.append({"text": "Удалить…", "callback": self._action_callback(
            scope, "delete_prompt", document_id=document["document_id"],
            revision=document["current_revision"], state_revision=document["state_revision"],
            title=document.get("title"),
        )})
        buttons.extend([
            {"text": "К списку", "callback": "upp:m"},
            {"text": "Главное меню", "callback": "main_menu"},
        ])
        return self._result("PLANNING_DOCUMENT_DETAILS", "\n".join(lines), self._keyboard(buttons), document_id=document.get("document_id"))

    def _begin_sales_mix(self, scope, action):
        if self.sales_mix_planning_service is None:
            return self._stale()
        result = self.planning_service.get_document(
            action.get("document_id"), revision=action.get("revision"),
        )
        if result.get("error") is True:
            return self._error(result.get("code"))
        document = result.get("document") or {}
        if (document.get("status") != "ACTIVE"
                or document.get("revision") != document.get("current_revision")
                or document.get("state_revision") != action.get("state_revision")):
            return self._error("PLANNING_DOCUMENT_REVISION_CONFLICT")
        payload = document.get("payload") or {}
        items = payload.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 10:
            return self._error("SALES_MIX_SCOPE_UNSUPPORTED")
        row_keys = [str(item.get("row_id") or (item.get("identity") or {}).get("sku") or "") for item in items]
        if any(not key for key in row_keys) or len(row_keys) != len(set(row_keys)):
            return self._error("SALES_MIX_IDENTITY_AMBIGUOUS")
        pending = {
            "ticket": token_hex(12), "kind": "sales_mix", "stage": "period",
            "document_id": document["document_id"], "revision": document["revision"],
            "state_revision": document["state_revision"],
            "payload": deepcopy(payload), "created_at": self.clock(),
            "period_label": None, "quantities": {key: None for key in row_keys},
            "row_index": 0, "expenses": [], "expense_count": None,
            "expense_index": 0,
        }
        with self._lock:
            self._pending[scope["key"]] = pending
        return self._sales_mix_prompt(scope, pending, "Укажите период расчёта, например 01.08.2026 - 31.08.2026.")

    def _sales_mix_prompt(self, scope, pending, message):
        buttons = [{"text": "Отмена", "callback": "upp:c"}, {"text": "Главное меню", "callback": "main_menu"}]
        if pending.get("stage") == "quantity":
            items = pending["payload"].get("items") or []
            index = pending.get("row_index", 0)
            if 0 <= index < len(items):
                key = str(items[index].get("row_id") or (items[index].get("identity") or {}).get("sku") or "")
                token = self._register_action(
                    scope, "sales_mix_skip", document_id=pending["document_id"],
                    revision=pending["revision"], ticket=pending["ticket"], row_index=index,
                )
                buttons.insert(0, {"text": "Оставить количество неизвестным", "callback": f"upp:a:{token}"})
                identity = items[index].get("identity") or {}
                name = str(identity.get("product_name") or identity.get("offer_id") or key)[:45]
                message = f"{message}\n\n{index + 1}/{len(items)} · {name} · SKU {identity.get('sku', key)}"
        return self._result(
            "SALES_MIX_INPUT_REQUIRED", message, self._keyboard(buttons),
            read_only=True, executed=False,
        )

    def _handle_sales_mix_text(self, text, scope, pending):
        value = str(text or "").strip()
        updated = deepcopy(pending)
        stage = pending.get("stage")
        if stage == "period":
            if not self.sales_mix_planning_service._valid_period(value):
                return self._sales_mix_prompt(scope, pending, "Период не принят. Укажите даты в формате ДД.ММ.ГГГГ - ДД.ММ.ГГГГ; диапазон — не более 366 дней.")
            updated["period_label"] = value
            updated["stage"] = "quantity"
            updated["row_index"] = 0
            return self._save_sales_mix_pending_and_prompt(scope, pending, updated, "Введите целое число подтверждённых успешных продаж. Ноль указывайте явно.")
        if stage == "quantity":
            if not value.isascii() or not value.isdigit() or len(value) > 6:
                return self._sales_mix_prompt(scope, pending, "Количество не принято. Введите целое число от 0 до 100 000 на SKU или оставьте его неизвестным кнопкой.")
            quantity = int(value)
            if quantity > self.sales_mix_planning_service.MAX_QUANTITY_PER_ITEM:
                return self._sales_mix_prompt(scope, pending, "Количество превышает лимит 100 000 на SKU.")
            items = pending["payload"].get("items") or []
            index = pending.get("row_index", 0)
            if not 0 <= index < len(items):
                return self._stale()
            identity = items[index].get("identity") or {}
            key = str(items[index].get("row_id") or identity.get("sku") or "")
            known_total = sum(
                item_quantity for item_key, item_quantity in updated["quantities"].items()
                if item_key != key and type(item_quantity) is int
            ) + quantity
            if known_total > self.sales_mix_planning_service.MAX_TOTAL_QUANTITY:
                return self._sales_mix_prompt(scope, pending, "Общее подтверждённое количество превышает 1 000 000 единиц.")
            updated["quantities"][key] = quantity
            updated["row_index"] = index + 1
            if updated["row_index"] >= len(items):
                updated["stage"] = "expense_count"
                return self._save_sales_mix_pending_and_prompt(scope, pending, updated, "Введите число дополнительных расходов за период. Введите 0, если явно подтверждаете пустой список.")
            return self._save_sales_mix_pending_and_prompt(scope, pending, updated, "Введите целое количество успешных продаж или оставьте его неизвестным кнопкой.")
        if stage == "quantity_edit":
            if not value.isascii() or not value.isdigit() or len(value) > 6:
                return self._sales_mix_prompt(scope, pending, "Количество не принято. Введите целое число от 0 до 100 000 на SKU.")
            quantity = int(value)
            if quantity > self.sales_mix_planning_service.MAX_QUANTITY_PER_ITEM:
                return self._sales_mix_prompt(scope, pending, "Количество превышает лимит 100 000 на SKU.")
            row_id = pending.get("row_id")
            if row_id not in updated.get("quantities", {}):
                return self._stale()
            known_total = sum(
                item_quantity for item_key, item_quantity in updated["quantities"].items()
                if item_key != row_id and type(item_quantity) is int
            ) + quantity
            if known_total > self.sales_mix_planning_service.MAX_TOTAL_QUANTITY:
                return self._sales_mix_prompt(scope, pending, "Общее подтверждённое количество превышает 1 000 000 единиц.")
            updated["quantities"][row_id] = quantity
            updated["stage"] = "preview"
            updated["expenses_confirmed"] = pending.get("expenses_confirmed") is True
            return self._save_sales_mix_preview(scope, pending, updated)
        if stage == "expense_count":
            if not value.isascii() or not value.isdigit() or len(value) > 2 or int(value) > self.sales_mix_planning_service.MAX_FIXED_EXPENSES:
                return self._sales_mix_prompt(scope, pending, "Введите целое число дополнительных расходов от 0 до 20.")
            count = int(value)
            updated["expense_count"] = count
            if count == 0:
                updated["stage"] = "preview"
                updated["expenses_confirmed"] = True
                return self._save_sales_mix_preview(scope, pending, updated)
            updated["stage"] = "expense_entry"
            updated["expense_index"] = 0
            return self._save_sales_mix_pending_and_prompt(scope, pending, updated, f"Расход 1/{count}: введите название и сумму через точку с запятой, например Упаковка; 250.00")
        if stage == "expense_entry":
            parts = value.split(";", 1)
            if len(parts) != 2 or not parts[0].strip() or len(parts[0].strip()) > 80:
                return self._sales_mix_prompt(scope, pending, "Не понял расход. Введите название; сумма, например Реклама; 1250.00")
            amount = self.sales_mix_planning_service._decimal(parts[1].strip().replace(",", "."))
            if amount is None or amount < 0 or amount > self.sales_mix_planning_service.MAX_AMOUNT:
                return self._sales_mix_prompt(scope, pending, "Сумма расхода не принята. Укажите неотрицательную сумму до 1 000 000 000 ₽.")
            current_expense_total = sum(
                self.sales_mix_planning_service._decimal(item.get("amount")) or Decimal("0")
                for item in updated.get("expenses") or [] if isinstance(item, dict)
            )
            if current_expense_total + amount > self.sales_mix_planning_service.MAX_FIXED_EXPENSE_TOTAL:
                return self._sales_mix_prompt(scope, pending, "Сумма дополнительных расходов за период не должна превышать 1 000 000 000 ₽.")
            updated["expenses"].append({"name": parts[0].strip(), "amount": format(amount.quantize(Decimal('0.01')), '.2f')})
            updated["expense_index"] += 1
            if updated["expense_index"] >= updated["expense_count"]:
                updated["stage"] = "preview"
                updated["expenses_confirmed"] = True
                return self._save_sales_mix_preview(scope, pending, updated)
            return self._save_sales_mix_pending_and_prompt(scope, pending, updated, f"Расход {updated['expense_index'] + 1}/{updated['expense_count']}: название; сумма")
        return self._stale()

    def _save_sales_mix_pending_and_prompt(self, scope, previous, updated, message):
        with self._lock:
            current = self._pending.get(scope["key"])
            if not isinstance(current, dict) or current.get("ticket") != previous.get("ticket") or current.get("stage") != previous.get("stage"):
                return self._stale()
            self._pending[scope["key"]] = updated
        return self._sales_mix_prompt(scope, updated, message)

    def _save_sales_mix_preview(self, scope, previous, updated):
        payload = updated.get("payload") or {}
        result = self.sales_mix_planning_service.calculate(
            payload.get("items"), quantities=updated.get("quantities"),
            period_label=updated.get("period_label"), expenses=updated.get("expenses"),
            expenses_confirmed=updated.get("expenses_confirmed") is True,
        )
        if result.get("error") is True:
            return self._sales_mix_prompt(scope, previous, "Не удалось проверить план: " + str(result.get("code")) + ". Данные не сохранены.")
        updated["preview"] = deepcopy(result)
        with self._lock:
            current = self._pending.get(scope["key"])
            if not isinstance(current, dict) or current.get("ticket") != previous.get("ticket") or current.get("stage") != previous.get("stage"):
                return self._stale()
            self._pending[scope["key"]] = updated
        token = self._register_action(
            scope, "sales_mix_confirm", document_id=updated["document_id"],
            revision=updated["revision"], ticket=updated["ticket"],
        )
        lines = [
            "План экономики заданного объёма продаж",
            f"Период: {result.get('period')}",
            f"Успешные продажи: {result.get('total_quantity')} шт.; состав: {result.get('included_rows')}/{result.get('selected_rows')} строк.",
            "Строка: Q × цена → выручка · себестоимость · комиссия · реклама · fees · вклад до налога (₽).",
        ]
        for row in result.get("rows", []):
            components = row.get("components") or {}
            lines.append(
                f"• {row.get('label')}: {row.get('quantity')} × "
                f"{row.get('price_per_unit')} → выручка {components.get('revenue')} ₽; "
                f"себест. {components.get('cost_of_goods')} ₽; "
                f"комиссия {components.get('commission')} ₽; "
                f"реклама {components.get('advertising')} ₽; "
                f"fees {components.get('fees')} ₽; "
                f"вклад {row.get('profit_before_tax_contribution')} ₽."
            )
        components = result.get("components") or {}
        lines.extend([
            f"Выручка: {components.get('revenue')} ₽; баллы: {components.get('discount_points')} ₽.",
            f"Прибыль до дополнительных расходов и налога: {components.get('profit_before_tax')} ₽.",
            f"Дополнительные расходы за период: {result.get('fixed_expense_total')} ₽; подтверждение: {'да' if updated.get('expenses_confirmed') else 'нет'}.",
            f"Прибыль до налога после расходов: {result.get('profit_before_tax_after_fixed_expenses')} ₽.",
        ])
        for expense in result.get("fixed_expenses", []):
            lines.append(f"Расход за период · {expense.get('name')}: {expense.get('amount')} ₽.")
        if result.get("coverage_complete") is True:
            lines.append(f"Налог: {result.get('tax') if result.get('tax') is not None else 'не рассчитан (' + str(result.get('tax_status')) + ')'} ₽; итоговая прибыль: {result.get('profit') if result.get('profit') is not None else 'не определена'} ₽; маржа: {result.get('margin_percent') if result.get('margin_percent') is not None else 'не определена'}%.")
        else:
            lines.append("Частичный подтверждённый subtotal; налог, итоговая прибыль и маржа всего выбранного набора недоступны.")
            for excluded in result.get("excluded_rows", [])[:10]:
                lines.append(f"Исключено · {excluded.get('label')}: {excluded.get('reason')}.")
        if result.get("coverage_complete") is True:
            self._append_sales_mix_advertising_cap(lines, payload, result)
        buttons = [
            {"text": "Подтвердить и сохранить ревизию", "callback": f"upp:a:{token}"},
            {"text": "Отмена", "callback": "upp:c"},
        ]
        return self._result("SALES_MIX_PREVIEW", "\n".join(lines)[:3800], self._keyboard(buttons),
                            sales_mix_result=result, read_only=True, executed=False)

    def _append_sales_mix_advertising_cap(self, lines, payload, result):
        """Show summed standalone caps without claiming a group optimization."""
        if self.advertising_cap_service is None:
            return
        target = payload.get("target_margin_percent")
        if target is None or result.get("tax_status") != "CONFIRMED":
            return
        item_by_id = {
            str(item.get("row_id") or (item.get("identity") or {}).get("sku") or ""): item
            for item in payload.get("items", []) if isinstance(item, dict)
        }
        quantities = {row.get("row_id"): row.get("quantity") for row in result.get("rows", [])}
        if len(quantities) != len(item_by_id) or any(value is None for value in quantities.values()):
            return
        total = Decimal("0.00")
        for row_id, item in item_by_id.items():
            quantity = quantities.get(row_id)
            if type(quantity) is not int:
                return
            if quantity == 0:
                continue
            cap = self.advertising_cap_service.solve(item.get("inputs") or {}, target)
            target_cap = cap.get("target") if isinstance(cap, dict) else None
            if not isinstance(target_cap, dict) or target_cap.get("available") is not True:
                return
            amount = self.sales_mix_planning_service._decimal(target_cap.get("advertising_per_unit"))
            if amount is None or amount < 0:
                return
            total += (amount * quantity).quantize(Decimal("0.01"))
        lines.append(
            f"Сумма индивидуальных рекламных пределов при цели {target}%: "
            f"{total:.2f} ₽/период. Это сумма лимитов отдельных SKU; "
            "она не оптимизирует и не гарантирует маржу группы."
        )

    def _skip_sales_mix_quantity(self, scope, action):
        with self._lock:
            pending = self._pending.get(scope["key"])
            if (not isinstance(pending, dict) or pending.get("kind") != "sales_mix"
                    or pending.get("stage") != "quantity"
                    or pending.get("ticket") != action.get("ticket")
                    or pending.get("document_id") != action.get("document_id")
                    or pending.get("revision") != action.get("revision")
                    or pending.get("row_index") != action.get("row_index")):
                return self._stale()
            updated = deepcopy(pending)
            updated["row_index"] += 1
            count = len(updated["payload"].get("items") or [])
            if updated["row_index"] >= count:
                updated["stage"] = "expense_count"
                message = "Введите число дополнительных расходов за период. Введите 0, если явно подтверждаете пустой список."
            else:
                message = "Количество оставлено неизвестным. Введите целое Q или пропустите следующую строку кнопкой."
            self._pending[scope["key"]] = updated
        return self._sales_mix_prompt(scope, updated, message)

    def _confirm_sales_mix(self, scope, action):
        with self._lock:
            pending = deepcopy(self._pending.get(scope["key"]))
        if (not isinstance(pending, dict) or pending.get("kind") != "sales_mix"
                or pending.get("stage") != "preview"
                or pending.get("ticket") != action.get("ticket")
                or pending.get("document_id") != action.get("document_id")
                or pending.get("revision") != action.get("revision")):
            return self._stale()
        payload = pending.get("payload") or {}
        sales_mix = {
            "period_label": pending.get("period_label"),
            "quantities": deepcopy(pending.get("quantities") or {}),
            "expenses": deepcopy(pending.get("expenses") or []),
            "confirmed": pending.get("expenses_confirmed") is True,
        }
        verified = self.sales_mix_planning_service.calculate(
            payload.get("items"), quantities=sales_mix["quantities"],
            period_label=sales_mix["period_label"], expenses=sales_mix["expenses"],
            expenses_confirmed=sales_mix["confirmed"],
        )
        if verified.get("error") is True or verified != pending.get("preview"):
            with self._lock:
                current = self._pending.get(scope["key"])
                if isinstance(current, dict) and current.get("ticket") == pending.get("ticket"):
                    self._pending.pop(scope["key"], None)
            return self._stale()
        # Re-check the ticket after the pure calculation. Another update may
        # have replaced this user's draft while verification was running.
        with self._lock:
            current = self._pending.get(scope["key"])
            if (not isinstance(current, dict)
                    or current.get("kind") != "sales_mix"
                    or current.get("stage") != "preview"
                    or current.get("ticket") != pending.get("ticket")
                    or current.get("document_id") != pending.get("document_id")
                    or current.get("revision") != pending.get("revision")):
                return self._stale()
            result = self.planning_service.save_sales_mix_revision(
                pending["document_id"], sales_mix,
                expected_revision=pending["revision"],
                expected_state_revision=pending["state_revision"],
                idempotency_key=pending["ticket"],
            )
            self._pending.pop(scope["key"], None)
        if result.get("error") is True:
            return self._error(result.get("code"))
        document = self.planning_service.get_document(
            pending["document_id"], revision=result.get("revision"),
        )
        return self._detail_screen(scope, document)

    def _refresh_plan_fact(self, scope, action, user_id):
        if self.period_profit_sku_runtime is None or self.plan_fact_comparison_service is None:
            return self._error("PLAN_FACT_SOURCE_UNAVAILABLE")
        document_result = self.planning_service.get_document(
            action.get("document_id"), revision=action.get("revision"),
        )
        if document_result.get("error") is True:
            return self._error(document_result.get("code"))
        document = document_result.get("document") or {}
        if (
            document.get("owner_id") != scope["owner_id"]
            or document.get("store_id") != scope["store_id"]
            or document.get("current_revision") != action.get("current_revision")
        ):
            return self._error("PLANNING_DOCUMENT_REVISION_CONFLICT")
        payload = document.get("payload") or {}
        mix = payload.get("sales_mix")
        items = payload.get("items")
        if not isinstance(mix, dict) or not isinstance(items, list):
            return self._error("PLAN_FACT_SALES_MIX_REQUIRED")
        current_calculation_version = getattr(
            self.sales_mix_planning_service.scenario_service, "VERSION", None
        )
        if payload.get("calculation_version") != current_calculation_version:
            return self._error("PLAN_FACT_CALCULATION_VERSION_INCOMPATIBLE")
        period = self.plan_fact_comparison_service._period(mix.get("period_label"))
        if period is None:
            return self._error("PLAN_FACT_PERIOD_INVALID")
        identities = [item.get("identity") for item in items if isinstance(item, dict)]
        if len(identities) != len(items):
            return self._error("PLAN_FACT_IDENTITY_INVALID")

        inflight_key = (
            scope["tenant_scope"], str(document.get("document_id") or ""),
            int(document.get("revision") or 0),
        )
        with self._lock:
            if inflight_key in self._plan_fact_inflight:
                return self._result(
                    "PLAN_FACT_QUERY_IN_PROGRESS",
                    "Сверка этого плана за период уже выполняется. Повторный запрос не запущен.",
                    self._keyboard([{"text": "К карточке плана", "callback": self._action_callback(
                        scope, "open", document_id=document["document_id"], revision=document["revision"]
                    )}]),
                )
            self._plan_fact_inflight.add(inflight_key)
        generation_result = self.comparison_snapshot_store.begin_generation(
            scope["owner_id"], scope["store_id"], "plan_fact",
        )
        if generation_result.get("error") is True:
            with self._lock:
                self._plan_fact_inflight.discard(inflight_key)
            return self._error(generation_result.get("code"))
        generation = generation_result["generation"]
        try:
            fact_result = self.period_profit_sku_runtime.query_selected_identities(
                identities, date_from=period[0], date_to=period[1],
            )
            if not isinstance(fact_result, dict) or fact_result.get("error") is True:
                code = fact_result.get("code") if isinstance(fact_result, dict) else None
                return self._error(code or "PLAN_FACT_QUERY_FAILED")
            # Reject a completed response if the plan was revised while the
            # bounded Ozon request was running.
            latest = self.planning_service.get_document(document["document_id"])
            latest_document = latest.get("document") if isinstance(latest, dict) else None
            if (
                not isinstance(latest_document, dict)
                or latest_document.get("current_revision") != action.get("current_revision")
                or latest_document.get("owner_id") != scope["owner_id"]
                or latest_document.get("store_id") != scope["store_id"]
            ):
                return self._error("PLANNING_DOCUMENT_REVISION_CONFLICT")
            generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            comparison = self.plan_fact_comparison_service.compare(
                document_result, fact_result,
                tenant_scope=scope["tenant_scope"], generated_at_utc=generated_at,
            )
            if comparison.get("error") is True:
                return self._error(comparison.get("code"))
            stored = self.comparison_snapshot_store.put_snapshot(
                scope["owner_id"], scope["store_id"], "plan_fact",
                generation, int(document["revision"]),
                {"status": "CURRENT", "captured_at_utc": generated_at},
                comparison.get("coverage") or {},
                [{
                    "row_id": "comparison",
                    "comparison": comparison,
                    "document_title": document.get("title"),
                    "document_id": document.get("document_id"),
                    "revision": document.get("revision"),
                    "current_revision": document.get("current_revision"),
                }],
            )
            if stored.get("error") is True:
                return self._error(stored.get("code"))
            snapshot = stored["snapshot"]
            return self._render_plan_fact_snapshot(scope, snapshot)
        finally:
            with self._lock:
                self._plan_fact_inflight.discard(inflight_key)

    def _read_plan_fact_snapshot(self, scope, action, kind):
        snapshot_result = self.comparison_snapshot_store.get_snapshot(
            action.get("snapshot_id"), scope["owner_id"], scope["store_id"],
            "plan_fact", action.get("generation"), action.get("version"),
        )
        if snapshot_result.get("error") is True:
            return self._result(
                "PLAN_FACT_SNAPSHOT_EXPIRED",
                "Снимок сверки истёк или устарел. Нажмите «Обновить факт» в карточке сохранённого плана.",
                self._saved_keyboard(),
            )
        snapshot = snapshot_result.get("snapshot") or {}
        row = next((item for item in snapshot.get("rows", []) if item.get("row_id") == "comparison"), None)
        if not isinstance(row, dict) or not isinstance(row.get("comparison"), dict):
            return self._error("PLAN_FACT_SNAPSHOT_INVALID")
        if kind == "plan_fact_export":
            if self.analytics_export_service is None:
                return self._error("ANALYTICS_EXPORT_UNAVAILABLE")
            return self.analytics_export_service.export_plan_fact_comparison(
                row, action.get("file_format"),
            )
        return self._render_plan_fact_snapshot(
            scope, snapshot, details=kind == "plan_fact_details",
        )

    def _comparison_picker(self, scope, action, offset=0):
        if self.plan_comparison_service is None:
            return self._error("PLANNING_COMPARISON_UNAVAILABLE")
        first = self.planning_service.get_document(
            action.get("document_id"), revision=action.get("revision"),
        )
        if first.get("error") is True:
            return self._error(first.get("code"))
        first_doc = first.get("document") or {}
        if first_doc.get("owner_id") != scope["owner_id"] or first_doc.get("store_id") != scope["store_id"]:
            return self._error("PLANNING_TENANT_SCOPE_MISMATCH")
        page = self.planning_service.list_documents(
            include_archived=True, limit=self.PAGE_SIZE, offset=offset,
        )
        if page.get("error") is True:
            return self._error(page.get("code"))
        buttons = []
        lines = [
            "Выберите второй сохранённый вариант.",
            f"Первый: {first_doc.get('title')} · версия {first_doc.get('revision')}.",
            "Показаны ревизии и копии этого магазина; просмотр не обращается к Ozon.",
        ]
        revisions = self.planning_service.list_revisions(first_doc.get("document_id"))
        if revisions.get("error") is False:
            for item in revisions.get("items") or []:
                if item.get("revision") == first_doc.get("revision"):
                    continue
                buttons.append({
                    "text": f"{first_doc.get('title', 'План')[:24]} · версия {item['revision']}",
                    "callback": self._action_callback(
                        scope, "compare_pick", first_document_id=first_doc["document_id"],
                        first_revision=first_doc["revision"], second_document_id=first_doc["document_id"],
                        second_revision=item["revision"],
                    ),
                })
        for item in page.get("items") or []:
            if (item.get("document_id") == first_doc.get("document_id")
                    and item.get("revision") == first_doc.get("revision")):
                continue
            title = str(item.get("title") or "План")[:32]
            buttons.append({
                "text": f"{title} · v{item.get('revision')}",
                "callback": self._action_callback(
                    scope, "compare_pick", first_document_id=first_doc["document_id"],
                    first_revision=first_doc["revision"], second_document_id=item["document_id"],
                    second_revision=item["revision"],
                ),
            })
        if page.get("has_more"):
            buttons.append({
                "text": "Следующая страница",
                "callback": self._action_callback(
                    scope, "compare_page", document_id=first_doc["document_id"],
                    revision=first_doc["revision"], offset=page["next_offset"],
                ),
            })
        if not buttons:
            lines.append("Сохранённых альтернативных версий пока нет. Сначала сохраните копию или новую ревизию.")
        buttons.extend([
            {"text": "К карточке плана", "callback": self._action_callback(
                scope, "open", document_id=first_doc["document_id"], revision=first_doc["revision"],
            )},
            {"text": "Мои планы", "callback": "upp:m"},
        ])
        return self._result("PLANNING_COMPARISON_PICKER", "\n".join(lines), self._keyboard(buttons))

    def _compare_saved_documents(self, scope, action):
        first = self.planning_service.get_document(
            action.get("first_document_id"), revision=action.get("first_revision"),
        )
        second = self.planning_service.get_document(
            action.get("second_document_id"), revision=action.get("second_revision"),
        )
        if first.get("error") is True or second.get("error") is True:
            return self._error("PLANNING_DOCUMENT_NOT_FOUND")
        first_doc, second_doc = first.get("document") or {}, second.get("document") or {}
        comparison = self.plan_comparison_service.compare(first, second)
        if comparison.get("error") is True:
            return self._error(comparison.get("code"))
        generation_result = self.comparison_snapshot_store.begin_generation(
            scope["owner_id"], scope["store_id"], "plan_comparison",
        )
        if generation_result.get("error") is True:
            return self._error(generation_result.get("code"))
        generation = generation_result["generation"]
        version = max(int(first_doc.get("revision") or 0), int(second_doc.get("revision") or 0))
        stored = self.comparison_snapshot_store.put_snapshot(
            scope["owner_id"], scope["store_id"], "plan_comparison",
            generation, version, {"status": "HISTORICAL_ASSUMPTIONS"},
            comparison.get("scope") or {}, [{
                "row_id": "comparison", "comparison": comparison,
            }],
        )
        if stored.get("error") is True:
            return self._error(stored.get("code"))
        return self._render_plan_comparison_snapshot(scope, stored["snapshot"])

    def _read_plan_comparison_snapshot(self, scope, action, kind):
        snapshot_result = self.comparison_snapshot_store.get_snapshot(
            action.get("snapshot_id"), scope["owner_id"], scope["store_id"],
            "plan_comparison", action.get("generation"), action.get("version"),
        )
        if snapshot_result.get("error") is True:
            return self._result(
                "PLANNING_COMPARISON_SNAPSHOT_EXPIRED",
                "Снимок сравнения истёк. Откройте карточку плана и сформируйте сравнение снова.",
                self._saved_keyboard(),
            )
        snapshot = snapshot_result.get("snapshot") or {}
        row = next((item for item in snapshot.get("rows", []) if item.get("row_id") == "comparison"), None)
        if not isinstance(row, dict):
            return self._error("PLANNING_COMPARISON_SNAPSHOT_INVALID")
        if kind == "plan_comparison_export":
            if self.analytics_export_service is None:
                return self._error("ANALYTICS_EXPORT_UNAVAILABLE")
            return self.analytics_export_service.export_plan_comparison(
                row, action.get("file_format"),
            )
        return self._render_plan_comparison_snapshot(
            scope, snapshot, offset=action.get("offset", 0),
        )

    def _render_plan_comparison_snapshot(self, scope, snapshot, offset=0):
        row = next((item for item in snapshot.get("rows", []) if item.get("row_id") == "comparison"), None)
        comparison = row.get("comparison") if isinstance(row, dict) else None
        if not isinstance(comparison, dict):
            return self._error("PLANNING_COMPARISON_SNAPSHOT_INVALID")
        first, second = comparison.get("first") or {}, comparison.get("second") or {}
        lines = [
            "Сравнение сохранённых вариантов · исторические допущения",
            f"1. {first.get('title')} · версия {first.get('revision')}",
            f"2. {second.get('title')} · версия {second.get('revision')}",
            "Снимки источников не обновлялись.",
        ]
        if comparison.get("status") in {"NOT_COMPARABLE", "INPUTS_ONLY"}:
            lines.append("Итоговые метрики нельзя честно сопоставить: " + self._comparison_reason_label(comparison.get("reason")))
        dimensions = comparison.get("changed_dimensions") or []
        if dimensions:
            labels = {"price": "цена", "volume": "объём продаж", "assumptions": "другие допущения", "fixed_expenses": "дополнительные расходы", "period": "период"}
            lines.append("Между вариантами меняется: " + ", ".join(labels.get(item, item) for item in dimensions) + ".")
        scope_changes = []
        input_changes = []
        for product in comparison.get("input_changes") or []:
            identity = product.get("identity") or {}
            label = str(
                identity.get("product_name") or identity.get("offer_id")
                or identity.get("sku") or "Товар"
            )[:60]
            scope_status = product.get("scope_status")
            if scope_status in {"ADDED_IN_SECOND", "REMOVED_FROM_SECOND"}:
                sku = identity.get("sku")
                suffix = f" · SKU {sku}" if sku else ""
                direction = "добавлен во втором варианте" if scope_status == "ADDED_IN_SECOND" else "есть только в первом варианте"
                scope_changes.append(f"• Состав SKU · {label}{suffix}: {direction}.")
                continue
            for change in product.get("changes") or []:
                input_changes.append(
                    f"• {label} · {change.get('label')}: "
                    f"{change.get('before', '—')} → {change.get('after', '—')} "
                    f"{change.get('unit', '')}"
                )
        expense_changes = [
            f"• Расход «{str(change.get('name') or 'Без названия')[:60]}»: "
            f"{change.get('before', '0.00')} → {change.get('after', '0.00')} ₽ "
            f"(изменение {change.get('delta', '—')} ₽)."
            for change in comparison.get("expense_changes") or []
            if isinstance(change, dict)
        ]
        # Put SKU additions/removals first so scope changes are visible before
        # long per-field histories. All entries remain reachable by page.
        changes = scope_changes + input_changes + expense_changes
        total_changes = len(changes)
        try:
            requested_offset = int(offset)
        except (TypeError, ValueError):
            requested_offset = 0
        page_offset = min(max(0, requested_offset), max(0, total_changes - 1))
        page_offset = (page_offset // self.COMPARISON_PAGE_SIZE) * self.COMPARISON_PAGE_SIZE
        page_end = min(total_changes, page_offset + self.COMPARISON_PAGE_SIZE)
        if total_changes:
            lines.append(f"Изменения {page_offset + 1}–{page_end} из {total_changes}:")
            lines.extend(self._truncate_utf16(line, 220) for line in changes[page_offset:page_end])
        else:
            lines.append("Введённые параметры не изменились.")
        for metric, label in (("revenue", "Выручка"), ("profit", "Прибыль"), ("margin_percent", "Маржа")):
            item = (comparison.get("metrics") or {}).get(metric) or {}
            if item.get("status") == "COMPARABLE":
                unit = " п.п." if metric == "margin_percent" else " ₽"
                lines.append(f"{label}: {item['before']} → {item['after']} · изменение {item['delta']}{unit}.")
        if comparison.get("status") == "COMPARABLE":
            lines.append("Сравнение рассчитано для одинаковых SKU, периода, объёма, налоговой политики и версии расчёта.")
        else:
            lines.append("При несовпадении версии расчёта создайте две новые копии одной версии; оригиналы останутся сохранены.")
        token_values = {
            "snapshot_id": snapshot.get("snapshot_id"), "generation": snapshot.get("generation"),
            "version": snapshot.get("version"),
        }
        buttons = []
        if page_offset > 0:
            buttons.append({"text": "К первой странице", "callback": self._action_callback(
                scope, "plan_comparison_view", **token_values, offset=0,
            )})
            if page_offset > self.COMPARISON_PAGE_SIZE:
                buttons.append({"text": "← Предыдущая страница", "callback": self._action_callback(
                    scope, "plan_comparison_view", **token_values,
                    offset=page_offset - self.COMPARISON_PAGE_SIZE,
                )})
        if page_end < total_changes:
            label = "Подробнее" if page_offset == 0 else "Следующая страница →"
            buttons.append({"text": label, "callback": self._action_callback(
                scope, "plan_comparison_view", **token_values, offset=page_end,
            )})
        for file_format in ("csv", "json"):
            buttons.append({"text": file_format.upper(), "callback": self._action_callback(
                scope, "plan_comparison_export", **token_values, file_format=file_format,
            )})
        buttons.extend([
            {"text": "К первому плану", "callback": self._action_callback(
                scope, "open", document_id=first.get("document_id"), revision=first.get("revision"),
            )},
            {"text": "Мои планы", "callback": "upp:m"},
        ])
        return self._result(
            "PLANNING_COMPARISON_READY" if comparison.get("status") == "COMPARABLE" else "PLANNING_COMPARISON_PARTIAL",
            self._truncate_utf16("\n".join(lines), 3500), self._keyboard(buttons),
            plan_comparison=deepcopy(comparison), snapshot_id=snapshot.get("snapshot_id"),
            comparison_page={
                "offset": page_offset, "shown": max(0, page_end - page_offset),
                "total": total_changes,
            },
        )

    @staticmethod
    def _comparison_reason_label(reason):
        labels = {
            "PLAN_KIND_MISMATCH": "различается формат вариантов.",
            "CALCULATION_VERSION_MISMATCH": "варианты рассчитаны разными версиями калькулятора.",
            "CALCULATION_VERSION_UNSUPPORTED": "версия калькулятора в сохранённых вариантах больше не поддерживается текущим расчётом.",
            "PRODUCT_SCOPE_MISMATCH": "в вариантах различается набор SKU; показаны только общие строки и состав наборов.",
            "PERIOD_MISMATCH": "указаны разные периоды.",
            "CONFIRMED_SALES_MIX_REQUIRED": "не в обоих вариантах подтверждены период и количества успешных продаж.",
            "INCOMPLETE_SALES_MIX": "в одном из вариантов не заполнены все строки.",
            "TAX_POLICY_MISMATCH_OR_UNKNOWN": "налоговые режимы различаются или не подтверждены.",
            "RESULT_METRIC_UNAVAILABLE": "итоговая прибыль или маржа не определена.",
        }
        return labels.get(reason, "для итогового сравнения недостаточно совместимых данных.")

    def _export_saved_document(self, scope, action, kind):
        if self.analytics_export_service is None or action.get("file_format") not in {"csv", "json"}:
            return self._error("ANALYTICS_EXPORT_UNAVAILABLE")
        result = self.planning_service.get_document(
            action.get("document_id"), revision=action.get("revision"),
        )
        if result.get("error") is True:
            return self._error(result.get("code"))
        document = result.get("document") or {}
        if document.get("owner_id") != scope["owner_id"] or document.get("store_id") != scope["store_id"]:
            return self._error("PLANNING_TENANT_SCOPE_MISMATCH")
        payload = document.get("payload") or {}
        if kind == "export_saved_plan":
            projection = None
            mix = payload.get("sales_mix")
            if isinstance(mix, dict) and self.sales_mix_planning_service is not None:
                if payload.get("calculation_version") != getattr(self.sales_mix_planning_service.scenario_service, "VERSION", None):
                    return self._error("PLANNING_HISTORICAL_CALCULATION_INCOMPATIBLE")
                projection = self.sales_mix_planning_service.calculate(
                    payload.get("items"), quantities=mix.get("quantities"),
                    period_label=mix.get("period_label"), expenses=mix.get("expenses"),
                    expenses_confirmed=mix.get("confirmed") is True,
                )
                if projection.get("error") is True:
                    projection = {"status": "UNAVAILABLE", "reason": projection.get("code")}
            return self.analytics_export_service.export_saved_plan(
                document, action["file_format"], sales_mix_projection=projection,
            )
        if kind == "export_sales_mix":
            mix = payload.get("sales_mix")
            if not isinstance(mix, dict) or self.sales_mix_planning_service is None:
                return self._error("SALES_MIX_PLANNING_UNAVAILABLE")
            if payload.get("calculation_version") != getattr(self.sales_mix_planning_service.scenario_service, "VERSION", None):
                return self._error("PLANNING_HISTORICAL_CALCULATION_INCOMPATIBLE")
            projection = self.sales_mix_planning_service.calculate(
                payload.get("items"), quantities=mix.get("quantities"),
                period_label=mix.get("period_label"), expenses=mix.get("expenses"),
                expenses_confirmed=mix.get("confirmed") is True,
            )
            return self.analytics_export_service.export_sales_mix(
                document, projection, action["file_format"],
            )
        if kind == "export_advertising_cap":
            if self.advertising_cap_service is None:
                return self._error("UNIT_PRICE_ADVERTISING_CAP_UNAVAILABLE")
            if payload.get("calculation_version") != getattr(self.advertising_cap_service.scenario_service, "VERSION", None):
                return self._error("PLANNING_HISTORICAL_CALCULATION_INCOMPATIBLE")
            target = payload.get("target_margin_percent")
            caps = []
            for item in payload.get("items") or []:
                identity = item.get("identity") or {}
                result = self.advertising_cap_service.solve(
                    item.get("inputs") or {}, target if target is not None else 0,
                    identity=identity, provenance=item.get("provenance") or {},
                    sources=item.get("sources") or {},
                )
                be = result.get("break_even") or {}
                goal = result.get("target") or {}
                caps.append({
                    "product_id": identity.get("product_id"), "offer_id": identity.get("offer_id"),
                    "sku": identity.get("sku"), "status": result.get("status") or result.get("code"),
                    "target_margin_percent": target,
                    "break_even_rate": be.get("advertising_rate"),
                    "break_even_per_unit": be.get("advertising_per_unit"),
                    "target_rate": goal.get("advertising_rate") if target is not None else None,
                    "target_per_unit": goal.get("advertising_per_unit") if target is not None else None,
                    "inputs": item.get("inputs") or {},
                })
            return self.analytics_export_service.export_advertising_cap(
                document, caps, action["file_format"],
            )
        return self._stale()

    def _render_plan_fact_snapshot(self, scope, snapshot, *, details=False):
        rows = snapshot.get("rows") or []
        row = next((item for item in rows if item.get("row_id") == "comparison"), None)
        comparison = row.get("comparison") if isinstance(row, dict) else None
        if not isinstance(comparison, dict):
            return self._error("PLAN_FACT_SNAPSHOT_INVALID")
        plan = comparison.get("plan") or {}
        actual = comparison.get("actual") or {}
        revenue = comparison.get("revenue_comparison") or {}
        if details:
            lines = [
                "Детали сопоставимости",
                "Количество факта: " + str(actual.get("quantity_basis") or "не подтверждено точными данными о проданных единицах"),
                "Выручка плана: цена продавца × введённое количество успешных продаж.",
                "Фактическая выручка: финансовая сумма продажи Ozon; баллы за скидки представлены отдельно.",
                str(revenue.get("note") or ""),
                "Прибыль не сравнивается: реклама и внешние расходы не подтверждены для выбранного состава SKU, а Return COGS может относиться к уровню магазина.",
                "Снимок построен " + str(comparison.get("generated_at_utc") or "неизвестно") + "; открытие деталей не обновляет Ozon.",
            ]
        else:
            lines = [
                f"План и факт за {plan.get('period', {}).get('date_from')} — {plan.get('period', {}).get('date_to')}",
                f"План · {row.get('document_title') or 'Сохранённый план'} · версия {plan.get('revision')}",
                f"Успешные продажи: план {plan.get('quantity') if plan.get('quantity') is not None else 'неполный'}, факт {actual.get('quantity') if actual.get('quantity') is not None else 'не подтверждён'} шт.",
                f"Выручка: план {plan.get('revenue') if plan.get('revenue') is not None else 'неполный'} ₽, факт {actual.get('revenue')} ₽, разница {revenue.get('delta') if revenue.get('delta') is not None else 'не рассчитана'} ₽.",
                f"Разложение разницы: количество {revenue.get('quantity_effect') if revenue.get('quantity_effect') is not None else '—'} ₽; фактическая выручка на единицу {revenue.get('actual_average_revenue_effect') if revenue.get('actual_average_revenue_effect') is not None else '—'} ₽.",
                f"Прибыль плана {plan.get('profit') if plan.get('profit') is not None else 'не определена'} ₽; прибыль факта группы {actual.get('profit') if actual.get('profit') is not None else 'недоступна'} ₽ — сопоставимая разница не рассчитана.",
                f"Точное сопоставление SKU: {comparison.get('coverage', {}).get('matched_exact_identities', 0)}/{comparison.get('coverage', {}).get('selected_identities', 0)}; количество факта: {actual.get('quantity_status')}.",
                "Факт обновлён " + str(comparison.get("generated_at_utc") or "неизвестно") + ". Кнопки и выгрузки читают этот снимок без повторного запроса.",
            ]
        buttons = [
            {"text": "Подробнее" if not details else "К результату", "callback": self._action_callback(
                scope, "plan_fact_details" if not details else "plan_fact_view",
                snapshot_id=snapshot.get("snapshot_id"), generation=snapshot.get("generation"),
                version=snapshot.get("version"),
            )},
            {"text": "CSV", "callback": self._action_callback(
                scope, "plan_fact_export", snapshot_id=snapshot.get("snapshot_id"),
                generation=snapshot.get("generation"), version=snapshot.get("version"),
                file_format="csv",
            )},
            {"text": "JSON", "callback": self._action_callback(
                scope, "plan_fact_export", snapshot_id=snapshot.get("snapshot_id"),
                generation=snapshot.get("generation"), version=snapshot.get("version"),
                file_format="json",
            )},
            {"text": "Обновить факт", "callback": self._action_callback(
                scope, "plan_fact_refresh", document_id=row.get("document_id"),
                revision=row.get("revision"), current_revision=row.get("current_revision"),
            )},
            {"text": "К карточке плана", "callback": self._action_callback(
                scope, "open", document_id=row.get("document_id"), revision=row.get("revision"),
            )},
            {"text": "Главное меню", "callback": "main_menu"},
        ]
        return self._result(
            "PLAN_FACT_COMPARISON_READY" if comparison.get("status") == "COMPARABLE" else "PLAN_FACT_COMPARISON_PARTIAL",
            "\n".join(lines), self._keyboard(buttons),
            plan_fact_comparison=deepcopy(comparison),
            snapshot_id=snapshot.get("snapshot_id"),
            source_freshness=deepcopy(snapshot.get("source_freshness") or {}),
        )

    def _show_historical_advertising_cap(self, scope, action):
        result = self.planning_service.get_document(
            action.get("document_id"), revision=action.get("revision"),
        )
        if result.get("error") is True:
            return self._error(result.get("code"))
        document = result.get("document") or {}
        payload = document.get("payload") or {}
        if payload.get("calculation_version") != getattr(
            getattr(self.advertising_cap_service, "scenario_service", None), "VERSION", None
        ):
            return self._result(
                "PLANNING_HISTORICAL_CALCULATION_INCOMPATIBLE",
                "Эта версия плана использует другую версию расчёта. Исторические результаты сохранены; для сравнения создайте новые планы одной версии.",
                self._keyboard([{"text": "К карточке плана", "callback": self._action_callback(
                    scope, "open", document_id=document.get("document_id"),
                    revision=document.get("revision"),
                )}]),
            )
        target = payload.get("target_margin_percent")
        lines = [
            f"Рекламные пределы · историческая версия {document.get('revision')}",
            "Расчёт использует только сохранённые допущения и не обновляет Ozon.",
            "Исторический результат нельзя подставить напрямую; продолжите план для нового transient-сценария.",
        ]
        cap_rows = []
        for index, item in enumerate(payload.get("items") or [], start=1):
            if not isinstance(item, dict):
                continue
            inputs = item.get("inputs") or {}
            identity = item.get("identity") or {}
            cap = self.advertising_cap_service.solve(
                inputs, target if target is not None else 0,
                identity=identity, provenance=item.get("provenance") or {},
                sources=item.get("sources") or {},
            )
            label = str(identity.get("product_name") or "Товар")[:40]
            if cap.get("error") is True:
                lines.append(f"{index}. {label}: предел недоступен ({cap.get('code')}).")
                cap_rows.append({"product_id": identity.get("product_id"),
                                 "offer_id": identity.get("offer_id"), "sku": identity.get("sku"),
                                 "status": cap.get("code"), "inputs": inputs})
                continue
            be = cap.get("break_even") or {}
            tm = cap.get("target") or {}
            cap_rows.append({
                "product_id": identity.get("product_id"), "offer_id": identity.get("offer_id"),
                "sku": identity.get("sku"), "status": "AVAILABLE",
                "target_margin_percent": target,
                "break_even_rate": be.get("advertising_rate"),
                "break_even_per_unit": be.get("advertising_per_unit"),
                "target_rate": tm.get("advertising_rate") if target is not None else None,
                "target_per_unit": tm.get("advertising_per_unit") if target is not None else None,
                "inputs": inputs,
            })
            lines.append(
                f"{index}. {label} · безубыточность {be.get('advertising_rate', '—')}% "
                f"({be.get('advertising_per_unit', '—')} ₽/шт.); "
                + (f"цель {target}%: {tm.get('advertising_rate', '—')}% ({tm.get('advertising_per_unit', '—')} ₽/шт.)."
                   if target is not None else "целевой предел не рассчитан: у сохранённой версии нет явной цели." )
            )
        callback = self._action_callback(
            scope, "continue", document_id=action.get("document_id"),
            revision=action.get("revision"),
        )
        buttons = [
            {"text": "Продолжить план", "callback": callback},
            {"text": "К карточке плана", "callback": self._action_callback(scope, "open", document_id=action.get("document_id"), revision=action.get("revision"))},
            {"text": "Мои планы", "callback": "upp:m"},
        ]
        if self.analytics_export_service is not None:
            for file_format in ("csv", "json"):
                buttons.insert(0, {"text": "Экспорт предела · " + file_format.upper(),
                    "callback": self._action_callback(
                        scope, "export_advertising_cap", document_id=action.get("document_id"),
                        revision=action.get("revision"), file_format=file_format,
                    )})
        return self._result(
            "PLANNING_HISTORICAL_ADVERTISING_CAP",
            "\n".join(lines)[:3000],
            self._keyboard(buttons),
        )

    def _add_update_controls(
        self, result, scope, *, plan_kind, document_id, revision, state_revision,
        scenario_id=None, batch_id=None, version=None,
    ):
        """Offer explicit CAS update and copy after a successful source refresh."""
        if not isinstance(result, dict) or result.get("error") is True:
            return result
        keyboard = result.get("keyboard")
        buttons = list((keyboard or {}).get("buttons") or [])
        copy_button = next((item for item in buttons if item.get("text") == "💾 Сохранить план"), None)
        if copy_button is not None:
            copy_button["text"] = "📄 Сохранить копию"
        if plan_kind == "single":
            # The callback keyboard is generated from the exact live session;
            # calculation projections may carry an older version-shaped field.
            values = {
                "scenario_id": scenario_id or self._scenario_id_from_result(result),
                "version": version or self._scenario_version_from_result(result),
            }
        else:
            batch = result.get("batch_plan") or {}
            values = {
                "batch_id": batch_id or batch.get("batch_id"),
                "version": version or batch.get("version"),
            }
        if not values.get("version") or not values.get("scenario_id", values.get("batch_id")):
            result["keyboard"] = self._keyboard(buttons)
            return result
        callback = self._action_callback(
            scope, "save_update", document_id=document_id, revision=revision,
            state_revision=state_revision,
            plan_kind=plan_kind, **values,
        )
        buttons.insert(0, {"text": "💾 Сохранить изменения в этот план", "callback": callback})
        result["keyboard"] = self._keyboard(buttons)
        return result

    @staticmethod
    def _preserve_saved_plan_context(document, capture):
        """Carry confirmed period inputs across an exact-identity editor update."""
        if not isinstance(document, dict) or not isinstance(capture, dict):
            return {"error": True, "code": "PLANNING_CAPTURE_INVALID"}
        old_payload = document.get("payload")
        new_payload = deepcopy(capture.get("payload"))
        if not isinstance(old_payload, dict) or not isinstance(new_payload, dict):
            return {"error": True, "code": "PLANNING_CAPTURE_INVALID"}
        sales_mix = old_payload.get("sales_mix")
        if old_payload.get("plan_kind") != new_payload.get("plan_kind"):
            return {"error": True, "code": "PLANNING_PLAN_IDENTITY_CHANGED"}

        def rows_by_identity(items):
            if not isinstance(items, list):
                return None
            rows = {}
            for item in items:
                if not isinstance(item, dict):
                    return None
                identity = item.get("identity")
                if not isinstance(identity, dict):
                    return None
                required_identity = tuple(
                    str(identity.get(field) or "").strip()
                    for field in ("product_id", "offer_id", "sku")
                )
                normalized_store_id = str(identity.get("store_id") or "").strip()
                key = (*required_identity, normalized_store_id)
                if not all(required_identity) or key in rows:
                    return None
                row_id = str(item.get("row_id") or identity.get("sku") or "")
                if not row_id:
                    return None
                if row_id in rows.values():
                    return None
                rows[key] = row_id
            return rows

        previous_rows = rows_by_identity(old_payload.get("items"))
        current_rows = rows_by_identity(new_payload.get("items"))
        if (previous_rows is None or current_rows is None
                or set(previous_rows) != set(current_rows)):
            return {"error": True, "code": "PLANNING_PLAN_IDENTITY_CHANGED"}
        if sales_mix is None:
            return capture
        old_quantities = sales_mix.get("quantities") if isinstance(sales_mix, dict) else None
        if (not isinstance(old_quantities, dict)
                or set(old_quantities) != set(previous_rows.values())):
            return {"error": True, "code": "PLANNING_SALES_MIX_SCOPE_CHANGED"}
        quantities_by_identity = {
            identity: old_quantities[row_id]
            for identity, row_id in previous_rows.items()
        }
        preserved_mix = deepcopy(sales_mix)
        preserved_mix["quantities"] = {
            row_id: quantities_by_identity[identity]
            for identity, row_id in current_rows.items()
        }
        new_payload["sales_mix"] = preserved_mix
        merged = deepcopy(capture)
        merged["payload"] = new_payload
        return merged

    @staticmethod
    def _scenario_id_from_result(result):
        for item in (result.get("keyboard") or {}).get("buttons", []):
            parts = str(item.get("callback") or "").split(":")
            if len(parts) == 5 and parts[:2] == ["upc", "e"]:
                return parts[2]
        return None

    @staticmethod
    def _scenario_version_from_result(result):
        for item in (result.get("keyboard") or {}).get("buttons", []):
            parts = str(item.get("callback") or "").split(":")
            if len(parts) == 5 and parts[:2] == ["upc", "e"]:
                try:
                    return int(parts[3])
                except ValueError:
                    return None
        return None

    @staticmethod
    def _truncate_utf16(value, limit):
        text = str(value or "")
        output = []
        used = 0
        for char in text:
            units = len(char.encode("utf-16-le")) // 2
            if used + units > limit:
                break
            output.append(char)
            used += units
        return "".join(output)

    def _register_action(self, scope, kind, **values):
        token = token_hex(5)
        with self._lock:
            self._actions[token] = {"kind": kind, "owner_id": scope["owner_id"],
                                   "tenant_scope": scope["tenant_scope"],
                                   "created_at": self.clock(), **deepcopy(values)}
            self._actions.move_to_end(token)
            while len(self._actions) > self.MAX_ACTIONS:
                self._actions.popitem(last=False)
        return token

    def _action_callback(self, scope, kind, **values):
        return "upp:a:" + self._register_action(scope, kind, **values)

    def _consume_action(self, token, scope):
        with self._lock:
            action = self._actions.pop(token, None)
        if not isinstance(action, dict) or action.get("owner_id") != scope["owner_id"] or action.get("tenant_scope") != scope["tenant_scope"]:
            return None
        if self.clock() - action.get("created_at", 0) > self.ACTION_TTL_SECONDS:
            return None
        return deepcopy(action)

    def _clear_other_scopes(self, scope):
        with self._lock:
            for key in [key for key in self._pending if key[0] == scope["owner_id"] and key != scope["key"]]:
                self._pending.pop(key, None)
            for token, action in list(self._actions.items()):
                if action.get("owner_id") == scope["owner_id"] and action.get("tenant_scope") != scope["tenant_scope"]:
                    self._actions.pop(token, None)
            for key in [key for key in self._plan_edit_contexts
                        if key[0] == scope["owner_id"] and key[1] != scope["tenant_scope"]]:
                self._plan_edit_contexts.pop(key, None)

    def _clear_plan_edit_contexts(self, scope):
        with self._lock:
            for key in [key for key in self._plan_edit_contexts
                        if key[0] == scope["owner_id"] and key[1] == scope["tenant_scope"]]:
                self._plan_edit_contexts.pop(key, None)

    @staticmethod
    def _scope(user_id):
        owner = str(user_id or "").strip()
        tenant_scope = str(get_current_tenant_user_id() or "").strip()
        scoped_owner, store_id = split_store_tenant_scope(tenant_scope)
        if not owner or not tenant_scope or owner != scoped_owner:
            return None
        # SavedPlanningPlanService and the repository persist the supported
        # legacy/default tenant as an empty store ID. Keep that representation
        # consistent in every runtime scope check.
        return {"owner_id": owner, "store_id": str(store_id or "").strip(), "tenant_scope": tenant_scope,
                "key": (owner, tenant_scope)}

    def _keyboard(self, buttons):
        builder = getattr(self.keyboard_service, "build_unit_price_batch_keyboard", None)
        if callable(builder):
            return builder(buttons)
        safe = [item for item in buttons if isinstance(item, dict)
                and isinstance(item.get("callback"), str)
                and len(item["callback"].encode("utf-8")) <= 64]
        return {"error": False, "type": "inline_keyboard", "buttons": safe}

    def _cancel_keyboard(self):
        return self._keyboard([{"text": "Отмена", "callback": "upp:c"}, {"text": "Главное меню", "callback": "main_menu"}])

    def _saved_keyboard(self):
        return self._keyboard([{"text": "📚 Мои планы", "callback": "upp:m"}, {"text": "Главное меню", "callback": "main_menu"}])

    def _main_keyboard(self):
        builder = getattr(self.keyboard_service, "build_main_keyboard", None)
        return builder() if callable(builder) else self._saved_keyboard()

    @classmethod
    def _normalize_title(cls, value):
        if not isinstance(value, str):
            return None
        normalized = " ".join(value.split())
        return normalized if 1 <= len(normalized) <= 80 else None

    @staticmethod
    def _find_button_callback(keyboard, text):
        for item in (keyboard or {}).get("buttons", []):
            if item.get("text") == text:
                return item.get("callback")
        return None

    @staticmethod
    def _scenario_id_from_keyboard(keyboard):
        for item in (keyboard or {}).get("buttons", []):
            callback = item.get("callback", "")
            parts = callback.split(":")
            if len(parts) >= 4 and parts[:2] == ["upc", "v"]:
                return parts[2]
        return None

    @staticmethod
    def _scenario_version_from_keyboard(keyboard):
        for item in (keyboard or {}).get("buttons", []):
            callback = item.get("callback", "")
            parts = callback.split(":")
            if len(parts) >= 4 and parts[:2] == ["upc", "v"]:
                return parts[3]
        return None

    @staticmethod
    def _result(status, message, keyboard, **extra):
        return {"error": False, "status": status, "message": message,
                "keyboard": keyboard, "read_only": True, "executed": False, **extra}

    def _error(self, code):
        code = str(code or "PLANNING_UNAVAILABLE")
        messages = {
            "PLANNING_DOCUMENT_QUOTA_REACHED": "Достигнут общий лимит сохранённых планов магазина, включая архив. Откройте «Мои планы» и удалите ненужный документ только после отдельного подтверждения; архивирование лимит не освобождает.",
            "PLANNING_DOCUMENT_REVISION_LIMIT": "Достигнут лимит версий этого плана. Можно сохранить его отдельной копией, если остаётся место, или удалить документ и версии после подтверждения.",
            "PLANNING_DOCUMENT_TOO_LARGE": "План превышает допустимый размер и не сохранён. Сократите число товаров или лишние допущения и повторите сохранение; текущие документы не изменены.",
            "PLANNING_DOCUMENT_REVISION_CONFLICT": "План уже изменён в другом действии. Откройте его заново и повторите сохранение; новая версия не перезаписана.",
            "PLANNING_DOCUMENT_STATE_CONFLICT": "Название или состояние плана изменилось после открытия действия. Откройте план заново и подтвердите нужное действие ещё раз.",
            "PLANNING_DOCUMENT_STATE_REVISION_REQUIRED": "Действие устарело. Откройте план заново, чтобы получить актуальное состояние.",
            "PLANNING_STORAGE_UNAVAILABLE": "Локальное хранилище планов временно недоступно. Ничего не сохранено; повторите позже.",
            "PLANNING_PLAN_IDENTITY_CHANGED": "Карточка товара или состав плана изменились. Старые ручные значения не перенесены; сохраните отдельную копию для нового состава.",
            "PLAN_FACT_CALCULATION_VERSION_INCOMPATIBLE": "У этой версии плана другая версия расчёта. Сначала откройте план и создайте актуальную локальную ревизию; исходная версия останется сохранённой.",
            "PLAN_FACT_PERIOD_INVALID": "В плане не удалось подтвердить календарный период. Откройте план и задайте период заново.",
            "PLAN_FACT_ACTUAL_SCOPE_MISMATCH": "Не удалось точно сопоставить весь набор SKU с текущими товарами. Факт не приложен к плану.",
            "PERIOD_PROFIT_SELECTED_GROUP_IDENTITY_UNRESOLVED": "Один из SKU не совпал с текущей карточкой товара. Автоматическая замена товара не выполнялась.",
            "PLANNING_DOCUMENT_REVISION_CONFLICT": "План изменился во время запроса. Результат не прикреплён; откройте актуальную версию и повторите сверку.",
        }
        return {"error": True, "code": str(code or "PLANNING_UNAVAILABLE"),
                "message": messages.get(code, "Сохранённые планы сейчас недоступны. Текущий план не изменён."),
                "keyboard": self._main_keyboard(), "read_only": True, "executed": False}

    def _stale(self):
        return self._result("PLANNING_ACTION_STALE",
                            "Кнопка устарела или относится к другому магазину. Откройте список планов заново.",
                            self._saved_keyboard())
