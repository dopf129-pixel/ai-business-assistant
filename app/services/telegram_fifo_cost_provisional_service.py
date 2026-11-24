"""Owner-only Telegram flow for non-authoritative FIFO summary scenarios."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import re
from time import monotonic
from uuid import uuid4

from services.fifo_cost_provisional_fbo_csv_import_service import (
    ProvisionalFboParseResult,
)
from services.fifo_cost_provisional_movements_import_service import (
    ProvisionalMovementsParseResult,
)
from services.fifo_cost_provisional_contracts import (
    ProvisionalRangeAssumptions,
    ProvisionalStatus,
    ProvisionalSummaryRequest,
)
from services.fifo_cost_provisional_timeline_service import (
    FifoCostProvisionalTimelineService,
)
from services.fifo_cost_transition_contracts import ScopeIdentity
from services.fifo_cost_report_import_worker_client import FifoCostReportImportWorkerClient


class TelegramFifoCostProvisionalService:
    """Keep provisional inputs in the existing short-lived Telegram session.

    This service never writes transition cases, FIFO layers, Period Profit data,
    or the saved-estimate ledger. Durable estimates are introduced separately.
    """

    PAGE_SIZE = 8
    FBO_UPLOAD_TTL_SECONDS = 15 * 60
    FBO_MAX_FILE_BYTES = FifoCostReportImportWorkerClient.MAX_FILE_BYTES
    MOVEMENTS_UPLOAD_TTL_SECONDS = 15 * 60

    def __init__(
        self, *, evidence_reader, summary_service, fbo_worker=None,
        timeline_service=None, monotonic_clock=monotonic,
    ):
        self.evidence_reader = evidence_reader
        self.summary_service = summary_service
        self.fbo_worker = fbo_worker or FifoCostReportImportWorkerClient()
        self.timeline_service = timeline_service or FifoCostProvisionalTimelineService()
        self._monotonic = monotonic_clock

    def start(self, runtime, owner, session):
        if runtime.physical_sales_import_service is not None:
            runtime.physical_sales_import_service.clear_selection(user_id=owner)
        session.pop("provisional_flow", None)
        session["provisional_flow"] = {
            "snapshot_fingerprint": None,
            "movement_fingerprint": None,
            "opening_all_old": None,
            "all_period_supply_receipts_new": None,
            "closing_old_min": None,
            "closing_old_max": None,
            "result": None,
            "timeline_result": None,
            "movement_document": None,
            "movements_upload": None,
            "timeline_coverage_confirmed": None,
            "snapshot_page": 0,
            "movement_page": 0,
        }
        session.pop("step", None)
        session["flow_revision"] = session.get("flow_revision", 0) + 1
        return self.show(runtime, owner, session)

    def handle_text(self, runtime, owner, session, text):
        flow = session.get("provisional_flow")
        if not isinstance(flow, dict):
            return runtime._stale()
        value = str(text or "").strip()
        step = session.get("step")
        if step == "provisional_fbo_period":
            return self._set_fbo_period(runtime, owner, session, value)
        if step == "provisional_close_exact":
            parsed = self._parse_units(value)
            if parsed is None:
                return runtime._result("Введите целое неотрицательное число единиц. Предыдущие сведения не изменены.")
            flow["closing_old_min"] = flow["closing_old_max"] = parsed
        elif step == "provisional_close_range":
            pieces = value.split("-")
            if len(pieces) != 2:
                return runtime._result("Введите границы диапазона в формате 10-25. Предыдущие сведения не изменены.")
            low, high = (self._parse_units(piece.strip()) for piece in pieces)
            if low is None or high is None or low > high:
                return runtime._result("Диапазон должен содержать целые числа: минимум не больше максимума. Данные не изменены.")
            flow["closing_old_min"], flow["closing_old_max"] = low, high
        else:
            return runtime._stale()
        session.pop("step", None)
        flow["result"] = None
        self._advance(runtime, session)
        return self.show(runtime, owner, session)

    def handle_callback(self, runtime, owner, session, ticket, action):
        if action == "provisional_start":
            return self.start(runtime, owner, session)
        flow = session.get("provisional_flow")
        if not isinstance(flow, dict):
            return runtime._stale()
        if action == "provisional_fbo_upload":
            return self._start_fbo_upload(runtime, owner, session, flow)
        if action in {"provisional_fbo_confirm", "provisional_fbo_cancel"}:
            return self._resolve_fbo_preview(
                runtime, owner, session, ticket, flow, action,
            )
        if action == "provisional_movements_upload":
            return self._start_movements_upload(runtime, owner, session, flow)
        if action in {"provisional_movements_confirm", "provisional_movements_cancel"}:
            return self._resolve_movements_preview(
                runtime, owner, session, ticket, flow, action,
            )
        if action == "provisional_back":
            session.pop("provisional_flow", None)
            session.pop("step", None)
            self._advance(runtime, session)
            return runtime._show_summary(owner)
        if action == "provisional_snapshot":
            return self._select_report(runtime, owner, session, ticket, flow, "snapshot")
        if action == "provisional_movement":
            return self._select_report(runtime, owner, session, ticket, flow, "movement")
        if action == "provisional_opening_yes":
            flow["opening_all_old"] = True
        elif action == "provisional_opening_no":
            flow["opening_all_old"] = False
        elif action == "provisional_receipts_yes":
            flow["all_period_supply_receipts_new"] = True
        elif action == "provisional_receipts_no":
            flow["all_period_supply_receipts_new"] = False
        elif action == "provisional_closing_unknown":
            flow["closing_old_min"] = flow["closing_old_max"] = None
        elif action == "provisional_closing_exact":
            session["step"] = "provisional_close_exact"
            self._advance(runtime, session)
            return runtime._result("Введите предполагаемое точное количество старых единиц в конечном остатке. Это гипотеза для сценария.")
        elif action == "provisional_closing_range":
            session["step"] = "provisional_close_range"
            self._advance(runtime, session)
            return runtime._result("Введите диапазон старого остатка в формате минимум-максимум, например 10-25. Это сценарная гипотеза.")
        elif action == "provisional_calculate":
            return self._calculate(runtime, owner, session, flow)
        elif action == "provisional_timeline_calculate":
            return self._calculate_timeline(runtime, owner, session, flow)
        elif action == "provisional_timeline_coverage_yes":
            flow["timeline_coverage_confirmed"] = True
        elif action == "provisional_timeline_coverage_no":
            flow["timeline_coverage_confirmed"] = False
        elif action == "provisional_upload":
            session.pop("provisional_flow", None)
            session.pop("step", None)
            self._advance(runtime, session)
            return runtime._start_report_import(owner, session, "report_turnover")
        elif action == "provisional_page":
            page = ticket.get("page")
            page_kind = ticket.get("page_kind")
            if type(page) is not int or page < 0 or page_kind not in {"snapshot", "movement"}:
                return runtime._stale()
            flow[f"{page_kind}_page"] = page
        else:
            return runtime._stale()
        flow["result"] = None
        flow["timeline_result"] = None
        self._advance(runtime, session)
        return self.show(runtime, owner, session)

    def show(self, runtime, owner, session):
        flow = session.get("provisional_flow")
        if not isinstance(flow, dict):
            return runtime._stale()
        candidates = self._reports(runtime, session)
        if candidates is None:
            return runtime._result(
                "Не удалось безопасно прочитать сохранённые ведомости. Предварительный расчёт не выполнен.",
                keyboard=runtime._keyboard([{
                    "text": "⬅️ К карточке партии",
                    "callback": runtime._issue_ticket(owner, session, "provisional_back"),
                }]),
            )
        snapshots = [item for item in candidates if item["period_from"] == item["period_to"]]
        snapshot = self._find(candidates, flow.get("snapshot_fingerprint"))
        movement = self._find(candidates, flow.get("movement_fingerprint"))
        buttons = []
        lines = [
            "🧪 Предварительная оценка FIFO — только сценарий",
            f"SKU {session['identity']['sku']} · {session['display_name']}",
            "История FIFO и прибыль магазина не меняются.",
            "",
        ]
        case = session.get("case")
        if not isinstance(case, dict) or case.get("old_unit_cost_rub") is None or case.get("new_unit_cost_rub") is None:
            lines.append("Для денежного диапазона сначала укажите в карточке старую и новую себестоимость; текущие ставки не определены.")
        else:
            lines.append(f"Ставки из карточки партии: старая {case['old_unit_cost_rub']} ₽, новая {case['new_unit_cost_rub']} ₽.")
        timezone = (case.get("metadata", {}).get("store_timezone")
                    if isinstance(case, dict) and isinstance(case.get("metadata"), dict)
                    else "неизвестен")
        lines.append(f"Даты трактуются в часовом поясе магазина: {timezone}.")
        lines.extend([
            "",
            "1) Выберите подтверждённый снимок оборотной ведомости за один день D:",
        ])
        lines.append(self._report_label(snapshot) if snapshot else "Снимок не выбран.")
        snapshot_page = min(flow.get("snapshot_page", 0), max(0, (len(snapshots) - 1) // self.PAGE_SIZE))
        flow["snapshot_page"] = snapshot_page
        snapshot_start = snapshot_page * self.PAGE_SIZE
        for item in snapshots[snapshot_start:snapshot_start + self.PAGE_SIZE]:
            buttons.append({"text": self._report_choice_label(item, "snapshot"), "callback": runtime._issue_ticket(
                owner, session, "provisional_snapshot", fingerprint=item["file_fingerprint"],
            )})
        snapshot_pages = max(1, (len(snapshots) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        if snapshot_page > 0:
            buttons.append({"text": "⬅️ Снимки", "callback": runtime._issue_ticket(
                owner, session, "provisional_page", page_kind="snapshot", page=snapshot_page - 1,
            )})
        if snapshot_page + 1 < snapshot_pages:
            buttons.append({"text": "Ещё снимки ➡️", "callback": runtime._issue_ticket(
                owner, session, "provisional_page", page_kind="snapshot", page=snapshot_page + 1,
            )})
        if snapshot:
            lines.extend(["", "2) Выберите ведомость движений с началом на следующий день:"])
            next_day = self._next_day(snapshot["period_to"])
            eligible = [item for item in candidates if item["period_from"] == next_day and item["period_to"] >= next_day]
            lines.append(self._report_label(movement) if movement else "Ведомость движений не выбрана.")
            movement_page = min(flow.get("movement_page", 0), max(0, (len(eligible) - 1) // self.PAGE_SIZE))
            flow["movement_page"] = movement_page
            movement_start = movement_page * self.PAGE_SIZE
            for item in eligible[movement_start:movement_start + self.PAGE_SIZE]:
                buttons.append({"text": self._report_choice_label(item, "movement"),
                                "callback": runtime._issue_ticket(owner, session, "provisional_movement", fingerprint=item["file_fingerprint"])})
            movement_pages = max(1, (len(eligible) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
            if movement_page > 0:
                buttons.append({"text": "⬅️ Ведомости", "callback": runtime._issue_ticket(
                    owner, session, "provisional_page", page_kind="movement", page=movement_page - 1,
                )})
            if movement_page + 1 < movement_pages:
                buttons.append({"text": "Ещё ведомости ➡️", "callback": runtime._issue_ticket(
                    owner, session, "provisional_page", page_kind="movement", page=movement_page + 1,
                )})
            if not eligible:
                lines.append(f"Нужен полный отчёт с подтверждённым периодом от {next_day} включительно.")
        lines.extend(["", "3) Допущение: весь остаток снимка D — старая партия."])
        lines.append(self._yes_no_label(flow.get("opening_all_old")))
        buttons.extend([
            {"text": "Подтверждаю: весь остаток старый", "callback": runtime._issue_ticket(owner, session, "provisional_opening_yes")},
            {"text": "Нет / не могу подтвердить", "callback": runtime._issue_ticket(owner, session, "provisional_opening_no")},
        ])
        lines.extend(["", "4) Допущение: весь приход из поставок L в окне относится к новой партии."])
        lines.append(self._yes_no_label(flow.get("all_period_supply_receipts_new")))
        buttons.extend([
            {"text": "Подтверждаю: приход новой партии", "callback": runtime._issue_ticket(owner, session, "provisional_receipts_yes")},
            {"text": "Нет / есть старый приход", "callback": runtime._issue_ticket(owner, session, "provisional_receipts_no")},
        ])
        close = flow.get("closing_old_min")
        if close is None:
            lines.extend(["", "Конечный остаток старой партии: не установлен. По умолчанию будет широкая граница."])
        elif close == flow.get("closing_old_max"):
            lines.extend(["", f"Сценарное предположение об остатке старой партии: {close} шт."])
        else:
            lines.extend(["", f"Сценарный диапазон старого остатка: {close}–{flow['closing_old_max']} шт."])
        buttons.extend([
            {"text": "Остаток неизвестен (широкий диапазон)", "callback": runtime._issue_ticket(owner, session, "provisional_closing_unknown")},
            {"text": "Задать одно число", "callback": runtime._issue_ticket(owner, session, "provisional_closing_exact")},
            {"text": "Задать диапазон", "callback": runtime._issue_ticket(owner, session, "provisional_closing_range")},
        ])
        costs_ready = (
            isinstance(case, dict)
            and case.get("old_unit_cost_rub") is not None
            and case.get("new_unit_cost_rub") is not None
        )
        if snapshot and movement and costs_ready:
            buttons.append({"text": "Рассчитать диапазон", "callback": runtime._issue_ticket(owner, session, "provisional_calculate")})
        self._append_fbo_status(runtime, owner, session, flow, lines, buttons)
        self._append_movements_status(runtime, owner, session, flow, lines, buttons)
        if snapshot and movement:
            buttons.append({
                "text": "🧾 Добавить CSV отправлений FBO",
                "callback": runtime._issue_ticket(owner, session, "provisional_fbo_upload"),
            })
            buttons.append({
                "text": "📋 Добавить CSV прочих движений",
                "callback": runtime._issue_ticket(owner, session, "provisional_movements_upload"),
            })
            coverage = flow.get("timeline_coverage_confirmed")
            lines.extend([
                "",
                "Подтвердите, что источники полностью покрывают выкупы, отгрузки, приёмки, отмены, "
                "возвраты, удержания/освобождения, списания и изменения доступности за окно; "
                "пропущенных событий нет. Отсутствующие группы должны быть нулевыми.",
            ])
            lines.append(self._yes_no_label(coverage))
            buttons.extend([
                {"text": "Подтверждаю полноту источников", "callback": runtime._issue_ticket(
                    owner, session, "provisional_timeline_coverage_yes",
                )},
                {"text": "Не могу подтвердить полноту", "callback": runtime._issue_ticket(
                    owner, session, "provisional_timeline_coverage_no",
                )},
                {"text": "Рассчитать хронологическую модель", "callback": runtime._issue_ticket(
                    owner, session, "provisional_timeline_calculate",
                )},
            ])
        buttons.extend([
            {"text": "📄 Загрузить оборотную ведомость", "callback": runtime._issue_ticket(owner, session, "provisional_upload")},
            {"text": "⬅️ К карточке партии", "callback": runtime._issue_ticket(owner, session, "provisional_back")},
        ])
        if flow.get("result") is not None:
            lines.extend(["", self._format_result(flow["result"])])
        if flow.get("timeline_result") is not None:
            lines.extend(["", self._format_timeline_result(flow["timeline_result"], flow.get("result"))])
        return runtime._result("\n".join(lines), keyboard=runtime._keyboard(buttons))

    def _start_fbo_upload(self, runtime, owner, session, flow):
        reports = self._reports(runtime, session)
        movement = self._find(reports or (), flow.get("movement_fingerprint"))
        snapshot = self._find(reports or (), flow.get("snapshot_fingerprint"))
        if reports is None or movement is None or snapshot is None:
            return runtime._result(
                "Сначала выберите подтверждённый снимок и соседнюю ведомость движений. FBO CSV не выбран.",
                code="FIFO_PROVISIONAL_FBO_REPORTS_REQUIRED",
            )
        current = runtime._read_case(session["case_id"], session["identity"])
        if not runtime._case_matches(current, session["identity"], session["case_revision"]):
            return runtime._result(
                "FIFO-дело изменилось. Откройте его заново перед добавлением CSV.",
                code="FIFO_PROVISIONAL_CASE_STALE",
            )
        case = session.get("case")
        try:
            timezone_name = case["metadata"]["store_timezone"]
            scope_data = case["metadata"]["scope"]
            scope = ScopeIdentity(
                owner_id=scope_data["owner_id"],
                store_id=session["identity"]["store_id"],
                product_id=session["identity"].get("product_id"),
                offer_id=session["identity"].get("offer_id"),
                sku=session["identity"]["sku"],
            )
        except (KeyError, TypeError, ValueError):
            return runtime._result(
                "Не удалось проверить магазин и SKU. CSV не выбран.",
                code="FIFO_PROVISIONAL_SCOPE_INVALID",
            )
        if runtime.physical_sales_import_service is not None:
            runtime.physical_sales_import_service.clear_selection(user_id=owner)
        flow["timeline_coverage_confirmed"] = None
        flow["timeline_result"] = None
        upload = {
            "token": uuid4().hex,
            "case_id": session["case_id"],
            "case_revision": session["case_revision"],
            "identity": dict(session["identity"]),
            "scope": scope,
            "timezone_name": timezone_name,
            "movement_fingerprint": movement["file_fingerprint"],
            "movement_from": movement["period_from"],
            "movement_to": movement["period_to"],
            "snapshot_to": snapshot["period_to"],
            "period_from": None,
            "period_to": None,
            "preview": None,
            "accepted": None,
            "expires_at": self._monotonic() + self.FBO_UPLOAD_TTL_SECONDS,
        }
        flow["fbo_upload"] = upload
        session["step"] = "provisional_fbo_period"
        self._advance(runtime, session)
        return runtime._result(
            "Укажите период, который полностью покрывает CSV отправлений, включая дни без строк. "
            f"Он должен включать период ведомости движений {movement['period_from']} — {movement['period_to']}. "
            "Формат: YYYY-MM-DD — YYYY-MM-DD. После подтверждения пришлите CSV в течение 15 минут. "
            "Номер отправления и дополнительные колонки не будут показаны или сохранены.",
            keyboard=runtime._keyboard([{
                "text": "Отмена",
                "callback": runtime._issue_ticket(
                    owner, session, "provisional_fbo_cancel",
                    fbo_token=upload["token"],
                ),
            }]),
        )

    def _set_fbo_period(self, runtime, owner, session, text):
        flow = session.get("provisional_flow")
        upload = flow.get("fbo_upload") if isinstance(flow, dict) else None
        if not self._upload_matches_session(runtime, session, upload):
            session.pop("step", None)
            if isinstance(flow, dict):
                flow.pop("fbo_upload", None)
            self._advance(runtime, session)
            return runtime._result(
                "Выбор FBO CSV истёк или относится к другому делу. Выберите его заново.",
                code="FIFO_PROVISIONAL_FBO_SELECTION_STALE",
            )
        match = re.fullmatch(
            r"\s*(\d{4}-\d{2}-\d{2})\s*(?:—|–|\s+-\s+)\s*(\d{4}-\d{2}-\d{2})\s*",
            str(text or ""),
        )
        if match is None:
            return runtime._result(
                "Введите обе границы полного периода CSV: YYYY-MM-DD — YYYY-MM-DD.",
                code="FIFO_PROVISIONAL_FBO_PERIOD_INVALID",
            )
        start_text, end_text = match.groups()
        try:
            start = date.fromisoformat(start_text)
            end = date.fromisoformat(end_text)
        except ValueError:
            return runtime._result(
                "Даты периода CSV неверны. Период не сохранён.",
                code="FIFO_PROVISIONAL_FBO_PERIOD_INVALID",
            )
        if (
            start.isoformat() != start_text or end.isoformat() != end_text
            or end < start
            or start_text > upload["movement_from"]
            or end_text < upload["movement_to"]
        ):
            return runtime._result(
                "Подтверждённый период должен быть непрерывным и покрывать весь период ведомости движений. "
                "Период не сохранён.",
                code="FIFO_PROVISIONAL_FBO_PERIOD_INVALID",
            )
        upload["period_from"], upload["period_to"] = start_text, end_text
        upload["expires_at"] = self._monotonic() + self.FBO_UPLOAD_TTL_SECONDS
        session["step"] = "provisional_fbo_file"
        self._advance(runtime, session)
        return runtime._result(
            f"Период полного покрытия CSV подтверждён: {start_text} — {end_text}. "
            "Теперь отправьте CSV. Строки вне выбранного SKU будут отброшены.",
            code="FIFO_PROVISIONAL_FBO_PERIOD_SET",
        )

    def has_fbo_document_selection(self, runtime, owner, session):
        flow = session.get("provisional_flow") if isinstance(session, dict) else None
        upload = flow.get("fbo_upload") if isinstance(flow, dict) else None
        return (
            isinstance(upload, dict)
            and session.get("step") in {
                "provisional_fbo_period", "provisional_fbo_file", "provisional_fbo_preview",
            }
        )

    def clear_fbo_upload(self, session):
        if not isinstance(session, dict):
            return
        flow = session.get("provisional_flow")
        if isinstance(flow, dict):
            flow.pop("fbo_upload", None)
        if session.get("step") in {
            "provisional_fbo_period", "provisional_fbo_file", "provisional_fbo_preview",
        }:
            session.pop("step", None)

    def preflight_fbo_document(self, runtime, owner, session, filename, file_size):
        if not self.has_fbo_document_selection(runtime, owner, session):
            return {"error": False, "selected": False, "read_only_ozon": True}
        flow = session["provisional_flow"]
        upload = flow["fbo_upload"]
        if not self._upload_matches_session(runtime, session, upload):
            return self._preflight_error(
                "FIFO_PROVISIONAL_FBO_SELECTION_STALE",
                "Выбор FBO CSV истёк или изменился. Файл не загружен; выберите его заново.",
            )
        if session.get("step") != "provisional_fbo_file":
            code = (
                "FIFO_PROVISIONAL_FBO_PREVIEW_PENDING"
                if session.get("step") == "provisional_fbo_preview"
                else "FIFO_PROVISIONAL_FBO_PERIOD_REQUIRED"
            )
            return self._preflight_error(
                code,
                "Сначала завершите ввод полного периода или подтвердите/отмените предпросмотр. Файл не загружен.",
            )
        if not isinstance(filename, str) or not filename.lower().endswith(".csv"):
            return self._preflight_error(
                "FIFO_PROVISIONAL_FBO_FORMAT_UNSUPPORTED",
                "Выбрано действие для FBO CSV. Пришлите CSV; выбранное дело не изменено.",
            )
        if type(file_size) is not int or file_size <= 0 or file_size > self.FBO_MAX_FILE_BYTES:
            return self._preflight_error(
                "FIFO_PROVISIONAL_FBO_FILE_SIZE_INVALID",
                "CSV должен быть непустым и не превышать 10 МиБ. Файл не загружен.",
            )
        if upload.get("preview") is not None or upload.get("accepted") is not None:
            return self._preflight_error(
                "FIFO_PROVISIONAL_FBO_PREVIEW_PENDING",
                "Сначала подтвердите или отмените предыдущий предпросмотр.",
            )
        return {
            "error": False, "selected": True, "accepted": True,
            "read_only_ozon": True,
        }

    def handle_fbo_document(self, runtime, owner, session, content, filename):
        file_size = (
            content.nbytes if isinstance(content, memoryview)
            else len(content) if isinstance(content, (bytes, bytearray)) else None
        )
        preflight = self.preflight_fbo_document(
            runtime, owner, session, filename, file_size,
        )
        if preflight.get("selected") is not True:
            if preflight.get("selected") is False:
                return {"error": False, "handled": False, "read_only_ozon": True}
            return preflight
        if preflight.get("accepted") is not True:
            return preflight
        raw = content.tobytes() if isinstance(content, memoryview) else bytes(content)
        flow = session.get("provisional_flow")
        upload = flow.get("fbo_upload") if isinstance(flow, dict) else None
        if not self._upload_matches_session(runtime, session, upload):
            return self._upload_error(
                "FIFO_PROVISIONAL_FBO_SELECTION_STALE",
                "Выбор FBO CSV истёк или изменился. Дело не изменено; повторите выбор.",
            )
        parsed = self.fbo_worker.parse_provisional_fbo_csv(
            filename=filename, payload=raw, scope=upload["scope"],
            timezone_name=upload["timezone_name"],
        )
        if not isinstance(parsed, ProvisionalFboParseResult):
            return self._upload_error(
                "FIFO_PROVISIONAL_FBO_WORKER_RESULT_INVALID",
                "Не удалось проверить CSV. Дело не изменено; исправьте файл и повторите.",
            )
        if parsed.status != "COMPLETE" or parsed.document is None:
            code = parsed.issue_codes[0] if parsed.issue_codes else "FIFO_PROVISIONAL_FBO_PARSE_FAILED"
            return self._upload_error(
                code,
                "Не удалось проверить FBO CSV по безопасному формату. "
                "Дело не изменено; дополнительные поля и сырые строки не показываются.",
            )
        reports = self._reports(runtime, session)
        movement = self._find(reports or (), upload["movement_fingerprint"])
        current = runtime._read_case(upload["case_id"], upload["identity"])
        if (
            reports is None or movement is None
            or not runtime._case_matches(current, upload["identity"], upload["case_revision"])
            or movement["period_from"] != upload["movement_from"]
            or movement["period_to"] != upload["movement_to"]
        ):
            return self._upload_error(
                "FIFO_PROVISIONAL_FBO_SELECTION_STALE",
                "Отчёт или FIFO-дело изменились во время чтения CSV. Предпросмотр не сохранён.",
            )
        fields = movement["report"].normalized_fields
        redeemed = fields.get("redeemed_units") if hasattr(fields, "get") else None
        if type(redeemed) is not int or redeemed < 0:
            return self._upload_error(
                "FIFO_PROVISIONAL_FBO_STATEMENT_UNAVAILABLE",
                "Не удалось получить количество выкупов из выбранной ведомости. Предпросмотр не создан.",
            )
        document = parsed.document
        delivered_units = 0
        old_dispatch_delivered_after_snapshot = 0
        old_dispatch_delivered_in_window = 0
        old_dispatch_delivered_after_window = 0
        old_dispatch_in_transit_at_export = 0
        missing_delivery_date_rows = 0
        missing_dispatch_date_rows = 0
        for row in document.rows:
            dispatch_date = row.dispatch.local_date.isoformat() if row.dispatch else None
            delivered_date = row.delivered.local_date.isoformat() if row.delivered else None
            dispatched_by_snapshot = (
                dispatch_date is not None and dispatch_date <= upload["snapshot_to"]
            )
            if row.status_kind == "DELIVERED":
                if delivered_date is None:
                    missing_delivery_date_rows += 1
                    continue
                if dispatch_date is None:
                    if upload["movement_from"] <= delivered_date <= upload["movement_to"]:
                        missing_dispatch_date_rows += 1
                if upload["movement_from"] <= delivered_date <= upload["movement_to"]:
                    delivered_units += row.quantity
                    if dispatched_by_snapshot:
                        old_dispatch_delivered_in_window += row.quantity
                if delivered_date > upload["snapshot_to"] and dispatched_by_snapshot:
                    old_dispatch_delivered_after_snapshot += row.quantity
                    if delivered_date > upload["movement_to"]:
                        old_dispatch_delivered_after_window += row.quantity
            elif row.status_kind == "IN_TRANSIT" and dispatched_by_snapshot:
                old_dispatch_in_transit_at_export += row.quantity
        preview = {
            "document": document,
            "delivered_units_in_window": delivered_units,
            "old_dispatch_delivered_after_snapshot": old_dispatch_delivered_after_snapshot,
            "old_dispatch_delivered_in_window": old_dispatch_delivered_in_window,
            "old_dispatch_delivered_after_window": old_dispatch_delivered_after_window,
            "old_dispatch_in_transit_at_export": old_dispatch_in_transit_at_export,
            "statement_redeemed_units": redeemed,
            "delta_units": delivered_units - redeemed,
            "missing_delivery_date_rows": missing_delivery_date_rows,
            "missing_dispatch_date_rows": missing_dispatch_date_rows,
            "movement_fingerprint": upload["movement_fingerprint"],
            "token": uuid4().hex,
        }
        upload["preview"] = preview
        session["step"] = "provisional_fbo_preview"
        self._advance(runtime, session)
        return runtime._result(
            self._fbo_preview_text(upload),
            keyboard=runtime._keyboard([
                {
                    "text": "Использовать в предварительной оценке",
                    "callback": runtime._issue_ticket(
                        owner, session, "provisional_fbo_confirm",
                        fbo_token=preview["token"],
                    ),
                },
                {
                    "text": "Отменить CSV",
                    "callback": runtime._issue_ticket(
                        owner, session, "provisional_fbo_cancel",
                        fbo_token=preview["token"],
                    ),
                },
            ]),
            code="FIFO_PROVISIONAL_FBO_PREVIEW_READY",
        )

    def _resolve_fbo_preview(self, runtime, owner, session, ticket, flow, action):
        upload = flow.get("fbo_upload")
        token = ticket.get("fbo_token")
        if (
            not isinstance(upload, dict) or not isinstance(token, str)
            or token != (upload.get("preview") or {}).get("token", upload.get("token"))
            or not self._upload_matches_session(runtime, session, upload)
        ):
            return runtime._stale()
        if action == "provisional_fbo_confirm":
            preview = upload.get("preview")
            if not isinstance(preview, dict):
                return runtime._stale()
            upload["accepted"] = preview
            upload["preview"] = None
            flow["timeline_coverage_confirmed"] = None
            flow["timeline_result"] = None
            session.pop("step", None)
            self._advance(runtime, session)
            return self.show(runtime, owner, session)
        flow.pop("fbo_upload", None)
        session.pop("step", None)
        self._advance(runtime, session)
        return self.show(runtime, owner, session)

    def _start_movements_upload(self, runtime, owner, session, flow):
        reports = self._reports(runtime, session)
        snapshot = self._find(reports or (), flow.get("snapshot_fingerprint"))
        movement = self._find(reports or (), flow.get("movement_fingerprint"))
        if reports is None or snapshot is None or movement is None:
            return runtime._result(
                "Сначала выберите снимок и соседнюю ведомость движений. CSV движений не выбран.",
                code="FIFO_PROVISIONAL_MOVEMENTS_REPORTS_REQUIRED",
            )
        current = runtime._read_case(session["case_id"], session["identity"])
        if not runtime._case_matches(current, session["identity"], session["case_revision"]):
            return runtime._result(
                "FIFO-дело изменилось. Откройте его заново перед загрузкой CSV движений.",
                code="FIFO_PROVISIONAL_CASE_STALE",
            )
        case = session.get("case")
        try:
            metadata = case["metadata"]
            scope_data = metadata["scope"]
            identity = session["identity"]
            scope = ScopeIdentity(
                owner_id=scope_data["owner_id"], store_id=identity["store_id"],
                product_id=identity.get("product_id"), offer_id=identity.get("offer_id"),
                sku=identity["sku"],
            )
            timezone_name = metadata["store_timezone"]
        except (KeyError, TypeError, ValueError):
            return runtime._result(
                "Не удалось проверить магазин, SKU и часовой пояс. CSV движений не выбран.",
                code="FIFO_PROVISIONAL_SCOPE_INVALID",
            )
        flow["timeline_coverage_confirmed"] = None
        flow["timeline_result"] = None
        upload = {
            "token": uuid4().hex,
            "case_id": session["case_id"],
            "case_revision": session["case_revision"],
            "identity": dict(session["identity"]),
            "scope": scope,
            "timezone_name": timezone_name,
            "snapshot_fingerprint": snapshot["file_fingerprint"],
            "movement_fingerprint": movement["file_fingerprint"],
            "period_from": movement["period_from"],
            "period_to": movement["period_to"],
            "preview": None,
            "expires_at": self._monotonic() + self.MOVEMENTS_UPLOAD_TTL_SECONDS,
        }
        flow["movements_upload"] = upload
        session["step"] = "provisional_movements_file"
        self._advance(runtime, session)
        return runtime._result(
            "Пришлите CSV по шаблону движений для выбранного окна "
            f"{upload['period_from']} — {upload['period_to']}. Даты и время должны быть в часовом поясе магазина. "
            "Сырые номера отправлений и ссылки будут скрыты; обработка ограничена 10 МиБ и 15 секундами.",
            keyboard=runtime._keyboard([{
                "text": "Отмена",
                "callback": runtime._issue_ticket(
                    owner, session, "provisional_movements_cancel",
                    movements_token=upload["token"],
                ),
            }]),
            code="FIFO_PROVISIONAL_MOVEMENTS_UPLOAD_READY",
        )

    def has_movements_document_selection(self, runtime, owner, session):
        flow = session.get("provisional_flow") if isinstance(session, dict) else None
        upload = flow.get("movements_upload") if isinstance(flow, dict) else None
        return (
            isinstance(upload, dict)
            and session.get("step") in {"provisional_movements_file", "provisional_movements_preview"}
        )

    def preflight_movements_document(self, runtime, owner, session, filename, file_size):
        if not self.has_movements_document_selection(runtime, owner, session):
            return {"error": False, "selected": False, "read_only_ozon": True}
        upload = session["provisional_flow"]["movements_upload"]
        if not self._movements_upload_matches_session(runtime, session, upload):
            return self._preflight_error(
                "FIFO_PROVISIONAL_MOVEMENTS_SELECTION_STALE",
                "Выбор CSV движений истёк или изменился. Файл не загружен; выберите его заново.",
            )
        if session.get("step") != "provisional_movements_file":
            return self._preflight_error(
                "FIFO_PROVISIONAL_MOVEMENTS_PREVIEW_PENDING",
                "Сначала подтвердите или отмените предпросмотр CSV движений.",
            )
        if not isinstance(filename, str) or not filename.lower().endswith(".csv"):
            return self._preflight_error(
                "FIFO_PROVISIONAL_MOVEMENTS_FORMAT_UNSUPPORTED",
                "Для этого шага нужен CSV по шаблону движений. Файл не загружен.",
            )
        if (type(file_size) is not int or file_size <= 0
                or file_size > self.FBO_MAX_FILE_BYTES):
            return self._preflight_error(
                "FIFO_PROVISIONAL_MOVEMENTS_FILE_SIZE_INVALID",
                "CSV должен быть непустым и не превышать 10 МиБ. Файл не загружен.",
            )
        if upload.get("preview") is not None:
            return self._preflight_error(
                "FIFO_PROVISIONAL_MOVEMENTS_PREVIEW_PENDING",
                "Сначала подтвердите или отмените предыдущий предпросмотр.",
            )
        return {"error": False, "selected": True, "accepted": True, "read_only_ozon": True}

    def handle_movements_document(self, runtime, owner, session, content, filename):
        file_size = (
            content.nbytes if isinstance(content, memoryview)
            else len(content) if isinstance(content, (bytes, bytearray)) else None
        )
        preflight = self.preflight_movements_document(
            runtime, owner, session, filename, file_size,
        )
        if preflight.get("selected") is not True:
            if preflight.get("selected") is False:
                return {"error": False, "handled": False, "read_only_ozon": True}
            return preflight
        if preflight.get("accepted") is not True:
            return preflight
        raw = content.tobytes() if isinstance(content, memoryview) else bytes(content)
        flow = session["provisional_flow"]
        upload = flow.get("movements_upload")
        if not self._movements_upload_matches_session(runtime, session, upload):
            return self._upload_error(
                "FIFO_PROVISIONAL_MOVEMENTS_SELECTION_STALE",
                "Выбор CSV движений истёк или изменился. Документы не изменены; повторите выбор.",
            )
        parsed = self.fbo_worker.parse_provisional_movements_csv(
            filename=filename, payload=raw, scope=upload["scope"],
            timezone_name=upload["timezone_name"],
        )
        if not isinstance(parsed, ProvisionalMovementsParseResult):
            return self._upload_error(
                "FIFO_PROVISIONAL_MOVEMENTS_WORKER_RESULT_INVALID",
                "Не удалось безопасно проверить CSV движений. Предварительная оценка не изменена.",
            )
        if parsed.status != "COMPLETE" or parsed.document is None:
            code = parsed.issue_codes[0] if parsed.issue_codes else "FIFO_PROVISIONAL_MOVEMENTS_PARSE_FAILED"
            return self._upload_error(
                code,
                "CSV движений не прошёл проверку шаблона, SKU, дат и количества. "
                "Сырые строки не показываются; предыдущий подтверждённый файл сохранён.",
            )
        reports = self._reports(runtime, session)
        snapshot = self._find(reports or (), upload["snapshot_fingerprint"])
        movement = self._find(reports or (), upload["movement_fingerprint"])
        current = runtime._read_case(upload["case_id"], upload["identity"])
        if (
            reports is None or snapshot is None or movement is None
            or not runtime._case_matches(current, upload["identity"], upload["case_revision"])
            or snapshot["period_to"] is None
            or self._next_day(snapshot["period_to"]) != upload["period_from"]
            or movement["period_to"] != upload["period_to"]
        ):
            return self._upload_error(
                "FIFO_PROVISIONAL_MOVEMENTS_SELECTION_STALE",
                "Выбранный период или FIFO-дело изменились во время чтения. Предпросмотр не сохранён.",
            )
        document = parsed.document
        preview = {
            "document": document,
            "token": uuid4().hex,
            "movement_fingerprint": upload["movement_fingerprint"],
            "snapshot_fingerprint": upload["snapshot_fingerprint"],
        }
        upload["preview"] = preview
        session["step"] = "provisional_movements_preview"
        self._advance(runtime, session)
        event_counts = ", ".join(
            f"{kind}: {count}" for kind, count in sorted(document.event_counts.items())
        )
        return runtime._result(
            "Предпросмотр CSV движений — только предварительная модель.\n"
            f"Окно отчёта: {upload['period_from']} — {upload['period_to']}. "
            f"Строк: {document.row_count}; единиц в строках: {document.total_units}.\n"
            f"Группы событий: {event_counts}.\n"
            "Идентификаторы, номера отправлений и произвольные ссылки скрыты. "
            "Проверьте состав файла перед добавлением в сценарий.",
            keyboard=runtime._keyboard([
                {"text": "Использовать CSV движений", "callback": runtime._issue_ticket(
                    owner, session, "provisional_movements_confirm", movements_token=preview["token"],
                )},
                {"text": "Отменить CSV движений", "callback": runtime._issue_ticket(
                    owner, session, "provisional_movements_cancel", movements_token=preview["token"],
                )},
            ]),
            code="FIFO_PROVISIONAL_MOVEMENTS_PREVIEW_READY",
        )

    def _resolve_movements_preview(self, runtime, owner, session, ticket, flow, action):
        upload = flow.get("movements_upload")
        preview = upload.get("preview") if isinstance(upload, dict) else None
        token = ticket.get("movements_token")
        if (
            action == "provisional_movements_cancel"
            and isinstance(upload, dict) and preview is None
            and token == upload.get("token")
            and self._movements_upload_matches_session(runtime, session, upload)
        ):
            flow.pop("movements_upload", None)
            session.pop("step", None)
            self._advance(runtime, session)
            return self.show(runtime, owner, session)
        if (
            not isinstance(preview, dict) or not isinstance(token, str)
            or token != preview.get("token")
            or not self._movements_upload_matches_session(runtime, session, upload)
            or preview.get("movement_fingerprint") != flow.get("movement_fingerprint")
            or preview.get("snapshot_fingerprint") != flow.get("snapshot_fingerprint")
        ):
            return runtime._stale()
        if action == "provisional_movements_confirm":
            flow["movement_document"] = preview["document"]
            flow["timeline_coverage_confirmed"] = None
            flow["timeline_result"] = None
        flow.pop("movements_upload", None)
        session.pop("step", None)
        self._advance(runtime, session)
        return self.show(runtime, owner, session)

    def _movements_upload_matches_session(self, runtime, session, upload):
        flow = session.get("provisional_flow")
        if (
            not isinstance(flow, dict) or not isinstance(upload, dict)
            or type(upload.get("expires_at")) not in (int, float)
            or self._monotonic() >= upload["expires_at"]
            or upload.get("case_id") != session.get("case_id")
            or upload.get("case_revision") != session.get("case_revision")
            or upload.get("identity") != session.get("identity")
            or upload.get("movement_fingerprint") != flow.get("movement_fingerprint")
            or upload.get("snapshot_fingerprint") != flow.get("snapshot_fingerprint")
        ):
            return False
        current = runtime._read_case(upload["case_id"], upload["identity"])
        return runtime._case_matches(current, upload["identity"], upload["case_revision"])

    def _append_fbo_status(self, runtime, owner, session, flow, lines, buttons):
        upload = flow.get("fbo_upload")
        if not isinstance(upload, dict):
            return
        preview = upload.get("preview") or upload.get("accepted")
        if not isinstance(preview, dict):
            return
        document = preview.get("document")
        if document is None:
            return
        delta = preview["delta_units"]
        sign = "+" if delta > 0 else ""
        lines.extend([
            "",
            "Дополнительная сверка FBO CSV (только сценарий):",
            f"Покрытие владельца: {upload['period_from']} — {upload['period_to']}; "
            f"строк выбранного SKU: {document.row_count}; единиц: {document.selected_units}.",
            f"Статус Доставлен в окне ведомости: {preview['delivered_units_in_window']} шт.; "
            f"выкупы T в ведомости: {preview['statement_redeemed_units']} шт.; "
            f"диагностическая разница CSV − ведомость: {sign}{delta} шт.",
            f"Доставлено после снимка из отправлений до снимка: "
            f"{preview['old_dispatch_delivered_after_snapshot']} шт. "
            f"(в окне ведомости {preview['old_dispatch_delivered_in_window']}, "
            f"позже окна {preview['old_dispatch_delivered_after_window']}); "
            f"таких единиц со статусом «В пути» при выгрузке: "
            f"{preview['old_dispatch_in_transit_at_export']}.",
            "Поздняя доставка не переводит старое отправление на новую ставку. Разницу CSV не подставляем вместо T; полнота отмен и возвратов не подтверждается этой выгрузкой.",
        ])
        if (
            document.unknown_status_rows or preview["missing_delivery_date_rows"]
            or preview["missing_dispatch_date_rows"]
        ):
            lines.append(
                f"Строк с нераспознанным статусом: {document.unknown_status_rows}; "
                f"доставленных без даты доставки: {preview['missing_delivery_date_rows']}; "
                f"доставленных в окне без даты передачи: {preview['missing_dispatch_date_rows']}."
            )
        if upload.get("preview") is not None:
            buttons.extend([
                {
                    "text": "Использовать FBO CSV",
                    "callback": runtime._issue_ticket(
                        owner, session, "provisional_fbo_confirm",
                        fbo_token=preview["token"],
                    ),
                },
                {
                    "text": "Отменить FBO CSV",
                    "callback": runtime._issue_ticket(
                        owner, session, "provisional_fbo_cancel",
                        fbo_token=preview["token"],
                    ),
                },
            ])

    def _append_movements_status(self, runtime, owner, session, flow, lines, buttons):
        document = flow.get("movement_document")
        if document is not None:
            counts = ", ".join(
                f"{kind}: {count}" for kind, count in sorted(document.event_counts.items())
            )
            dates = [event.local_date.isoformat() for event in document.events]
            window = f"{min(dates)} — {max(dates)}" if dates else "даты отсутствуют"
            lines.extend([
                "",
                f"CSV прочих движений подтверждён владельцем: строк {document.row_count}, "
                f"единиц {document.total_units}; даты событий {window}.",
                f"Группы событий: {counts}.",
            ])
        else:
            lines.extend([
                "",
                "CSV прочих движений не загружен. Если таких движений не было, это отдельно учитывается в подтверждении полноты.",
            ])
        upload = flow.get("movements_upload")
        if isinstance(upload, dict) and isinstance(upload.get("preview"), dict):
            lines.append("Предпросмотр CSV движений ожидает подтверждения или отмены.")

    def _fbo_preview_text(self, upload):
        document = upload["preview"]["document"]
        preview = upload["preview"]
        delta = preview["delta_units"]
        sign = "+" if delta > 0 else ""
        return (
            "Предпросмотр FBO CSV — только диагностический сценарий.\n"
            f"Период полного покрытия: {upload['period_from']} — {upload['period_to']}.\n"
            f"Точный SKU: {document.row_count} строк, {document.selected_units} единиц; "
            f"строки других SKU отброшены: {document.excluded_other_sku_rows}.\n"
            f"Доставлено по CSV в окне ведомости: {preview['delivered_units_in_window']} шт.; "
            f"выкупы T в ведомости: {preview['statement_redeemed_units']} шт.; "
            f"разница: {sign}{delta} шт.\n"
            f"Из них передано до снимка и доставлено после него: "
            f"{preview['old_dispatch_delivered_in_window']} шт.; "
            f"всего таких доставок после снимка в CSV: "
            f"{preview['old_dispatch_delivered_after_snapshot']} шт. "
            f"(позже окна {preview['old_dispatch_delivered_after_window']}); "
            f"до снимка передано и всё ещё «В пути» при выгрузке: "
            f"{preview['old_dispatch_in_transit_at_export']} шт.\n"
            f"Распознанные группы статусов (строки): {dict(document.status_counts)}. "
            f"Нераспознанных строк: {document.unknown_status_rows}.\n"
            "Разница не исправляет и не заменяет T; номер отправления, названия и дополнительные "
            "колонки скрыты. CSV сам по себе не доказывает полноту событий."
        )

    def _upload_matches_session(self, runtime, session, upload):
        if not isinstance(upload, dict):
            return False
        flow = session.get("provisional_flow")
        if (
            not isinstance(flow, dict)
            or type(upload.get("expires_at")) not in (int, float)
            or self._monotonic() >= upload["expires_at"]
            or upload.get("case_id") != session.get("case_id")
            or upload.get("case_revision") != session.get("case_revision")
            or upload.get("identity") != session.get("identity")
            or upload.get("movement_fingerprint") != flow.get("movement_fingerprint")
        ):
            return False
        current = runtime._read_case(upload["case_id"], upload["identity"])
        return runtime._case_matches(
            current, upload["identity"], upload["case_revision"],
        )

    @staticmethod
    def _upload_error(code, message):
        return {
            "error": False, "handled": True, "code": code,
            "message": message, "read_only_ozon": True,
        }

    @classmethod
    def _preflight_error(cls, code, message):
        return {
            **cls._upload_error(code, message),
            "selected": True,
            "accepted": False,
        }

    def _calculate(self, runtime, owner, session, flow):
        reports = self._reports(runtime, session)
        if reports is None:
            return runtime._stale()
        if (self._find(reports, flow.get("snapshot_fingerprint")) is None
                or self._find(reports, flow.get("movement_fingerprint")) is None):
            return runtime._result("Выбранные отчёты устарели или отсутствуют. Обновите список и повторите расчёт.")
        try:
            request = self._build_summary_request(runtime, session, flow, reports)
        except (KeyError, TypeError, ValueError, InvalidOperation):
            return runtime._result("Не хватает подтверждённых данных или допущений. История FIFO не менялась.")
        if request is None:
            return runtime._result("Не хватает подтверждённых данных или допущений. История FIFO не менялась.")
        result = self.summary_service.calculate(request)
        flow["result"] = result
        flow["timeline_result"] = None
        self._advance(runtime, session)
        return self.show(runtime, owner, session)

    def _calculate_timeline(self, runtime, owner, session, flow):
        reports = self._reports(runtime, session)
        if reports is None:
            return runtime._stale()
        snapshot = self._find(reports, flow.get("snapshot_fingerprint"))
        movement = self._find(reports, flow.get("movement_fingerprint"))
        if snapshot is None or movement is None:
            return runtime._stale()
        try:
            request = self._build_summary_request(runtime, session, flow, reports)
        except (KeyError, TypeError, ValueError, InvalidOperation):
            request = None
        if request is None:
            return runtime._result(
                "Не хватает подтверждённых отчётов, ставок или исходных допущений. Хронологическая модель не рассчитана.",
            )
        summary_result = self.summary_service.calculate(request)
        flow["result"] = summary_result
        source_reader = self.evidence_reader
        source_bundle = (
            source_reader.read_timeline_sources(
                case_id=session["case_id"], identity=session["identity"],
                expected_case_revision=session["case_revision"],
            )
            if callable(getattr(source_reader, "read_timeline_sources", None))
            else {"error": False, "physical_sales": None, "physical_sales_status": "NOT_CONFIGURED"}
        )
        if not isinstance(source_bundle, dict) or source_bundle.get("error") is not False:
            physical_sales = None
            physical_status = "UNAVAILABLE"
        else:
            physical_sales = source_bundle.get("physical_sales")
            physical_status = source_bundle.get("physical_sales_status")
        fbo_upload = flow.get("fbo_upload")
        accepted_fbo = (
            fbo_upload.get("accepted") if isinstance(fbo_upload, dict)
            and self._upload_matches_session(runtime, session, fbo_upload) else None
        )
        self._advance(runtime, session)
        flow["timeline_result"] = self.timeline_service.calculate(
            scope=request.scope,
            timezone_name=request.store_timezone,
            case_id=session["case_id"],
            snapshot_report=snapshot["report"],
            movement_report=movement["report"],
            summary_result=summary_result,
            fbo_document=accepted_fbo.get("document") if isinstance(accepted_fbo, dict) else None,
            fbo_coverage_from=fbo_upload.get("period_from") if isinstance(accepted_fbo, dict) else None,
            fbo_coverage_to=fbo_upload.get("period_to") if isinstance(accepted_fbo, dict) else None,
            movement_document=flow.get("movement_document"),
            confirmed_reports=(snapshot["report"], movement["report"]),
            confirmed_physical_sales=physical_sales,
            physical_sales_status=physical_status,
            owner_confirmed_coverage=flow.get("timeline_coverage_confirmed") is True,
        )
        return self.show(runtime, owner, session)

    @staticmethod
    def _build_summary_request(runtime, session, flow, reports):
        snapshot = TelegramFifoCostProvisionalService._find(
            reports, flow.get("snapshot_fingerprint"),
        )
        movement = TelegramFifoCostProvisionalService._find(
            reports, flow.get("movement_fingerprint"),
        )
        case = session.get("case")
        if not snapshot or not movement or not isinstance(case, dict):
            return None
        metadata = case["metadata"]
        scope_data = metadata["scope"]
        identity = session["identity"]
        scope = ScopeIdentity(
            owner_id=scope_data["owner_id"], store_id=identity["store_id"],
            product_id=identity.get("product_id"), offer_id=identity.get("offer_id"),
            sku=identity["sku"],
        )
        return ProvisionalSummaryRequest(
            scope=scope, store_timezone=metadata["store_timezone"],
            snapshot=snapshot["report"], movement_report=movement["report"],
            old_unit_cost_rub=Decimal(str(case["old_unit_cost_rub"])),
            new_unit_cost_rub=Decimal(str(case["new_unit_cost_rub"])),
            assumptions=ProvisionalRangeAssumptions(
                opening_all_old=flow.get("opening_all_old"),
                all_period_supply_receipts_new=flow.get("all_period_supply_receipts_new"),
                closing_old_min=flow.get("closing_old_min"),
                closing_old_max=flow.get("closing_old_max"),
            ),
        )

    def _select_report(self, runtime, owner, session, ticket, flow, kind):
        fingerprint = ticket.get("fingerprint")
        reports = self._reports(runtime, session)
        item = self._find(reports or (), fingerprint)
        if not item:
            return runtime._stale()
        if kind == "snapshot" and item["period_from"] != item["period_to"]:
            return runtime._stale()
        if kind == "movement":
            selected = self._find(reports, flow.get("snapshot_fingerprint"))
            if not selected or item["period_from"] != self._next_day(selected["period_to"]):
                return runtime._stale()
            if fingerprint == flow.get("movement_fingerprint"):
                return self.show(runtime, owner, session)
            flow["movement_fingerprint"] = fingerprint
            flow["all_period_supply_receipts_new"] = None
            flow["closing_old_min"] = None
            flow["closing_old_max"] = None
        else:
            if fingerprint == flow.get("snapshot_fingerprint"):
                return self.show(runtime, owner, session)
            flow["snapshot_fingerprint"] = fingerprint
            flow["movement_fingerprint"] = None
            flow["opening_all_old"] = None
            flow["all_period_supply_receipts_new"] = None
            flow["closing_old_min"] = None
            flow["closing_old_max"] = None
        flow.pop("fbo_upload", None)
        flow.pop("movements_upload", None)
        flow["movement_document"] = None
        flow["timeline_coverage_confirmed"] = None
        flow["result"] = None
        flow["timeline_result"] = None
        self._advance(runtime, session)
        return self.show(runtime, owner, session)

    def _reports(self, runtime, session):
        if self.evidence_reader is None:
            return []
        result = self.evidence_reader.list_turnover_reports(
            case_id=session["case_id"], identity=session["identity"],
            expected_case_revision=session["case_revision"],
        )
        if not isinstance(result, dict) or result.get("error") is not False:
            return None
        return list(result.get("reports", ()))

    @staticmethod
    def _find(reports, fingerprint):
        if not fingerprint:
            return None
        return next((item for item in reports if item.get("file_fingerprint") == fingerprint), None)

    @staticmethod
    def _format_result(result):
        if result.status is not ProvisionalStatus.SUMMARY_RANGE:
            issue_text = {
                "SNAPSHOT_REQUIRED": "не выбран однодневный снимок",
                "MOVEMENT_REPORT_REQUIRED": "не выбрана ведомость движений",
                "REPORT_CONTROL_INVALID": "контрольные суммы ведомости не сходятся",
                "REPORT_WINDOW_MISMATCH": "периоды отчётов не образуют непрерывное окно",
                "BUCKET_BOUNDARY_MISMATCH": "категории остатка на стыке отчётов различаются",
                "UNSUPPORTED_RECEIPTS": "есть неразобранные виды поступлений",
                "UNSUPPORTED_EXPENSES": "есть неразобранные виды выбытий",
                "OWNER_OPENING_COMPOSITION_REQUIRED": "не подтверждено, что начальный остаток относится к старой партии",
                "OWNER_RECEIPT_PARTY_REQUIRED": "не подтверждено, что поступления относятся к новой партии",
                "QUANTITY_DISTRIBUTION_EMPTY": "не существует распределения, согласованного с остатками",
                "CLOSING_OLD_STOCK_RANGE_INVALID": "диапазон конечного старого остатка не согласован с остатком",
            }
            reason = next((issue_text[code.value] for code in result.issue_codes if code.value in issue_text),
                          "нужны дополнительные данные или проверка отчётов")
            if result.status is ProvisionalStatus.SOURCE_CONFLICT:
                return f"Сводная модель заблокирована: {reason}. Денежный диапазон не показан."
            return f"Сводная модель не рассчитана: {reason}."
        issue = " Широкая граница: остаток старой партии на конец не установлен." if result.issue_codes else ""
        return (
            f"Предварительная оценка {result.period_from} — {result.period_to}:\n"
            f"Начальный остаток: {result.opening_total:,} шт.; поставки L: {result.supply_receipts:,}; "
            f"пригодные возвраты M: {result.buyer_return_receipts:,}; выкупы T: {result.redeemed_units:,}; "
            f"прочие поддержанные выбытия V/W/X: {result.other_supported_expenses:,}; конечный остаток: {result.closing_total:,}.\n"
            f"Старые выкупы: {result.old_sold_min:,}–{result.old_sold_max:,}; новые: "
            f"{result.new_sold_min:,}–{result.new_sold_max:,}.\n"
            f"Себестоимость выкупов до сторно возвратов: {result.gross_cogs_low_rub:,.2f}–"
            f"{result.gross_cogs_high_rub:,.2f} ₽. Ставки: {result.old_cost_rub} / {result.new_cost_rub} ₽.\n"
            f"S/AA компенсации исключены: {result.excluded_compensation_receipt} / {result.excluded_compensation_expense}."
            f"{issue} Это сводная модель без порядка событий по датам; значения не являются FIFO фактом."
        )

    @staticmethod
    def _format_timeline_result(result, summary_result=None):
        if result.status is ProvisionalStatus.TIMELINE_MODEL:
            layers = (
                f"Старые выкупы: {result.old_sold_units:,} шт.; новые: {result.new_sold_units:,} шт.\n"
                if result.old_sold_units is not None and result.new_sold_units is not None
                else "Ставки одинаковы, поэтому разделение выкупов между партиями не влияет на сумму.\n"
            )
            return (
                f"Хронологическая FIFO-модель · {result.period_from} — {result.period_to} "
                "(предварительная, не факт)\n"
                f"Выкупы: {result.redeemed_units:,} шт.\n{layers}"
                f"Себестоимость выкупов до сторно возвратов: {result.gross_cogs_rub:,.2f} ₽.\n"
                f"Возвратов по цепочке: {result.returned_units}; прочих выбытий: "
                f"{result.non_sale_removed_units} шт. на {result.non_sale_removed_cost_rub:,.2f} ₽; "
                f"остаток доступный / удержанный / в доставке: {result.ending_available_units} / "
                f"{result.ending_held_units} / {result.ending_buyer_delivery_units} шт.\n"
                "Владелец подтвердил полноту источников для выбранного окна; контрольные итоги сошлись. "
                "Модель предварительная: фактический FIFO и прибыль не изменены."
            )
        if result.status is ProvisionalStatus.TIMELINE_GAP:
            reason = TelegramFifoCostProvisionalService._timeline_gap_reason(result.issue_codes)
            progress = (
                f"Счётчик до первого пробела: обработано {result.processed_events} из "
                f"{result.supplied_events} событий; это не денежная и не полная оценка.\n"
                if result.supplied_events else ""
            )
            fallback = (
                "Ниже отдельно показан сводный диапазон по итогам отчёта; он не продолжает префикс хронологии."
                if summary_result is not None and summary_result.status is ProvisionalStatus.SUMMARY_RANGE
                else "Сводный диапазон пока недоступен."
            )
            return f"Хронологическая модель не построена: {reason}\n{progress}{fallback}"
        if result.status is ProvisionalStatus.SOURCE_CONFLICT:
            return "Источники или контрольные категории противоречат друг другу. Хронологическая денежная оценка не показана."
        missing = {
            "OWNER_COVERAGE_CONFIRMATION_REQUIRED": "подтвердите полноту набора событий или оставьте хронологическую модель недоступной",
            "FBO_CSV_REQUIRED": "добавьте CSV отправлений FBO",
            "FBO_COVERAGE_WINDOW_MISMATCH": "загрузите CSV FBO с периодом, точно совпадающим с выбранной ведомостью",
            "SUMMARY_INPUT_REQUIRED": "проверьте допущения по старому остатку и новой партии",
            "SUMMARY_SOURCE_CONFLICT": "исправьте противоречие сводных ведомостей",
            "REPORT_BOUNDARY_INVALID": "проверьте даты и категории на границе отчётов",
        }
        next_step = next((missing[code] for code in result.issue_codes if code in missing),
                         "проверьте выбранные отчёты и подтверждённые источники")
        return f"Хронологическая модель пока недоступна: {next_step}. Предварительный FIFO не меняет фактический расчёт."

    @staticmethod
    def _timeline_gap_reason(issue_codes):
        known = {
            "FBO_DISPATCH_TIME_MISSING": "не подтверждена дата передачи отправления",
            "FBO_DELIVERY_TIME_MISSING": "не подтверждена дата доставки или выкупа",
            "FBO_CANCELLED_UNRESOLVED": "не связана отмена с возвратом товара в остаток",
            "FBO_UNKNOWN_STATUS": "есть нераспознанный статус отправления",
            "FBO_OPENING_LINK_REQUIRED": "старый остаток в доставке не связан с отправлениями",
            "EVENT_REFERENCE_UNMATCHED": "не удалось связать движение со строкой отправления",
            "EVENT_DUPLICATE_CONFLICT": "источники расходятся по одному событию",
            "TIMESTAMP_PRECISION_INSUFFICIENT": "даты недостаточно, чтобы определить порядок событий",
            "TIMELINE_EVENT_ORDER_AMBIGUOUS": "порядок событий одинакового времени не подтверждён",
            "TIMELINE_NEGATIVE_AVAILABLE_STOCK": "выбытие превышает доступный остаток",
            "EVENT_TOTALS_DO_NOT_MATCH_REPORTS": "количества событий не совпали с итогами ведомости",
            "OPENING_DELIVERY_LINK_INCOMPLETE": "не все начальные отправления в доставке связаны с CSV",
            "PHYSICAL_SALES_EVIDENCE_UNAVAILABLE": "источник подтверждённых продаж временно недоступен",
        }
        return next((known[code] for code in issue_codes if code in known),
                    "не хватает полного набора последовательных событий")

    @classmethod
    def _report_label(cls, item):
        return (
            f"Выбрана оборотная ведомость {item['period_from']} — {item['period_to']}; "
            f"версия {cls._report_version_label(item)} "
            "(период подтверждён; отчёт полный)."
        )

    @classmethod
    def _report_choice_label(cls, item, kind):
        kind_label = "Снимок" if kind == "snapshot" else "Движения"
        period = item.get("period_from") or "дата неизвестна"
        if kind == "movement":
            period = f"{period}–{item.get('period_to') or 'дата неизвестна'}"
        return (
            f"{kind_label} {period} · {cls._report_capture_time_label(item)} · "
            f"{cls._report_fingerprint_label(item)}"
        )

    @classmethod
    def _report_version_label(cls, item):
        return (
            f"{cls._report_capture_time_label(item)} · "
            f"{cls._report_fingerprint_label(item)}"
        )

    @staticmethod
    def _report_capture_time_label(item):
        captured_at = item.get("captured_at")
        if not isinstance(captured_at, str):
            report = item.get("report")
            captured_at = getattr(report, "captured_at", None)
        try:
            captured_at = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
            if captured_at.tzinfo is None or captured_at.utcoffset() is None:
                raise ValueError("timezone")
            return captured_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%MZ")
        except (AttributeError, TypeError, ValueError):
            return "время неизвестно"

    @staticmethod
    def _report_fingerprint_label(item):
        fingerprint = item.get("file_fingerprint")
        return (
            fingerprint[:8]
            if isinstance(fingerprint, str) and len(fingerprint) >= 8
            else "версия неизвестна"
        )

    @staticmethod
    def _yes_no_label(value):
        return {True: "Подтверждено владельцем.", False: "Не подтверждено; расчёт будет остановлен.", None: "Не подтверждено."}[value]

    @staticmethod
    def _parse_units(value):
        if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
            return None
        parsed = int(value)
        return parsed if 0 <= parsed <= 1_000_000 else None

    @staticmethod
    def _next_day(value):
        from datetime import date, timedelta
        return (date.fromisoformat(value) + timedelta(days=1)).isoformat()

    @staticmethod
    def _advance(runtime, session):
        session["flow_revision"] = session.get("flow_revision", 0) + 1
