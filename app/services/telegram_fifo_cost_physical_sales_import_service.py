"""Tenant-bound Telegram selection, preview, save and confirm flow for FIFO physical sales."""

from __future__ import annotations

from datetime import date
from hashlib import sha256
import re
from threading import RLock
from time import monotonic
from uuid import uuid4

from services.fifo_cost_physical_sales_evidence_service import (
    FifoCostPhysicalSalesEvidenceService,
)
from services.fifo_cost_report_import_worker_client import (
    FifoCostReportImportWorkerClient,
)
from services.fifo_cost_transition_contracts import ScopeIdentity
from services.fifo_cost_repository import FifoCostRepository
from services.ozon_account_repository import split_store_tenant_scope
from services.tenant_context import get_current_tenant_user_id


class TelegramFifoCostPhysicalSalesImportService:
    """Keep uploaded bytes transient until an owner saves the exact preview."""

    CALLBACK_PREFIX = "fifo_physical"
    TTL_SECONDS = 15 * 60
    MAX_SELECTIONS = 128
    MAX_PREVIEWS = 64
    MAX_PENDING_BYTES = 32 * 1024 * 1024
    MAX_FILE_BYTES = FifoCostReportImportWorkerClient.MAX_FILE_BYTES
    EDITABLE_STATES = frozenset({"DRAFT", "AWAITING_EVIDENCE"})

    def __init__(
        self, repository=None, worker=None, evidence_service=None, *,
        monotonic_clock=monotonic, now_provider=None,
    ):
        from datetime import datetime, timezone

        self.repository = repository or FifoCostRepository()
        self.worker = worker or FifoCostReportImportWorkerClient()
        self.evidence_service = evidence_service or FifoCostPhysicalSalesEvidenceService()
        self._monotonic = monotonic_clock
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._selections = {}
        self._active = {}
        self._previews = {}
        self._lock = RLock()

    def start_selection(
        self, *, user_id, case_id, scope, expected_case_revision,
    ):
        owner, tenant, error = self._identity(user_id, scope)
        if error:
            return error
        current = self._read_case(case_id, scope)
        if not self._case_matches(current, scope, expected_case_revision):
            return self._result(
                "FIFO-дело изменилось или недоступно. Откройте его заново; файл не отправляйте.",
                code="FIFO_PHYSICAL_SALES_CASE_STALE",
            )
        try:
            timezone_name = current["case"]["metadata"]["store_timezone"]
        except (KeyError, TypeError):
            return self._error("FIFO_TRANSITION_CASE_CORRUPT")
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
                "revision": expected_case_revision,
                "timezone": timezone_name,
                "period_from": None,
                "period_to": None,
                "token": token,
                "expires_at": now + self.TTL_SECONDS,
                "preview_token": None,
            }
            self._active[(owner, tenant)] = token
            self._trim(self._selections, self.MAX_SELECTIONS)
        return self._result(
            "Сначала укажите полный период, который покрывает CSV, включая дни без продаж. "
            "Формат: 2026-11-05 — 2026-11-09. После этого отправьте CSV в течение 15 минут. "
            "Даты из финансового отчёта не подставляйте как физические даты. "
            "Файл будет показан до сохранения и останется частичным свидетельством.",
            code="FIFO_PHYSICAL_SALES_UPLOAD_SELECTED",
        )

    def handle_period_text(
        self, *, user_id, text, expected_case_id, expected_scope,
        expected_case_revision,
    ):
        """Accept the owner-declared full coverage window, not the min/max row dates."""
        owner, tenant, error = self._identity(user_id, expected_scope)
        if error:
            return error
        now = self._monotonic()
        with self._lock:
            self._purge(now)
            selection = self._active_selection(owner, tenant)
            if selection is None:
                return self._result(
                    "Выбор CSV истёк. Откройте действие заново; текст не сохранён.",
                    code="FIFO_PHYSICAL_SALES_SELECTION_STALE",
                )
            if (
                selection.get("case_id") != expected_case_id
                or selection.get("scope") != expected_scope
                or selection.get("revision") != expected_case_revision
            ):
                return self._result(
                    "Период относится к другому или изменённому FIFO-делу. Дело не изменено.",
                    code="FIFO_PHYSICAL_SALES_SELECTION_STALE",
                )
        if selection.get("period_from") is not None:
            return self._result(
                "Полный период уже задан. Теперь отправьте выбранный CSV; границы покрытия не выводятся из строк.",
                code="FIFO_PHYSICAL_SALES_PERIOD_ALREADY_SET",
            )
        match = re.fullmatch(
            r"\s*(\d{4}-\d{2}-\d{2})\s*(?:—|–|\s+-\s+)\s*(\d{4}-\d{2}-\d{2})\s*",
            str(text or ""),
        )
        if match is None:
            return self._result(
                "Введите обе границы периода в формате YYYY-MM-DD — YYYY-MM-DD. "
                "Укажите также крайние дни, в которые не было продаж.",
                code="FIFO_PHYSICAL_SALES_PERIOD_INVALID",
            )
        period_from, period_to = match.groups()
        try:
            start = date.fromisoformat(period_from)
            end = date.fromisoformat(period_to)
            if start.isoformat() != period_from or end.isoformat() != period_to or end < start:
                raise ValueError
        except ValueError:
            return self._result(
                "Даты периода неверны. Используйте реальные календарные даты и порядок от начала к концу.",
                code="FIFO_PHYSICAL_SALES_PERIOD_INVALID",
            )
        current = self._read_case(expected_case_id, expected_scope)
        if not self._case_matches(current, expected_scope, expected_case_revision):
            return self._result(
                "FIFO-дело изменилось. Период не сохранён; откройте дело заново.",
                code="FIFO_PHYSICAL_SALES_SELECTION_STALE",
            )
        dispatch_date = (current.get("case") or {}).get("dispatch_date")
        if not isinstance(dispatch_date, str) or not period_from <= dispatch_date <= period_to:
            return self._result(
                "Период должен покрывать дату отправки из FIFO-дела. Период не сохранён.",
                code="FIFO_PHYSICAL_SALES_PERIOD_DOES_NOT_COVER_DISPATCH",
            )
        with self._lock:
            active = self._active_selection(owner, tenant)
            if active is None or active.get("token") != selection.get("token"):
                return self._result(
                    "Выбор CSV изменился. Период не сохранён; откройте действие заново.",
                    code="FIFO_PHYSICAL_SALES_SELECTION_STALE",
                )
            active["period_from"] = period_from
            active["period_to"] = period_to
            active["expires_at"] = self._monotonic() + self.TTL_SECONDS
        return self._result(
            f"Период покрытия сохранён: {period_from} — {period_to}. "
            "Теперь отправьте CSV. Дни без строк продаж останутся частью заданного периода.",
            code="FIFO_PHYSICAL_SALES_PERIOD_SET",
        )

    def has_active_selection(self, *, user_id):
        owner, tenant, error = self._identity(user_id)
        if error:
            return False
        now = self._monotonic()
        with self._lock:
            self._purge(now)
            token = self._active.get((owner, tenant))
            return (owner, tenant, token) in self._selections if token else False

    def preflight_document(
        self, *, user_id, filename, file_size, expected_case_id=None,
        expected_scope=None, expected_case_revision=None,
    ):
        owner, tenant, error = self._identity(user_id)
        if error:
            return error
        now = self._monotonic()
        with self._lock:
            self._purge(now)
            selection = self._active_selection(owner, tenant)
            if selection is None:
                return {"error": False, "selected": False, "read_only_ozon": True}
            preview = self._previews.get((owner, tenant, selection.get("preview_token")))
            if isinstance(preview, dict):
                return self._result(
                    "Предпросмотр уже создан. Используйте его кнопки; новое дело не изменено.",
                    code="FIFO_PHYSICAL_SALES_PREVIEW_ALREADY_PENDING",
                    selected=True,
                )
            if expected_case_id is not None and (
                selection.get("case_id") != expected_case_id
                or selection.get("scope") != expected_scope
                or selection.get("revision") != expected_case_revision
            ):
                return self._result(
                    "Выбор файла относится к другому или изменённому делу. Файл не загружен.",
                    code="FIFO_PHYSICAL_SALES_SELECTION_STALE",
                    selected=True,
                )
            if selection.get("period_from") is None or selection.get("period_to") is None:
                return self._result(
                    "Сначала укажите полный период покрытия CSV сообщением YYYY-MM-DD — YYYY-MM-DD.",
                    code="FIFO_PHYSICAL_SALES_PERIOD_REQUIRED",
                    selected=True,
                )
        if not isinstance(filename, str) or not filename.lower().endswith(".csv"):
            return self._result(
                "Для этого действия подходит только CSV физических продаж. "
                "Выбранное FIFO-дело сохранено; отправьте правильный файл.",
                code="FIFO_PHYSICAL_SALES_FORMAT_UNSUPPORTED",
                selected=True,
            )
        if type(file_size) is not int or file_size <= 0 or file_size > self.MAX_FILE_BYTES:
            return self._result(
                "CSV не должен превышать 10 МиБ и должен содержать данные. "
                "Файл не загружен; FIFO-дело не изменено.",
                code="FIFO_PHYSICAL_SALES_FILE_SIZE_INVALID",
                selected=True,
            )
        current = self._read_case(selection["case_id"], selection["scope"])
        if not self._case_matches(current, selection["scope"], selection["revision"]):
            return self._result(
                "Выбранное FIFO-дело изменилось. Файл не загружен; откройте дело заново.",
                code="FIFO_PHYSICAL_SALES_SELECTION_STALE",
                selected=True,
            )
        return {
            "error": False, "selected": True, "accepted": True,
            "read_only_ozon": True,
        }

    def handle_document(
        self, *, user_id, content, filename=None, expected_case_id=None,
        expected_scope=None, expected_case_revision=None,
    ):
        owner, tenant, error = self._identity(user_id)
        if error:
            return error
        preflight = self.preflight_document(
            user_id=user_id, filename=filename,
            file_size=(content.nbytes if isinstance(content, memoryview) else
                       len(content) if isinstance(content, (bytes, bytearray)) else None),
            expected_case_id=expected_case_id,
            expected_scope=expected_scope,
            expected_case_revision=expected_case_revision,
        )
        if preflight.get("error") or not preflight.get("selected"):
            if preflight.get("selected") is False:
                return {"error": False, "handled": False, "read_only_ozon": True}
            return preflight
        if isinstance(content, memoryview):
            raw = content.tobytes()
        elif isinstance(content, (bytes, bytearray)):
            raw = bytes(content)
        else:
            return self._error("FIFO_REPORT_PAYLOAD_INVALID")
        key, selection = self._active_selection_snapshot(owner, tenant)
        if selection is None:
            return self._result(
                "Выбор файла истёк. FIFO-дело не изменено; выберите действие заново.",
                code="FIFO_PHYSICAL_SALES_SELECTION_STALE",
            )
        if selection.get("preview_token"):
            return self._result(
                "Предпросмотр уже создан. Используйте его кнопки; новый файл не принят.",
                code="FIFO_PHYSICAL_SALES_PREVIEW_ALREADY_PENDING",
            )
        current = self._read_case(selection["case_id"], selection["scope"])
        if not self._case_matches(current, selection["scope"], selection["revision"]):
            return self._result(
                "Выбранное FIFO-дело изменилось. Файл не сохранён; откройте дело заново.",
                code="FIFO_PHYSICAL_SALES_SELECTION_STALE",
            )
        parsed = self.worker.parse_physical_sales(
            filename=filename, payload=raw, scope=selection["scope"],
        )
        if (
            not hasattr(parsed, "status") or parsed.status not in {"COMPLETE", "ERROR"}
            or not isinstance(getattr(parsed, "issue_codes", None), tuple)
        ):
            return self._error("FIFO_REPORT_WORKER_RESULT_INVALID")
        if parsed.status != "COMPLETE" or parsed.document is None:
            code = parsed.issue_codes[0] if parsed.issue_codes else "FIFO_PHYSICAL_SALES_PARSE_FAILED"
            return self._result(
                "Не удалось проверить CSV. Выбранное дело не изменено; можно исправить файл и повторить.",
                code=code,
            )
        document = parsed.document
        if selection.get("period_from") is None or selection.get("period_to") is None:
            return self._result(
                "Сначала укажите полный период покрытия CSV. Файл не сохранён.",
                code="FIFO_PHYSICAL_SALES_PERIOD_REQUIRED",
            )
        preview = self.evidence_service.preview_document(
            document=document,
            period_from=selection["period_from"],
            period_to=selection["period_to"],
            timezone_name=selection["timezone"],
        )
        if preview.get("error"):
            return preview
        token = uuid4().hex[:12]
        preview_key = (owner, tenant, token)
        now = self._monotonic()
        with self._lock:
            self._purge(now)
            if len(self._previews) >= self.MAX_PREVIEWS or self._pending_bytes() + len(raw) > self.MAX_PENDING_BYTES:
                return self._result(
                    "Сейчас уже обрабатываются другие документы. Повторите позже; дело не изменено.",
                    code="FIFO_PHYSICAL_SALES_PENDING_CAPACITY",
                )
            active = self._active_selection(owner, tenant)
            if active is None or active.get("token") != selection["token"]:
                return self._result(
                    "Выбранное действие изменилось. Файл не сохранён; повторите выбор.",
                    code="FIFO_PHYSICAL_SALES_SELECTION_STALE",
                )
            self._previews[preview_key] = {
                "user_id": owner,
                "tenant": tenant,
                "selection_key": key,
                "token": token,
                "case_id": selection["case_id"],
                "scope": selection["scope"],
                "revision": selection["revision"],
                "timezone": selection["timezone"],
                "document": document,
                "preview": preview,
                "payload": raw,
                "filename": filename,
                "expires_at": now + self.TTL_SECONDS,
                "saved": None,
            }
            selection["preview_token"] = token
            selection["expires_at"] = now + self.TTL_SECONDS
            save_callback = self._callback("save", token)
            cancel_callback = self._callback("cancel", token)
        return {
            "error": False,
            "handled": True,
            "code": "FIFO_PHYSICAL_SALES_PREVIEW_READY",
            "message": self._preview_text(preview),
            "keyboard": self._keyboard(
                ("💾 Сохранить документ", save_callback),
                ("Отменить предпросмотр", cancel_callback),
            ),
            "read_only_ozon": True,
        }

    def handle_callback(
        self, *, user_id, callback, expected_case_id, expected_scope,
        expected_case_revision,
    ):
        owner, tenant, error = self._identity(user_id, expected_scope)
        if error:
            return error
        parts = str(callback or "").split(":")
        if len(parts) != 3 or parts[0] != self.CALLBACK_PREFIX:
            return {"error": False, "handled": False, "read_only_ozon": True}
        action, token = parts[1:]
        if action not in {"save", "select", "cancel"} or not self._valid_token(token):
            return self._error("FIFO_PHYSICAL_SALES_CALLBACK_INVALID")
        now = self._monotonic()
        key = (owner, tenant, token)
        with self._lock:
            self._purge(now)
            preview = self._previews.get(key)
            if preview is None:
                return self._result(
                    "Предпросмотр истёк или уже закрыт. Сохранённые сведения другого дела не затронуты.",
                    code="FIFO_PHYSICAL_SALES_PREVIEW_STALE",
                )
            if (
                preview["case_id"] != expected_case_id
                or preview["scope"] != expected_scope
                or preview["revision"] != expected_case_revision
            ):
                return self._result(
                    "Кнопка относится к другому или уже изменённому делу. Оно не изменено.",
                    code="FIFO_PHYSICAL_SALES_PREVIEW_STALE",
                )
            if preview.get("confirmed_result") is not None:
                return dict(preview["confirmed_result"], replayed=True)
        if action == "cancel":
            was_saved = isinstance(preview.get("saved"), dict)
            self._remove_preview(key, preview)
            return self._result(
                (
                    "Подтверждение отменено. Уже сохранённый документ остаётся "
                    "неподтверждённым; FIFO не изменена."
                    if was_saved else
                    "Предпросмотр закрыт. Само FIFO-дело не изменено."
                ),
                code="FIFO_PHYSICAL_SALES_PREVIEW_CANCELLED",
            )
        if action == "save":
            return self._save_preview(owner, tenant, key, preview)
        if not isinstance(preview.get("saved"), dict):
            return self._result(
                "Сначала сохраните документ, затем подтвердите его сведения.",
                code="FIFO_PHYSICAL_SALES_DOCUMENT_NOT_SAVED",
            )
        return self._confirm_preview(owner, tenant, key, preview)

    def clear_selection(self, *, user_id):
        owner, tenant, error = self._identity(user_id)
        if error:
            return error
        with self._lock:
            token = self._active.pop((owner, tenant), None)
            if token is not None:
                key = (owner, tenant, token)
                selection = self._selections.pop(key, None)
                preview_token = selection.get("preview_token") if selection else None
                if preview_token:
                    self._previews.pop((owner, tenant, preview_token), None)
        return {"error": False, "read_only_ozon": True}

    def _save_preview(self, owner, tenant, key, preview):
        saved = preview.get("saved")
        if isinstance(saved, dict):
            return self._saved_result(preview, saved, replayed=True)
        current = self._read_case(preview["case_id"], preview["scope"])
        if not self._case_matches(current, preview["scope"], preview["revision"]):
            return self._result(
                "FIFO-дело изменилось. Документ не сохранён; откройте его заново.",
                code="FIFO_PHYSICAL_SALES_PREVIEW_STALE",
            )
        document = preview["document"]
        result = self.evidence_service.save_document(
            repository=self.repository,
            case_id=preview["case_id"],
            scope=preview["scope"],
            filename=preview["filename"],
            payload=preview["payload"],
            document=document,
            period_from=preview["preview"]["period_from"],
            period_to=preview["preview"]["period_to"],
            timezone_name=preview["timezone"],
            captured_at=self._now_provider().isoformat(),
            expected_case_revision=preview["revision"],
            idempotency_key=self._save_idempotency_key(preview),
        )
        if result.get("error"):
            return result
        current_after_save = self._read_case(preview["case_id"], preview["scope"])
        if not self._case_matches(current_after_save, preview["scope"]):
            return self._result(
                "Документ сохранён, но дело успело измениться. Повторно откройте его для подтверждения.",
                code="FIFO_PHYSICAL_SALES_PREVIEW_STALE",
            )
        saved = {
            "evidence_id": result["evidence_id"],
            "evidence_fingerprint": result["payload_fingerprint"],
            "document_fingerprint": document.document_fingerprint,
            "rows_fingerprint": document.row_references_fingerprint,
            "identity_fingerprint": document.identity_fingerprint,
            "row_count": document.row_count,
            "unit_count": document.unit_count,
            "case_revision": current_after_save["case_revision"],
        }
        with self._lock:
            current_preview = self._previews.get(key)
            if current_preview is not preview:
                return self._result(
                    "Документ сохранён. Предпросмотр истёк; откройте дело и проверьте сохранённые сведения.",
                    code="FIFO_PHYSICAL_SALES_PREVIEW_STALE",
                )
            preview["saved"] = saved
            preview["revision"] = saved["case_revision"]
            preview["payload"] = b""
            preview["document"] = None
            preview["expires_at"] = self._monotonic() + self.TTL_SECONDS
            selection = self._selections.get(preview["selection_key"])
            if selection is not None:
                selection["revision"] = saved["case_revision"]
                selection["expires_at"] = preview["expires_at"]
        return self._saved_result(preview, saved)

    def _confirm_preview(self, owner, tenant, key, preview):
        saved = preview["saved"]
        selection = preview.get("version_selection")
        if not isinstance(selection, tuple):
            return self._saved_result(preview, saved, replayed=True)
        current = self._read_case(preview["case_id"], preview["scope"])
        if not self._case_matches(current, preview["scope"], saved["case_revision"]):
            return self._result(
                "FIFO-дело изменилось. Документ не подтверждён; откройте дело заново.",
                code="FIFO_PHYSICAL_SALES_PREVIEW_STALE",
            )
        result = self.evidence_service.confirm_document(
            repository=self.repository,
            case_id=preview["case_id"],
            scope=preview["scope"],
            evidence_id=saved["evidence_id"],
            expected_evidence_fingerprint=saved["evidence_fingerprint"],
            expected_case_revision=saved["case_revision"],
            expected_document_fingerprint=saved["document_fingerprint"],
            expected_rows_fingerprint=saved["rows_fingerprint"],
            expected_identity_fingerprint=saved["identity_fingerprint"],
            expected_row_count=saved["row_count"],
            period_from=preview["preview"]["period_from"],
            period_to=preview["preview"]["period_to"],
            timezone_name=preview["timezone"],
            semantics="PHYSICAL_OUTFLOW",
            idempotency_key=self._confirm_idempotency_key(
                preview, saved, selection,
            ),
            select_as_current=True,
            expected_superseded_evidence_fingerprints=selection,
        )
        if result.get("error"):
            return result
        response = self._result(
            f"Подтверждены сведения физического CSV: {saved['row_count']} строк, "
            f"{saved['unit_count']} единиц, даты {preview['preview']['period_from']} — "
            f"{preview['preview']['period_to']}. Этот файл выбран текущей версией; "
            f"{len(selection)} ранее подтверждённых версий оставлены в истории. "
            "Документ остаётся частичным: "
            "полнота всех продаж и движений этим подтверждением не доказана.",
            code="FIFO_PHYSICAL_SALES_CONFIRMED",
        )
        with self._lock:
            if self._previews.get(key) is preview:
                preview["confirmed_result"] = response
                preview["revision"] = result.get("case_revision")
                preview["payload"] = b""
                preview["document"] = None
                preview["expires_at"] = self._monotonic() + self.TTL_SECONDS
                selection = self._selections.pop(preview["selection_key"], None)
                owner_scope = (owner, tenant)
                if selection is not None and self._active.get(owner_scope) == selection["token"]:
                    self._active.pop(owner_scope, None)
        return response

    def _saved_result(self, preview, saved, *, replayed=False):
        listed = self.evidence_service.list_confirmed_documents(
            repository=self.repository, case_id=preview["case_id"],
            scope=preview["scope"],
        )
        if listed.get("error"):
            retry_callback = self._callback("save", preview["token"])
            return self._result(
                "CSV сохранён, но не удалось перечитать предыдущие подтверждённые версии. "
                "Ничего не выбрано текущим; повторите проверку.",
                code="FIFO_PHYSICAL_SALES_VERSION_SELECTION_UNAVAILABLE",
                selected=True,
            ) | {"keyboard": self._keyboard(
                ("Повторить проверку", retry_callback),
                ("Отменить подтверждение", self._callback("cancel", preview["token"])),
            )}
        superseded = tuple(sorted(
            item["payload_fingerprint"]
            for item in listed["documents"]
            if item["evidence_id"] != saved["evidence_id"]
        ))
        preview["version_selection"] = superseded
        previous = [
            item for item in listed["documents"]
            if item["evidence_id"] != saved["evidence_id"]
        ]
        selection_callback = self._callback("select", preview["token"])
        previous_summary = ""
        if previous:
            visible = previous[:5]
            previous_summary = (
                "\nРанее подтверждённые версии, которые будут заменены выбором этого файла: "
                f"{len(previous)}.\n"
                + "\n".join(
                    f"• {item['preview']['period_from']} — {item['preview']['period_to']}: "
                    f"{item['preview']['row_count']} строк, {item['preview']['unit_count']} шт."
                    for item in visible
                )
                + ("\n• Остальные версии также останутся в истории." if len(previous) > len(visible) else "")
            )
        message = (
            f"Документ сохранён: {saved['row_count']} строк, {saved['unit_count']} единиц, "
            f"покрытие {preview['preview']['period_from']} — {preview['preview']['period_to']}.\n"
            "Отдельно подтвердите физический смысл строк и выберите этот CSV текущей версией. "
            "При замене предыдущие файлы сохранятся в истории."
            f"{previous_summary}\n"
            "Подтверждение не доказывает полноту продаж и движений."
        )
        return {
            "error": False,
            "handled": True,
            "code": "FIFO_PHYSICAL_SALES_DOCUMENT_SAVED",
            "message": message,
            "keyboard": self._keyboard(
                (
                    "✅ Подтвердить и выбрать текущим"
                    if not previous else
                    f"✅ Заменить {len(previous)} подтвержд. верс. и выбрать текущим",
                    selection_callback,
                ),
                ("Отказаться от подтверждения", self._callback("cancel", preview["token"])),
            ),
            "replayed": replayed,
            "read_only_ozon": True,
        }

    @staticmethod
    def _preview_text(preview):
        return (
            "Предпросмотр физических продаж\n"
            f"Строк: {preview['row_count']} · единиц: {preview['unit_count']}\n"
            f"Период покрытия по вашему указанию: {preview['period_from']} — {preview['period_to']}\n"
            f"Даты в строках CSV: {preview['row_date_from']} — {preview['row_date_to']}\n"
            "Источник: файл, предоставленный владельцем; тип свидетельства — PARTIAL.\n"
            "Подтверждение означает, что вы проверили строки, физические даты и количества. "
            "Оно не доказывает, что документ содержит все продажи, возвраты и иные движения. "
            "Финансовые даты нельзя выдавать за физические даты."
        )

    def _active_selection(self, owner, tenant):
        token = self._active.get((owner, tenant))
        return self._selections.get((owner, tenant, token)) if token else None

    def _active_selection_snapshot(self, owner, tenant):
        with self._lock:
            selection = self._active_selection(owner, tenant)
            return ((owner, tenant, selection["token"]), dict(selection)) if selection else (None, None)

    def _remove_preview(self, key, preview):
        with self._lock:
            if self._previews.get(key) is not preview:
                return
            self._previews.pop(key, None)
            selection_key = preview["selection_key"]
            selection = self._selections.get(selection_key)
            if selection is not None and selection.get("preview_token") == preview["token"]:
                self._selections.pop(selection_key, None)
                owner_scope = (selection["user_id"], selection["tenant"])
                if self._active.get(owner_scope) == selection["token"]:
                    self._active.pop(owner_scope, None)

    def _purge(self, now):
        for collection in (self._selections, self._previews):
            for key in [key for key, item in collection.items() if item["expires_at"] <= now]:
                collection.pop(key, None)
        for owner_scope, token in list(self._active.items()):
            if (owner_scope[0], owner_scope[1], token) not in self._selections:
                self._active.pop(owner_scope, None)

    def _pending_bytes(self):
        return sum(
            len(item.get("payload", b"")) for item in self._previews.values()
        )

    @staticmethod
    def _trim(collection, maximum):
        while len(collection) > maximum:
            oldest = min(collection, key=lambda key: collection[key]["expires_at"])
            collection.pop(oldest, None)

    @staticmethod
    def _case_matches(result, scope, revision=None):
        if (
            not isinstance(result, dict) or result.get("error") is not False
            or result.get("state") not in TelegramFifoCostPhysicalSalesImportService.EDITABLE_STATES
        ):
            return False
        if revision is not None and (
            type(result.get("case_revision")) is not int
            or result["case_revision"] != revision
        ):
            return False
        case = result.get("case")
        metadata = case.get("metadata") if isinstance(case, dict) else None
        stored_scope = metadata.get("scope") if isinstance(metadata, dict) else None
        return isinstance(stored_scope, dict) and stored_scope == {
            "store_id": scope.store_id,
            "product_id": scope.product_id,
            "offer_id": scope.offer_id,
            "sku": scope.sku,
        }

    def _read_case(self, case_id, scope):
        return self.repository.read_transition_case(
            case_id=case_id, store_id=scope.store_id,
            product_id=scope.product_id, offer_id=scope.offer_id, sku=scope.sku,
        )

    @staticmethod
    def _identity(user_id, scope=None):
        tenant_value = str(get_current_tenant_user_id() or "").strip()
        owner, store = split_store_tenant_scope(tenant_value)
        user = str(user_id or "").strip()
        if not owner or not store or not user or owner != user:
            return None, None, TelegramFifoCostPhysicalSalesImportService._error(
                "FIFO_PHYSICAL_SALES_OWNER_SCOPE_REQUIRED",
            )
        if scope is not None and (
            not isinstance(scope, ScopeIdentity)
            or scope.owner_id != owner or scope.store_id != store
        ):
            return None, None, TelegramFifoCostPhysicalSalesImportService._error(
                "FIFO_TRANSITION_SCOPE_MISMATCH",
            )
        return owner, tenant_value, None

    @staticmethod
    def _save_idempotency_key(preview):
        digest = sha256(
            "\0".join((
                preview["case_id"], preview["scope"].store_id,
                preview["scope"].product_id or "", preview["scope"].offer_id or "",
                preview["scope"].sku, preview["document"].document_fingerprint,
                preview["preview"]["period_from"], preview["preview"]["period_to"],
            )).encode("utf-8")
        ).hexdigest()
        return "physical-sales-" + digest

    @staticmethod
    def _confirm_idempotency_key(preview, saved, superseded=()):
        digest = sha256(
            "\0".join((
                saved["evidence_fingerprint"], saved["document_fingerprint"],
                saved["rows_fingerprint"], preview["preview"]["period_from"],
                preview["preview"]["period_to"], preview["timezone"],
                str(saved["case_revision"]),
                *superseded,
            )).encode("utf-8")
        ).hexdigest()
        return "physconf-" + digest

    @classmethod
    def _callback(cls, action, token):
        return f"{cls.CALLBACK_PREFIX}:{action}:{token}"

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
    def _result(message, *, code, selected=None):
        result = {
            "error": False,
            "handled": True,
            "code": code,
            "message": message,
            "read_only_ozon": True,
        }
        if selected is not None:
            result["selected"] = selected
        if selected is True:
            result["accepted"] = False
        return result

    @staticmethod
    def _error(code):
        return {
            "error": True,
            "handled": True,
            "code": code,
            "message": "Не удалось обработать подтверждение физических продаж. FIFO-дело не изменено.",
            "read_only_ozon": True,
        }
