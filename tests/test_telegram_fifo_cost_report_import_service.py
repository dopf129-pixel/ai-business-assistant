from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from io import BytesIO

from openpyxl import Workbook

from services.fifo_cost_report_import_service import (
    FifoCostReportImportResult,
    FifoCostReportImportService,
)
from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_transition_contracts import (
    CostInputMode,
    EvidenceCompleteness,
    EvidenceSourceKind,
    ReportType,
    PeriodProvenance,
    ScopeIdentity,
    TransitionCase,
    TransitionMetadata,
    TransitionReasonCode,
    TransitionState,
    UnknownValue,
)
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)
from services.telegram_fifo_cost_report_import_service import (
    TelegramFifoCostReportImportService,
)


OWNER = "owner-1"
STORE = "store-1"
TENANT = make_store_tenant_scope(OWNER, STORE)
SKU = "3921245627"


def _case(*, case_id="case_000001", sku=SKU, revision=1):
    scope = ScopeIdentity(
        owner_id=OWNER,
        store_id=STORE,
        product_id="product-1",
        offer_id="hook-2",
        sku=sku,
    )
    metadata = TransitionMetadata(
        scope=scope,
        source_kind=EvidenceSourceKind.OWNER_INPUT,
        completeness=EvidenceCompleteness.PARTIAL,
        source_fingerprint="a" * 64,
    )
    return TransitionCase(
        metadata=metadata,
        case_id=case_id,
        case_revision=revision,
        state=TransitionState.DRAFT,
        created_at="2026-11-08T10:00:00Z",
        updated_at="2026-11-08T10:00:00Z" if revision == 1 else "2026-11-08T11:00:00Z",
        dispatch_date="2026-11-05",
        old_unit_cost_rub="21.00",
        new_unit_cost_rub="14.65",
        cost_input_mode=CostInputMode.TOTAL_LANDED,
        cost_components=None,
        owner_old_home_units=0,
        owner_old_transit_units=0,
        new_home_quantity=None,
        declared_shipped_units=6982,
        unknown_values={
            "new_home_quantity": UnknownValue(
                reason_code=TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE,
                source_kind=EvidenceSourceKind.OWNER_INPUT,
            ),
        },
    )


def _turnover_payload(sku=SKU):
    parser = FifoCostReportImportService()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = parser.SHEET_NAME
    for cell_ref, value in parser._EXPECTED_HEADERS.items():
        sheet[cell_ref] = value
    values = [0] * 40
    values[0] = int(sku)
    values[3:11] = [2740, 0, 2, 1, 1, 1, 75, 1672]
    values[11:18] = [0] * 7
    values[18] = 9
    values[19:26] = [775, 0, 5, 0, 0, 0, 0]
    values[26] = 4
    values[27:35] = [1988, 0, 2, 6, 0, 0, 70, 1646]
    values[35:39] = [4492, 0, 780, 3712]
    values[39] = 0
    for column, value in enumerate(values, start=1):
        sheet.cell(row=4, column=column, value=value)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


class _DirectWorker:
    def __init__(self):
        self.calls = 0
        self.fail = False

    def parse(self, *, report_type, filename, payload, scope):
        self.calls += 1
        if self.fail:
            return FifoCostReportImportResult(
                "ERROR", True, False, None, None, ("FIFO_REPORT_XLSX_PACKAGE_INVALID",),
            )
        if report_type is not ReportType.TURNOVER:
            return FifoCostReportImportResult(
                "ERROR", True, False, None, None, ("FIFO_REPORT_FORMAT_UNSUPPORTED",),
            )
        return FifoCostReportImportService().parse_turnover_workbook(
            payload=payload, filename=filename, scope=scope,
        )


def _setup(tmp_path, *, worker=None):
    repository = FifoCostRepository(
        db_path=tmp_path / "fifo-report-import.sqlite",
        now_provider=lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc),
    )
    service = TelegramFifoCostReportImportService(
        repository=repository,
        worker=worker or _DirectWorker(),
    )
    first = _case()
    tenant = set_current_tenant_user_id(TENANT)
    try:
        assert repository.save_transition_case(
            case=first, expected_revision=0, idempotency_key="case-create-0001",
        )["error"] is False
    finally:
        reset_current_tenant_user_id(tenant)
    return repository, service, first


def _select(service, case, *, user=OWNER):
    scope = case.metadata.scope
    ticket = service.create_selection_callback(
        user_id=user,
        case_id=case.case_id,
        scope=scope,
        report_type=ReportType.TURNOVER,
    )
    assert ticket["error"] is False
    assert len(ticket["callback"].encode("utf-8")) <= 64
    assert case.case_id not in ticket["callback"]
    assert scope.sku not in ticket["callback"]
    return service.handle_callback(user, ticket["callback"])


def test_upload_without_selected_case_is_not_parsed_or_saved(tmp_path):
    worker = _DirectWorker()
    repository, service, case = _setup(tmp_path, worker=worker)
    tenant = set_current_tenant_user_id(TENANT)
    try:
        result = service.handle_document(OWNER, _turnover_payload(), "turnover_04112026-05112026.xlsx")
        assert result["code"] == "FIFO_REPORT_CASE_SELECTION_REQUIRED"
        assert worker.calls == 0
        current = repository.read_transition_case(
            case_id=case.case_id, store_id=STORE, product_id="product-1",
            offer_id="hook-2", sku=SKU,
        )
        assert current["case_revision"] == 1
        assert repository.read_transition_evidence(
            case_id=case.case_id, store_id=STORE, product_id="product-1",
            offer_id="hook-2", sku=SKU, kind="REPORT_EVIDENCE",
        )["items"] == []
    finally:
        reset_current_tenant_user_id(tenant)


def test_explicit_preview_then_confirm_persists_once_and_replays(tmp_path):
    repository, service, case = _setup(tmp_path)
    tenant = set_current_tenant_user_id(TENANT)
    try:
        assert _select(service, case)["error"] is False
        preview = service.handle_document(
            OWNER, _turnover_payload(), "turnover_04112026-05112026.xlsx",
        )
        assert preview["code"] == "FIFO_REPORT_PREVIEW_READY"
        assert "дата-кандидат" in preview["message"]
        assert "Период из имени файла сам по себе не подтверждён" in preview["message"]
        confirm = preview["keyboard"]["buttons"][0]["callback"]
        assert len(confirm.encode("utf-8")) <= 64
        assert case.case_id not in confirm and SKU not in confirm
        before = repository.read_transition_case(
            case_id=case.case_id, store_id=STORE, product_id="product-1",
            offer_id="hook-2", sku=SKU,
        )
        assert before["case_revision"] == 1
        saved = service.handle_callback(OWNER, confirm)
        assert saved["code"] == "FIFO_TRANSITION_EVIDENCE_SAVED"
        assert saved["case_revision"] == 2
        replay = service.handle_callback(OWNER, confirm)
        assert replay["replayed"] is True
        evidence = repository.read_transition_evidence(
            case_id=case.case_id, store_id=STORE, product_id="product-1",
            offer_id="hook-2", sku=SKU, kind="REPORT_EVIDENCE",
        )
        assert len(evidence["items"]) == 1
        assert evidence["items"][0]["period_provenance"] == "FILENAME_CANDIDATE"
    finally:
        reset_current_tenant_user_id(tenant)


def test_same_report_can_be_reimported_to_append_owner_period_confirmation(tmp_path):
    repository, service, case = _setup(tmp_path)
    tenant = set_current_tenant_user_id(TENANT)
    filename = "turnover_04112026-05112026.xlsx"
    payload = _turnover_payload()
    try:
        _select(service, case)
        candidate_preview = service.handle_document(OWNER, payload, filename)
        candidate_confirm = candidate_preview["keyboard"]["buttons"][0]["callback"]
        candidate_saved = service.handle_callback(OWNER, candidate_confirm)
        assert candidate_saved["error"] is False
        assert "остаётся кандидатом" in candidate_saved["message"]

        # A fresh selection binds the same bytes to the current case revision.
        _select(service, case)
        confirmation_preview = service.handle_document(OWNER, payload, filename)
        confirm_period = next(
            button["callback"] for button in confirmation_preview["keyboard"]["buttons"]
            if button["text"] == "📅 Подтвердить период из имени файла"
        )
        assert len(confirm_period.encode("utf-8")) <= 64
        confirmed = service.handle_callback(OWNER, confirm_period)
        assert confirmed["error"] is False
        assert "отдельно подтверждён владельцем" in confirmed["message"]

        evidence = repository.read_transition_evidence(
            case_id=case.case_id, store_id=STORE, product_id="product-1",
            offer_id="hook-2", sku=SKU, kind="REPORT_EVIDENCE",
        )
        assert len(evidence["items"]) == 1
        assert evidence["items"][0]["period_from"] == "2026-11-04"
        assert evidence["items"][0]["period_to"] == "2026-11-05"
        assert evidence["items"][0]["period_provenance"] == "OWNER_CONFIRMED"

        connection = repository.get_connection()
        try:
            assert connection.execute(
                "SELECT period_provenance FROM fifo_cost_report_evidence WHERE case_id=?",
                (case.case_id,),
            ).fetchone()[0] == PeriodProvenance.FILENAME_CANDIDATE.value
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_report_period_confirmations WHERE case_id=?",
                (case.case_id,),
            ).fetchone()[0] == 1
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(tenant)


def test_failed_import_keeps_selected_case_available_for_retry(tmp_path):
    worker = _DirectWorker()
    worker.fail = True
    repository, service, case = _setup(tmp_path, worker=worker)
    tenant = set_current_tenant_user_id(TENANT)
    try:
        _select(service, case)
        failure = service.handle_document(OWNER, b"bad xlsx", "turnover.xlsx")
        assert failure["code"] == "FIFO_REPORT_XLSX_PACKAGE_INVALID"
        worker.fail = False
        retry = service.handle_document(
            OWNER, _turnover_payload(), "turnover_04112026-05112026.xlsx",
        )
        assert retry["code"] == "FIFO_REPORT_PREVIEW_READY"
        current = repository.read_transition_case(
            case_id=case.case_id, store_id=STORE, product_id="product-1",
            offer_id="hook-2", sku=SKU,
        )
        assert current["case_revision"] == 1
    finally:
        reset_current_tenant_user_id(tenant)


def test_stale_preview_does_not_clear_another_case_selection(tmp_path):
    repository, service, first = _setup(tmp_path)
    second = _case(case_id="case_000002", sku="3921245628")
    tenant = set_current_tenant_user_id(TENANT)
    try:
        assert repository.save_transition_case(
            case=second, expected_revision=0, idempotency_key="case-create-0002",
        )["error"] is False
        _select(service, first)
        first_preview = service.handle_document(
            OWNER, _turnover_payload(), "turnover_04112026-05112026.xlsx",
        )
        confirm_first = first_preview["keyboard"]["buttons"][0]["callback"]
        changed_first = replace(
            first, case_revision=2, updated_at="2026-11-08T11:00:00Z",
        )
        assert repository.save_transition_case(
            case=changed_first, expected_revision=1,
            idempotency_key="case-revise-0001",
        )["error"] is False
        _select(service, second)
        stale = service.handle_callback(OWNER, confirm_first)
        assert stale["code"] == "FIFO_REPORT_PREVIEW_STALE"
        second_preview = service.handle_document(
            OWNER, _turnover_payload("3921245628"), "turnover_04112026-05112026.xlsx",
        )
        assert second_preview["code"] == "FIFO_REPORT_PREVIEW_READY"
        assert repository.read_transition_evidence(
            case_id=second.case_id, store_id=STORE, product_id="product-1",
            offer_id="hook-2", sku="3921245628", kind="REPORT_EVIDENCE",
        )["items"] == []
    finally:
        reset_current_tenant_user_id(tenant)


def test_wrong_owner_scope_and_file_size_fail_before_worker(tmp_path):
    worker = _DirectWorker()
    _repository, service, _case_value = _setup(tmp_path, worker=worker)
    tenant = set_current_tenant_user_id(TENANT)
    try:
        assert service.handle_document(OWNER, b"x", "bad.csv")["code"] == "FIFO_REPORT_FORMAT_UNSUPPORTED"
        assert service.handle_document(
            OWNER, b"x" * (service.MAX_FILE_BYTES + 1), "large.xlsx",
        )["code"] == "FIFO_REPORT_FILE_SIZE_INVALID"
        assert worker.calls == 0
        wrong_owner = service.create_selection_callback(
            user_id="someone-else", case_id="case_000001",
            scope=_case().metadata.scope, report_type=ReportType.TURNOVER,
        )
        assert wrong_owner["code"] == "FIFO_REPORT_OWNER_SCOPE_REQUIRED"
    finally:
        reset_current_tenant_user_id(tenant)
