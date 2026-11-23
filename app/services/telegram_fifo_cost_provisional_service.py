"""Owner-only Telegram flow for non-authoritative FIFO summary scenarios."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from services.fifo_cost_provisional_contracts import (
    ProvisionalRangeAssumptions,
    ProvisionalStatus,
    ProvisionalSummaryRequest,
)
from services.fifo_cost_transition_contracts import ScopeIdentity


class TelegramFifoCostProvisionalService:
    """Keep provisional inputs in the existing short-lived Telegram session.

    This service never writes transition cases, FIFO layers, Period Profit data,
    or the saved-estimate ledger. Durable estimates are introduced separately.
    """

    PAGE_SIZE = 8

    def __init__(self, *, evidence_reader, summary_service):
        self.evidence_reader = evidence_reader
        self.summary_service = summary_service

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
        for index, item in enumerate(snapshots[snapshot_start:snapshot_start + self.PAGE_SIZE], start=snapshot_start):
            label = f"Снимок {item['period_from']} · {index + 1}"
            buttons.append({"text": label, "callback": runtime._issue_ticket(
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
            for index, item in enumerate(eligible[movement_start:movement_start + self.PAGE_SIZE], start=movement_start):
                buttons.append({"text": f"Движения {item['period_from']} — {item['period_to']} · {index + 1}",
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
        buttons.extend([
            {"text": "📄 Загрузить оборотную ведомость", "callback": runtime._issue_ticket(owner, session, "provisional_upload")},
            {"text": "⬅️ К карточке партии", "callback": runtime._issue_ticket(owner, session, "provisional_back")},
        ])
        if flow.get("result") is not None:
            lines.extend(["", self._format_result(flow["result"])])
        return runtime._result("\n".join(lines), keyboard=runtime._keyboard(buttons))

    def _calculate(self, runtime, owner, session, flow):
        reports = self._reports(runtime, session)
        if reports is None:
            return runtime._stale()
        snapshot = self._find(reports, flow.get("snapshot_fingerprint"))
        movement = self._find(reports, flow.get("movement_fingerprint"))
        case = session.get("case")
        if not snapshot or not movement or not isinstance(case, dict):
            return runtime._result("Выбранные отчёты устарели или отсутствуют. Обновите список и повторите расчёт.")
        try:
            metadata = case["metadata"]
            scope_data = metadata["scope"]
            identity = session["identity"]
            scope = ScopeIdentity(
                owner_id=scope_data["owner_id"], store_id=identity["store_id"],
                product_id=identity.get("product_id"), offer_id=identity.get("offer_id"),
                sku=identity["sku"],
            )
            old_cost = Decimal(str(case["old_unit_cost_rub"]))
            new_cost = Decimal(str(case["new_unit_cost_rub"]))
            request = ProvisionalSummaryRequest(
                scope=scope, store_timezone=metadata["store_timezone"],
                snapshot=snapshot["report"], movement_report=movement["report"],
                old_unit_cost_rub=old_cost, new_unit_cost_rub=new_cost,
                assumptions=ProvisionalRangeAssumptions(
                    opening_all_old=flow.get("opening_all_old"),
                    all_period_supply_receipts_new=flow.get("all_period_supply_receipts_new"),
                    closing_old_min=flow.get("closing_old_min"),
                    closing_old_max=flow.get("closing_old_max"),
                ),
            )
        except (KeyError, TypeError, ValueError, InvalidOperation):
            return runtime._result("Не хватает подтверждённых данных или допущений. История FIFO не менялась.")
        result = self.summary_service.calculate(request)
        flow["result"] = result
        self._advance(runtime, session)
        return self.show(runtime, owner, session)

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
            flow["movement_fingerprint"] = fingerprint
        else:
            flow["snapshot_fingerprint"] = fingerprint
            flow["movement_fingerprint"] = None
        flow["result"] = None
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
            return f"Результат: {result.status.value}; причина: {', '.join(code.value for code in result.issue_codes)}. Денежная оценка не показана."
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
    def _report_label(item):
        return f"Выбран отчёт за {item['period_from']} — {item['period_to']} (период подтверждён; отчёт полный)."

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
