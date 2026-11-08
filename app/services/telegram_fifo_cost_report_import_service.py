"""Tenant-bound Telegram preview/confirm flow for FIFO source reports."""

from __future__ import annotations

from hashlib import sha256
from threading import RLock
from time import monotonic
from uuid import uuid4

from services.fifo_cost_report_import_worker_client import (
    FifoCostReportImportWorkerClient,
)
from services.fifo_cost_transition_contracts import (
    ReportType,
    ScopeIdentity,
    TransitionState,
)
from services.fifo_cost_repository import FifoCostRepository
from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id


class TelegramFifoCostReportImportService:
    CALLBACK_PREFIX = "fifo_report"
    TTL_SECONDS = 15 * 60
    MAX_SELECTIONS = 512
    MAX_PREVIEWS = 1024
    MAX_FILE_BYTES = 10 * 1024 * 1024
    _REPORT_LABELS = {
        ReportType.TURNOVER: "Оборотная ведомость",
        ReportType.STOCK_MANAGEMENT: "Управление остатками",
    }
    _EDITABLE_STATES = frozenset({"DRAFT", "AWAITING_EVIDENCE"})

    def __init__(self, repository=None, worker=None, *, monotonic_clock=monotonic):
        self.repository = repository or FifoCostRepository()
        self.worker = worker or FifoCostReportImportWorkerClient()
        self._monotonic = monotonic_clock
        self._selections = {}
        self._active = {}
        self._previews = {}
        self._lock = RLock()

    def create_selection_callback(self, *, user_id, case_id, scope, report_type):
        owner, tenant, error = self._identity(user_id, scope)
        if error:
            return error
        try:
            report_type = report_type if isinstance(report_type, ReportType) else ReportType(str(report_type))
        except (TypeError, ValueError):
            return self._error("FIFO_REPORT_FORMAT_UNSUPPORTED")
        if report_type not in self._REPORT_LABELS:
            return self._error("FIFO_REPORT_FORMAT_UNSUPPORTED")
        current = self._read_case(case_id, scope)
        if not self._case_editable(current):
            return self._error("FIFO_REPORT_CASE_NOT_EDITABLE")
        now = self._monotonic()
        token = uuid4().hex[:12]
        key = (owner, tenant, token)
        with self._lock:
            self._purge(now)
            self._selections[key] = {
                "user_id": owner,
                "tenant": tenant,
                "case_id": case_id,
                "scope": scope,
                "revision": current["case_revision"],
                "report_type": report_type,
                "expires_at": now + self.TTL_SECONDS,
            }
            self._trim(self._selections, self.MAX_SELECTIONS)
        callback = f"{self.CALLBACK_PREFIX}:select:{token}"
        return {
            "error": False,
            "handled": True,
            "callback": callback,
            "keyboard": self._keyboard(("Выбрать дело для отчёта", callback)),
            "read_only_ozon": True,
        }

    def handle_callback(self, user_id, callback):
        owner, tenant, error = self._identity(user_id)
        if error:
            return error
        parts = str(callback or "").split(":")
        if len(parts) != 3 or parts[0] != self.CALLBACK_PREFIX:
            return {"error": False, "handled": False, "read_only_ozon": True}
        action, token = parts[1:]
        if action not in {"select", "confirm", "cancel"} or not self._valid_token(token):
            return self._error("FIFO_REPORT_CALLBACK_INVALID")
        key = (owner, tenant, token)
        now = self._monotonic()
        with self._lock:
            self._purge(now)
            if action == "select":
                ticket = self._selections.get(key)
                if ticket is None:
                    return self._error("FIFO_REPORT_SELECTION_STALE")
                self._active[(owner, tenant)] = token
                return {
                    "error": False,
                    "handled": True,
                    "message": (
                        f"Дело выбрано для отчёта «{self._REPORT_LABELS[ticket['report_type']]}». "
                        "Теперь отправьте соответствующий XLSX. Ничего не сохранится без подтверждения."
                    ),
                    "read_only_ozon": True,
                }
            if action == "cancel":
                preview = self._previews.pop(key, None)
                if preview is None:
                    return self._error("FIFO_REPORT_PREVIEW_STALE")
                return {
                    "error": False,
                    "handled": True,
                    "message": "Предпросмотр отчёта отменён. Дело и ранее сохранённые сведения не изменены.",
                    "read_only_ozon": True,
                }
            preview = self._previews.get(key)
            if preview is None:
                return self._error("FIFO_REPORT_PREVIEW_STALE")
            if preview.get("confirmed_result") is not None:
                return dict(preview["confirmed_result"], replayed=True)
        return self._confirm(key, preview)

    def handle_document(self, user_id, content, filename=None):
        owner, tenant, error = self._identity(user_id)
        if error:
            return error
        if not isinstance(filename, str) or not filename.lower().endswith(".xlsx"):
            return self._result(
                "Для FIFO отправьте XLSX: «Оборотная ведомость» или «Управление остатками». "
                "CSV-таблицы себестоимости по-прежнему загружаются в обычном меню себестоимости.",
                code="FIFO_REPORT_FORMAT_UNSUPPORTED",
            )
        if isinstance(content, memoryview):
            size = content.nbytes
        elif isinstance(content, (bytes, bytearray)):
            size = len(content)
        else:
            return self._error("FIFO_REPORT_PAYLOAD_INVALID")
        if size <= 0 or size > self.MAX_FILE_BYTES:
            return self._error("FIFO_REPORT_FILE_SIZE_INVALID")
        now = self._monotonic()
        selection_key = None
        with self._lock:
            self._purge(now)
            active_token = self._active.get((owner, tenant))
            if active_token:
                selection_key = (owner, tenant, active_token)
                selection = self._selections.get(selection_key)
            else:
                selection = None
        if selection is None:
            return self._result(
                "Сначала откройте конкретное незавершённое FIFO-дело и выберите тип отчёта, "
                "затем отправьте XLSX. Этот файл сейчас не обработан и не сохранён.",
                code="FIFO_REPORT_CASE_SELECTION_REQUIRED",
            )
        report_type = selection["report_type"]
        expected_ext = ".xlsx"
        if not filename.lower().endswith(expected_ext):
            return self._error("FIFO_REPORT_FORMAT_UNSUPPORTED")
        current = self._read_case(selection["case_id"], selection["scope"])
        if not self._case_matches_selection(current, selection):
            with self._lock:
                if self._active.get((owner, tenant)) == selection_key[2]:
                    self._active.pop((owner, tenant), None)
                self._selections.pop(selection_key, None)
            return self._result(
                "Выбранное FIFO-дело изменилось или больше недоступно. Откройте его заново; файл не сохранён.",
                code="FIFO_REPORT_SELECTION_STALE",
            )

        parsed = self.worker.parse(
            report_type=report_type,
            filename=filename,
            payload=content,
            scope=selection["scope"],
        )
        if not self._valid_parse_result(parsed):
            return self._error("FIFO_REPORT_WORKER_RESULT_INVALID")
        if parsed.status == "ERROR" or parsed.report_evidence is None:
            return self._result(
                "Не удалось проверить отчёт. Дело не изменено; выбранное дело можно использовать для повторной попытки.",
                code=(parsed.issue_codes[0] if parsed.issue_codes else "FIFO_REPORT_PARSE_FAILED"),
            )
        if (
            parsed.report_evidence.metadata.scope != selection["scope"]
            or parsed.report_evidence.report_type is not report_type
        ):
            return self._error("FIFO_REPORT_WORKER_RESULT_INVALID")
        refreshed = self._read_case(selection["case_id"], selection["scope"])
        if not self._case_matches_selection(refreshed, selection):
            return self._result(
                "Дело изменилось во время проверки файла. Отчёт не сохранён; откройте дело заново.",
                code="FIFO_REPORT_SELECTION_STALE",
            )
        report = parsed.report_evidence
        now = self._monotonic()
        preview_token = uuid4().hex[:12]
        preview_key = (owner, tenant, preview_token)
        preview = {
            "user_id": owner,
            "tenant": tenant,
            "selection_token": selection_key[2],
            "case_id": selection["case_id"],
            "scope": selection["scope"],
            "revision": selection["revision"],
            "report": report,
            "status": parsed.status,
            "issue_codes": parsed.issue_codes,
            "filename": filename,
            "expires_at": now + self.TTL_SECONDS,
            "confirmed_result": None,
        }
        with self._lock:
            self._purge(now)
            self._previews[preview_key] = preview
            self._trim(self._previews, self.MAX_PREVIEWS)
        label = self._REPORT_LABELS[report.report_type]
        period = (
            f"{report.period_from} — {report.period_to} (дата-кандидат из имени файла)"
            if report.period_from else "период не определён; подтвердите его отдельно"
        )
        status_text = "структурно полный" if parsed.status == "COMPLETE" else "частичный, требует проверки"
        issue_text = (
            f" Найдены замечания: {len(parsed.issue_codes)}."
            if parsed.issue_codes else ""
        )
        confirm = f"{self.CALLBACK_PREFIX}:confirm:{preview_token}"
        cancel = f"{self.CALLBACK_PREFIX}:cancel:{preview_token}"
        return {
            "error": False,
            "handled": True,
            "code": "FIFO_REPORT_PREVIEW_READY",
            "message": (
                f"Предпросмотр: {label}; {status_text}. Период: {period}."
                f"{issue_text}\nДоказательство пока не записано. Подтверждение добавит этот отчёт в выбранное дело."
            ),
            "keyboard": self._keyboard(
                ("✅ Добавить отчёт в дело", confirm),
                ("Отменить предпросмотр", cancel),
            ),
            "issue_count": len(parsed.issue_codes),
            "read_only_ozon": True,
        }

    def clear_selection(self, user_id):
        owner, tenant, error = self._identity(user_id)
        if error:
            return error
        with self._lock:
            token = self._active.pop((owner, tenant), None)
            if token:
                self._selections.pop((owner, tenant, token), None)
        return {"error": False, "read_only_ozon": True}

    def _confirm(self, key, preview):
        report = preview["report"]
        scope = preview["scope"]
        evidence = self.repository.read_transition_evidence(
            case_id=preview["case_id"], store_id=scope.store_id,
            product_id=scope.product_id, offer_id=scope.offer_id, sku=scope.sku,
            kind="REPORT_EVIDENCE", limit=200,
        )
        if isinstance(evidence, dict) and evidence.get("error") is False:
            for item in evidence.get("items", []):
                if (item.get("file_sha256") == report.file_sha256
                        and item.get("report_type") == report.report_type.value):
                    result = {
                        "error": False,
                        "handled": True,
                        "code": "FIFO_REPORT_EVIDENCE_ALREADY_SAVED",
                        "message": "Этот отчёт уже добавлен в выбранное дело.",
                        "read_only_ozon": True,
                    }
                    with self._lock:
                        current = self._previews.get(key)
                        if current is preview:
                            current["confirmed_result"] = result
                            current["expires_at"] = self._monotonic() + self.TTL_SECONDS
                    return result

        current_case = self._read_case(preview["case_id"], scope)
        if not self._case_matches_preview(current_case, preview):
            with self._lock:
                if self._previews.get(key) is preview:
                    self._previews.pop(key, None)
            return self._result(
                "Предпросмотр устарел: дело изменилось. Отчёт не записан; сформируйте новый предпросмотр.",
                code="FIFO_REPORT_PREVIEW_STALE",
            )
        idempotency_key = "report_" + sha256(
            f"{preview['case_id']}\0{report.report_type.value}\0{report.file_sha256}".encode()
        ).hexdigest()[:40]
        saved = self.repository.append_report_evidence(
            case_id=preview["case_id"], report=report,
            expected_case_revision=preview["revision"],
            idempotency_key=idempotency_key,
        )
        if not isinstance(saved, dict) or saved.get("error") is not False:
            code = saved.get("code") if isinstance(saved, dict) else None
            with self._lock:
                if code == "FIFO_TRANSITION_REVISION_CONFLICT" and self._previews.get(key) is preview:
                    self._previews.pop(key, None)
            return self._result(
                "Не удалось добавить отчёт: дело успело измениться или хранилище недоступно. "
                "Текущая работа сохранена; проверьте дело и создайте новый предпросмотр.",
                code=code if isinstance(code, str) else "FIFO_REPORT_EVIDENCE_SAVE_FAILED",
            )
        result = {
            "error": False,
            "handled": True,
            "code": saved.get("code", "FIFO_TRANSITION_EVIDENCE_SAVED"),
            "message": "Отчёт добавлен как доказательство. Период из имени файла остаётся кандидатом до отдельного подтверждения.",
            "case_revision": saved.get("case_revision"),
            "read_only_ozon": True,
        }
        with self._lock:
            current = self._previews.get(key)
            if current is preview:
                current["confirmed_result"] = result
                current["expires_at"] = self._monotonic() + self.TTL_SECONDS
        return result

    def _read_case(self, case_id, scope):
        return self.repository.read_transition_case(
            case_id=case_id, store_id=scope.store_id,
            product_id=scope.product_id, offer_id=scope.offer_id, sku=scope.sku,
        )

    @staticmethod
    def _case_editable(result):
        return (
            isinstance(result, dict) and result.get("error") is False
            and result.get("state") in TelegramFifoCostReportImportService._EDITABLE_STATES
        )

    @classmethod
    def _case_matches_selection(cls, result, selection):
        return (
            cls._case_editable(result)
            and type(result.get("case_revision")) is int
            and result.get("case_revision") == selection.get("revision")
        )

    @classmethod
    def _case_matches_preview(cls, result, preview):
        return cls._case_matches_selection(result, preview)

    @staticmethod
    def _valid_parse_result(result):
        return (
            hasattr(result, "status") and hasattr(result, "report_evidence")
            and result.status in {"COMPLETE", "PARTIAL", "ERROR"}
            and isinstance(result.issue_codes, tuple)
        )

    def _identity(self, user_id, scope=None):
        tenant_value = str(get_current_tenant_user_id() or "").strip()
        owner, store = split_store_tenant_scope(tenant_value)
        user = str(user_id or "").strip()
        if not owner or not store or not user or owner != user:
            return None, None, self._error("FIFO_REPORT_OWNER_SCOPE_REQUIRED")
        if scope is not None and (
            not isinstance(scope, ScopeIdentity)
            or scope.owner_id != owner or scope.store_id != store
        ):
            return None, None, self._error("FIFO_REPORT_SCOPE_MISMATCH")
        return owner, tenant_value, None

    def _purge(self, now):
        for collection in (self._selections, self._previews):
            for key in [key for key, item in collection.items() if item["expires_at"] <= now]:
                collection.pop(key, None)
        for owner_scope, token in list(self._active.items()):
            if (owner_scope[0], owner_scope[1], token) not in self._selections:
                self._active.pop(owner_scope, None)

    @staticmethod
    def _trim(collection, maximum):
        while len(collection) > maximum:
            oldest = min(collection, key=lambda key: collection[key]["expires_at"])
            collection.pop(oldest, None)

    @staticmethod
    def _valid_token(token):
        return isinstance(token, str) and len(token) == 12 and all(
            char in "0123456789abcdef" for char in token
        )

    @staticmethod
    def _keyboard(*buttons):
        return {
            "error": False,
            "type": "inline_keyboard",
            "buttons": [{"text": text, "callback": callback} for text, callback in buttons],
        }

    @staticmethod
    def _result(message, *, code):
        return {
            "error": False,
            "handled": True,
            "code": code,
            "message": message,
            "read_only_ozon": True,
        }

    @staticmethod
    def _error(code):
        return {
            "error": True,
            "handled": True,
            "code": code,
            "message": "Не удалось обработать действие с отчётом. Дело не изменено.",
            "read_only_ozon": True,
        }
