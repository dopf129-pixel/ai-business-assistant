from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import hashlib
import inspect
import sqlite3

import pytest

from cryptography.fernet import Fernet

from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_period_profit_source_service import (
    FifoCostPeriodProfitSourceService,
)
from services.fifo_cost_transition_store import FifoCostTransitionStore
from services.fifo_cost_transition_contracts import (
    CostInputMode,
    EvidenceCompleteness,
    EvidencePresence,
    EvidenceSourceKind,
    NormalizedSupplyStatus,
    PeriodProvenance,
    ReportEvidence,
    ReportType,
    ScopeIdentity,
    SupplyDeclaration,
    SupplyObservation,
    SupplyReferenceKind,
    TransitionCase,
    TransitionMetadata,
    TransitionReasonCode,
    TransitionState,
    UnknownValue,
)
from services.ozon_account_repository import make_store_tenant_scope
from services.period_profit_effective_cost_sale_quantity_summary_service import (
    PeriodProfitEffectiveCostSaleQuantitySummaryService,
)
from services.tenant_cipher_provider import encrypt_tenant_value
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


STORE = "store-transition"
OWNER = "owner-transition"
TENANT = make_store_tenant_scope(OWNER, STORE)
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
MASTER_KEY = Fernet.generate_key().decode("ascii")


def _metadata(kind=EvidenceSourceKind.OWNER_INPUT, completeness=EvidenceCompleteness.UNKNOWN,
              *, owner=OWNER, store=STORE, sku="sku-1", product="product-1",
              source_fingerprint=None):
    return TransitionMetadata(
        scope=ScopeIdentity(
            owner_id=owner, store_id=store, product_id=product,
            offer_id="offer-1", sku=sku,
        ),
        source_kind=kind,
        completeness=completeness,
        source_fingerprint=source_fingerprint or "a" * 64,
    )


def _case(case_id="transition-case-0001", *, sku="sku-1", owner=OWNER, store=STORE):
    return TransitionCase(
        metadata=_metadata(owner=owner, store=store, sku=sku),
        case_id=case_id,
        case_revision=1,
        state=TransitionState.DRAFT,
        created_at="2026-11-07T12:00:00Z",
        updated_at="2026-11-07T12:00:00Z",
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
                TransitionReasonCode.SUPPLY_OBSERVATION_MISSING,
                EvidenceSourceKind.OWNER_INPUT,
            ),
        },
    )


def _declaration(case_id="transition-case-0001", declaration_id="decl-0001",
                 quantity=6234, *, revision=1, encrypted=True, owner=OWNER,
                 store=STORE, sku="sku-1", reference_id=2000070135564):
    lookup = (
        encrypt_tenant_value(reference_id, master_key=MASTER_KEY)
        if encrypted else None
    )
    digest = hashlib.sha256(
        f"fifo-supply-reference:{owner}:{store}:SUPPLY:{reference_id}".encode()
    ).hexdigest()
    unknown_values = {} if encrypted else {
        "lookup_reference": UnknownValue(
            TransitionReasonCode.LOOKUP_REFERENCE_UNAVAILABLE,
            EvidenceSourceKind.OWNER_INPUT,
        ),
    }
    return SupplyDeclaration(
        metadata=_metadata(owner=owner, store=store, sku=sku),
        case_id=case_id,
        declaration_id=declaration_id,
        revision=revision,
        reference_kind=SupplyReferenceKind.SUPPLY,
        reference_digest=digest,
        encrypted_lookup_reference=lookup,
        declared_shipped_units=quantity,
        dispatch_date="2026-11-05",
        provenance=EvidenceSourceKind.OWNER_INPUT,
        unknown_values=unknown_values,
    )


def _observation(declaration_id="decl-0001"):
    return SupplyObservation(
        metadata=_metadata(
            EvidenceSourceKind.OZON_API, EvidenceCompleteness.PARTIAL,
            source_fingerprint="b" * 64,
        ),
        declaration_id=declaration_id,
        captured_at="2026-11-07T12:00:00Z",
        source_as_of=None,
        raw_status="RECEIVING",
        normalized_status=NormalizedSupplyStatus.RECEIVING,
        declared_quantity=6234,
        accepted_quantity=None,
        accepted_quantity_kind=None,
        act_reference_digest=None,
        act_version_digest=None,
        scope_complete=True,
        pagination_complete=False,
        presence=EvidencePresence.PRESENT,
        unknown_values={
            "accepted_quantity": UnknownValue(
                TransitionReasonCode.SUPPLY_OBSERVATION_MISSING,
                EvidenceSourceKind.OZON_API,
            ),
        },
    )


def _report():
    return ReportEvidence(
        metadata=_metadata(
            EvidenceSourceKind.OWNER_IMPORTED, EvidenceCompleteness.COMPLETE,
            source_fingerprint="c" * 64,
        ),
        report_type=ReportType.TURNOVER,
        period_from="2026-11-04",
        period_to="2026-11-05",
        period_provenance=PeriodProvenance.OWNER_CONFIRMED,
        captured_at="2026-11-07T12:00:00Z",
        file_sha256="d" * 64,
        parser_version="1.0.0",
        cell_references=("A1", "B12"),
        normalized_fields={"opening": 4492, "receipts": 0, "redeemed": 775,
                           "withdrawals": 5, "closing": 3712},
    )


def _repository(tmp_path):
    return FifoCostRepository(db_path=tmp_path / "transition.sqlite", now_provider=lambda: NOW)


def test_transition_repository_commands_are_keyword_only():
    for method_name in (
        "save_transition_case", "read_transition_case",
        "append_supply_declaration", "append_supply_observation",
        "append_report_evidence", "read_transition_evidence",
    ):
        parameters = inspect.signature(
            getattr(FifoCostRepository, method_name),
        ).parameters.values()
        assert all(
            parameter.kind is inspect.Parameter.KEYWORD_ONLY
            for parameter in list(parameters)[1:]
        ), method_name


def test_case_is_saved_read_after_restart_and_does_not_initialize_fifo(tmp_path):
    tenant = set_current_tenant_user_id(TENANT)
    try:
        repository = _repository(tmp_path)
        case = _case()
        saved = repository.save_transition_case(
            case=case, expected_revision=0, idempotency_key="case-create-0001",
        )
        assert saved == {
            "error": False, "code": "FIFO_TRANSITION_CASE_SAVED",
            "case_id": case.case_id, "case_revision": 1,
            "state": "DRAFT", "replayed": False,
        }
        restarted = _repository(tmp_path)
        read = restarted.read_transition_case(
            case_id=case.case_id, store_id=STORE, product_id="product-1",
            offer_id="offer-1", sku="sku-1",
        )
        assert read["case_revision"] == 1
        assert read["case"]["new_unit_cost_rub"] == "14.65"
        assert read["case"]["cost_input_mode"] == "TOTAL_LANDED"
        assert "owner_id" not in read["case"]["metadata"]["scope"]
        assert restarted.read_cost_history_snapshot(
            store_id=STORE, product_id="product-1", offer_id="offer-1", sku="sku-1",
        )["code"] == "FIFO_HISTORY_NOT_INITIALIZED"
    finally:
        reset_current_tenant_user_id(tenant)


def test_case_cas_idempotency_and_owner_state_gate(tmp_path):
    tenant = set_current_tenant_user_id(TENANT)
    try:
        repository = _repository(tmp_path)
        case = _case()
        assert repository.save_transition_case(
            case=case, expected_revision=0, idempotency_key="case-save-0001",
        )["error"] is False
        replay = repository.save_transition_case(
            case=case, expected_revision=0, idempotency_key="case-save-0001",
        )
        assert replay["code"] == "FIFO_TRANSITION_REPLAYED"
        assert replay["replayed"] is True

        conflicting = replace(case, new_unit_cost_rub=15)
        conflict = repository.save_transition_case(
            case=conflicting, expected_revision=0, idempotency_key="case-save-0001",
        )
        assert conflict["code"] == "FIFO_TRANSITION_IDEMPOTENCY_CONFLICT"

        stale = replace(case, case_revision=2, updated_at="2026-11-07T12:01:00Z")
        assert repository.save_transition_case(
            case=stale, expected_revision=0, idempotency_key="case-save-0002",
        )["code"] == "FIFO_TRANSITION_REVISION_CONFLICT"
        forbidden = replace(
            case, case_revision=2, state=TransitionState.READY_TO_CONFIRM,
            updated_at="2026-11-07T12:01:00Z",
        )
        assert repository.save_transition_case(
            case=forbidden, expected_revision=1, idempotency_key="case-save-0003",
        )["code"] == "FIFO_TRANSITION_CASE_NOT_READY"
    finally:
        reset_current_tenant_user_id(tenant)


def test_concurrent_case_updates_have_one_cas_winner(tmp_path):
    tenant = set_current_tenant_user_id(TENANT)
    try:
        repository = _repository(tmp_path)
        case = _case()
        repository.save_transition_case(
            case=case, expected_revision=0, idempotency_key="case-create-0001",
        )

        def update(price, key):
            thread_tenant = set_current_tenant_user_id(TENANT)
            try:
                changed = replace(
                    case, case_revision=2, new_unit_cost_rub=price,
                    updated_at="2026-11-07T12:01:00Z",
                )
                return repository.save_transition_case(
                    case=changed, expected_revision=1, idempotency_key=key,
                )
            finally:
                reset_current_tenant_user_id(thread_tenant)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda args: update(*args),
                [("14.65", "case-update-0001"), ("15.00", "case-update-0002")],
            ))
        assert sum(result.get("code") == "FIFO_TRANSITION_CASE_SAVED" for result in results) == 1
        assert sum(result.get("code") == "FIFO_TRANSITION_REVISION_CONFLICT" for result in results) == 1
        read = repository.read_transition_case(
            case_id=case.case_id, store_id=STORE, product_id="product-1",
            offer_id="offer-1", sku="sku-1",
        )
        assert read["case_revision"] == 2
        assert read["case"]["new_unit_cost_rub"] in {"14.65", "15.00"}
    finally:
        reset_current_tenant_user_id(tenant)


def test_evidence_append_replay_conflicting_key_stale_cas_and_safe_read(tmp_path):
    tenant = set_current_tenant_user_id(TENANT)
    try:
        repository = _repository(tmp_path)
        case_id = _case().case_id
        assert repository.save_transition_case(
            case=_case(), expected_revision=0, idempotency_key="case-create-0001",
        )["error"] is False
        declaration = _declaration()
        result = repository.append_supply_declaration(
            declaration=declaration, expected_case_revision=1,
            idempotency_key="decl-append-0001",
        )
        assert result["case_revision"] == 2
        replay = repository.append_supply_declaration(
            declaration=declaration, expected_case_revision=1,
            idempotency_key="decl-append-0001",
        )
        assert replay["replayed"] is True
        assert replay["case_revision"] == 2
        changed = _declaration(quantity=6000)
        assert repository.append_supply_declaration(
            declaration=changed, expected_case_revision=1,
            idempotency_key="decl-append-0001",
        )["code"] == "FIFO_TRANSITION_IDEMPOTENCY_CONFLICT"
        assert repository.append_supply_declaration(
            declaration=_declaration(declaration_id="decl-0002"),
            expected_case_revision=1, idempotency_key="decl-stale-0001",
        )["code"] == "FIFO_TRANSITION_REVISION_CONFLICT"

        read = repository.read_transition_evidence(
            case_id=case_id, store_id=STORE, product_id="product-1", offer_id="offer-1",
            sku="sku-1", kind="SUPPLY_DECLARATION",
        )
        assert len(read["items"]) == 1
        assert "encrypted_lookup_reference" not in read["items"][0]
        assert read["items"][0]["payload"]["reference_digest"] == declaration.reference_digest

        connection = sqlite3.connect(repository.db_path)
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_supply_declarations WHERE case_id=?",
                (case_id,),
            ).fetchone()[0] == 1
            assert connection.execute(
                "SELECT current_revision, current_state FROM fifo_cost_transition_cases "
                "WHERE case_id=?", (case_id,),
            ).fetchone() == (2, "AWAITING_EVIDENCE")
            assert b"2000070135564" not in repository.db_path.read_bytes()
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                connection.execute(
                    "UPDATE fifo_cost_supply_declarations SET declared_shipped_units=1 "
                    "WHERE case_id=?", (case_id,),
                )
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(tenant)


def test_observation_and_report_evidence_are_append_only_and_readable(tmp_path):
    tenant = set_current_tenant_user_id(TENANT)
    try:
        repository = _repository(tmp_path)
        case = _case()
        repository.save_transition_case(
            case=case, expected_revision=0, idempotency_key="case-create-0001",
        )
        repository.append_supply_declaration(
            declaration=_declaration(), expected_case_revision=1,
            idempotency_key="decl-append-0001",
        )
        observation = _observation()
        observed = repository.append_supply_observation(
            case_id=case.case_id, observation=observation, expected_case_revision=2,
            idempotency_key="observation-001",
        )
        assert observed["case_revision"] == 3
        report = _report()
        imported = repository.append_report_evidence(
            case_id=case.case_id, report=report, expected_case_revision=3,
            idempotency_key="report-import-0001",
        )
        assert imported["case_revision"] == 4
        obs_read = repository.read_transition_evidence(
            case_id=case.case_id, store_id=STORE, product_id="product-1", offer_id="offer-1",
            sku="sku-1", kind="SUPPLY_OBSERVATION",
        )
        assert obs_read["items"][0]["normalized_status"] == "RECEIVING"
        assert obs_read["items"][0]["accepted_quantity"] is None
        report_read = repository.read_transition_evidence(
            case_id=case.case_id, store_id=STORE, product_id="product-1", offer_id="offer-1",
            sku="sku-1", kind="REPORT_EVIDENCE",
        )
        assert report_read["items"][0]["payload"]["normalized_fields"]["closing"] == 3712
        assert report_read["items"][0]["file_sha256"] == report.file_sha256
    finally:
        reset_current_tenant_user_id(tenant)


def test_case_and_declaration_quotas_preserve_last_committed_state(tmp_path):
    tenant = set_current_tenant_user_id(TENANT)
    try:
        repository = _repository(tmp_path)
        for index in range(20):
            case = _case(f"transition-case-{index:04d}", sku=f"sku-{index}")
            assert repository.save_transition_case(
                case=case, expected_revision=0,
                idempotency_key=f"case-create-{index:04d}",
            )["error"] is False
        overflow_case = _case("transition-case-overflow", sku="sku-overflow")
        blocked = repository.save_transition_case(
            case=overflow_case, expected_revision=0,
            idempotency_key="case-create-overflow",
        )
        assert blocked["code"] == "FIFO_TRANSITION_CASE_LIMIT_REACHED"

        declaration_tenant = set_current_tenant_user_id(
            make_store_tenant_scope(OWNER, "store-declarations")
        )
        try:
            case = _case("transition-case-declarations", store="store-declarations")
            assert repository.save_transition_case(
                case=case, expected_revision=0, idempotency_key="case-decl-create",
            )["error"] is False
            case_revision = 1
            for index in range(100):
                result = repository.append_supply_declaration(
                    declaration=_declaration(
                        case_id=case.case_id, declaration_id=f"decl-{index:04d}",
                        quantity=0, store="store-declarations",
                        reference_id=2100000000000 + index,
                    ),
                    expected_case_revision=case_revision,
                    idempotency_key=f"decl-key-{index:04d}",
                )
                assert result["error"] is False, result
                case_revision += 1
            blocked_declaration = repository.append_supply_declaration(
                declaration=_declaration(
                    case_id=case.case_id, declaration_id="decl-overflow",
                    quantity=0, store="store-declarations", reference_id=2100000000100,
                ),
                expected_case_revision=case_revision,
                idempotency_key="decl-overflow-0001",
            )
            assert blocked_declaration["code"] == "FIFO_TRANSITION_DECLARATION_LIMIT_REACHED"
            read = repository.read_transition_case(
                case_id=case.case_id, store_id="store-declarations", product_id="product-1",
                offer_id="offer-1", sku="sku-1",
            )
            assert read["case_revision"] == case_revision
            declarations = repository.read_transition_evidence(
                case_id=case.case_id, store_id="store-declarations", product_id="product-1",
                offer_id="offer-1", sku="sku-1", kind="SUPPLY_DECLARATION", limit=200,
            )
            assert len(declarations["items"]) == 100
        finally:
            reset_current_tenant_user_id(declaration_tenant)
    finally:
        reset_current_tenant_user_id(tenant)


def test_foreign_tenant_cannot_read_or_append_to_transition_case(tmp_path):
    repository = _repository(tmp_path)
    owner = set_current_tenant_user_id(TENANT)
    try:
        case = _case()
        repository.save_transition_case(
            case=case, expected_revision=0, idempotency_key="case-create-0001",
        )
    finally:
        reset_current_tenant_user_id(owner)

    foreign = set_current_tenant_user_id(make_store_tenant_scope("another-owner", STORE))
    try:
        assert repository.read_transition_case(
            case_id=case.case_id, store_id=STORE, product_id="product-1",
            offer_id="offer-1", sku="sku-1",
        )["code"] == "FIFO_TRANSITION_CASE_NOT_FOUND"
        wrong_owner_declaration = _declaration(owner="another-owner")
        assert repository.append_supply_declaration(
            declaration=wrong_owner_declaration, expected_case_revision=1,
            idempotency_key="foreign-append-0001",
        )["code"] == "FIFO_TRANSITION_CASE_NOT_FOUND"
    finally:
        reset_current_tenant_user_id(foreign)


def test_observation_quota_does_not_append_or_advance_case_revision(tmp_path):
    tenant = set_current_tenant_user_id(TENANT)
    try:
        repository = _repository(tmp_path)
        case = _case()
        repository.save_transition_case(
            case=case, expected_revision=0, idempotency_key="case-create-0001",
        )
        repository.append_supply_declaration(
            declaration=_declaration(), expected_case_revision=1,
            idempotency_key="decl-append-0001",
        )
        connection = repository.get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.executemany(
                """INSERT INTO fifo_cost_supply_observations (
                    observation_id, case_id, declaration_id, declaration_revision,
                    captured_at, raw_status, normalized_status, declared_quantity,
                    accepted_quantity, accepted_quantity_kind, act_reference_digest,
                    act_version_digest, presence, completeness, scope_complete,
                    pagination_complete, source_kind, source_fingerprint, payload_json
                ) VALUES (?, ?, 'decl-0001', 1, '2026-11-07T12:00:00Z', 'RECEIVING',
                          'RECEIVING', 6234, NULL, NULL, NULL, NULL, 'PRESENT',
                          'PARTIAL', 1, 1, 'OZON_API', ?, '{}')""",
                [
                    (f"obs-limit-{index:04d}", case.case_id, "e" * 64)
                    for index in range(2000)
                ],
            )
            connection.commit()
        finally:
            connection.close()

        blocked = repository.append_supply_observation(
            case_id=case.case_id, observation=_observation(), expected_case_revision=2,
            idempotency_key="observation-overflow",
        )
        assert blocked["code"] == "FIFO_TRANSITION_OBSERVATION_LIMIT_REACHED"
        check = sqlite3.connect(repository.db_path)
        try:
            assert check.execute(
                "SELECT COUNT(*) FROM fifo_cost_supply_observations WHERE case_id=?",
                (case.case_id,),
            ).fetchone()[0] == 2000
            assert check.execute(
                "SELECT current_revision FROM fifo_cost_transition_cases WHERE case_id=?",
                (case.case_id,),
            ).fetchone()[0] == 2
        finally:
            check.close()
    finally:
        reset_current_tenant_user_id(tenant)


@pytest.mark.parametrize(
    "write_kind", ["case_create", "case_update", "declaration", "observation", "report"],
)
def test_injected_failure_rolls_back_each_transition_write(tmp_path, monkeypatch, write_kind):
    tenant = set_current_tenant_user_id(TENANT)
    try:
        repository = _repository(tmp_path)
        case = _case()
        if write_kind != "case_create":
            assert repository.save_transition_case(
                case=case, expected_revision=0, idempotency_key="case-create-0001",
            )["error"] is False
        if write_kind in {"observation", "report"}:
            assert repository.append_supply_declaration(
                declaration=_declaration(), expected_case_revision=1,
                idempotency_key="decl-append-0001",
            )["error"] is False
        expected_revision = {
            "case_create": 0, "case_update": 1,
            "declaration": 1, "observation": 2, "report": 2,
        }[write_kind]

        def fail_after_partial_write(*_args, **_kwargs):
            raise sqlite3.OperationalError("injected transition write failure")

        monkeypatch.setattr(
            FifoCostTransitionStore, "_insert_case_revision",
            staticmethod(fail_after_partial_write),
        )
        if write_kind == "case_create":
            result = repository.save_transition_case(
                case=case, expected_revision=0, idempotency_key="case-create-0001",
            )
        elif write_kind == "case_update":
            changed_case = replace(
                case, case_revision=2, updated_at="2026-11-07T12:01:00Z",
            )
            result = repository.save_transition_case(
                case=changed_case, expected_revision=1,
                idempotency_key="case-update-injected",
            )
        elif write_kind == "declaration":
            result = repository.append_supply_declaration(
                declaration=_declaration(), expected_case_revision=1,
                idempotency_key="decl-append-0001",
            )
        elif write_kind == "observation":
            result = repository.append_supply_observation(
                case_id=case.case_id, observation=_observation(),
                expected_case_revision=2, idempotency_key="observation-001",
            )
        else:
            result = repository.append_report_evidence(
                case_id=case.case_id, report=_report(),
                expected_case_revision=2, idempotency_key="report-import-0001",
            )
        assert result == {
            "error": True, "code": "FIFO_TRANSITION_STORAGE_UNAVAILABLE",
        }

        connection = sqlite3.connect(repository.db_path)
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_transition_cases WHERE case_id=?",
                (case.case_id,),
            ).fetchone()[0] == (0 if write_kind == "case_create" else 1)
            revision_row = connection.execute(
                "SELECT current_revision FROM fifo_cost_transition_cases WHERE case_id=?",
                (case.case_id,),
                ).fetchone()
            assert revision_row == (
                None if write_kind == "case_create" else (expected_revision,)
            )
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_transition_case_revisions WHERE case_id=?",
                (case.case_id,),
            ).fetchone()[0] == (0 if write_kind == "case_create" else expected_revision)
            for table, expected_count in (
                ("fifo_cost_supply_declarations", int(write_kind in {"observation", "report"})),
                ("fifo_cost_supply_observations", 0),
                ("fifo_cost_report_evidence", 0),
            ):
                assert connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE case_id=?",
                    (case.case_id,),
                ).fetchone()[0] == expected_count
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(tenant)


def test_pending_transition_keeps_legacy_mode_history_and_period_profit(tmp_path):
    class Finance:
        def get_daily_finance(self, _day, *, sku):
            return {
                "error": False, "sales_count": 1, "gross_sales": 100.0,
                "discount_points": 0.0, "net_accrual": 80.0,
                "commission": -10.0, "logistics": -20.0,
                "acquiring": -2.0, "other_fees": 0.0,
                "fee_breakdown": {}, "accrual_type_breakdown": {},
            }

        def get_daily_sale_posting_evidence(self, day):
            return {
                "error": False, "complete": True,
                "records": [{
                    "posting_number": "posting-transition-test", "sku": "sku-1",
                    "accrual_date": day,
                }],
            }

    class LegacyCost:
        def get_cost(self, _product_id):
            return 21.0

        def get_effective_cost_evidence(self, *_args, **_kwargs):
            return {
                "error": False, "effective_cost_confirmed": True,
                "historical_cost_confirmed": True, "cost_price": 21.0,
                "effective_from": "2026-01-01", "effective_through": "2026-12-31",
                "history_id": "test-legacy-history",
                "cost_basis": "SELLER_CONFIRMED_BOUNDED_PERIOD",
                "source": "SELLER_CONFIRMED_OPERATIONAL_HISTORY",
            }

    class PeriodProfit(PeriodProfitEffectiveCostSaleQuantitySummaryService):
        def _load_period_skus(self, *_args, **_kwargs):
            return {"map": {}, "expected": set(), "fatal": None}

        def _load_direct_finance_quantity_map(self, *_args, **_kwargs):
            return {"map": {}, "expected": set(), "fatal": None}

        def _load_realization_quantity_map(self, *_args, **_kwargs):
            return {("posting-transition-test", "sku-1"): 1}

        def _load_fbo_list_quantity_map(self, *_args, **_kwargs):
            return {}

        def _load_posting_quantity_for_identity(self, *_args, **_kwargs):
            return None

    tenant = set_current_tenant_user_id(TENANT)
    try:
        repository = _repository(tmp_path)
        fifo_source = FifoCostPeriodProfitSourceService(
            repository=repository, tenant_scope_provider=lambda: TENANT,
        )
        period_profit = PeriodProfit(
            finance_service=Finance(), cost_service=LegacyCost(), tax_rate=0.06,
            fifo_cost_source_service=fifo_source,
        )
        product = [{
            "product_id": "product-1", "offer_id": "offer-1", "sku": "sku-1",
        }]
        baseline_profit = period_profit.calculate(
            date(2026, 11, 6), date(2026, 11, 6), product,
        )
        baseline_mode = repository.read_cost_mode_status(
            store_id=STORE, product_id="product-1", offer_id="offer-1", sku="sku-1",
        )
        baseline_history = repository.read_cost_history_snapshot(
            store_id=STORE, product_id="product-1", offer_id="offer-1", sku="sku-1",
        )
        assert baseline_mode["code"] == "FIFO_COST_MODE_LEGACY"
        assert baseline_history["code"] == "FIFO_HISTORY_NOT_INITIALIZED"
        assert baseline_profit["error"] is False, baseline_profit
        assert baseline_profit["product_cost"] == 21.0
        assert baseline_profit["profit"] == 53.0

        assert repository.save_transition_case(
            case=_case(), expected_revision=0, idempotency_key="case-create-0001",
        )["error"] is False

        assert repository.read_cost_mode_status(
            store_id=STORE, product_id="product-1", offer_id="offer-1", sku="sku-1",
        ) == baseline_mode
        assert repository.read_cost_history_snapshot(
            store_id=STORE, product_id="product-1", offer_id="offer-1", sku="sku-1",
        ) == baseline_history
        assert period_profit.calculate(
            date(2026, 11, 6), date(2026, 11, 6), product,
        ) == baseline_profit
        connection = repository.get_connection()
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_streams WHERE store_id=? AND sku=?",
                (STORE, "sku-1"),
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_transition_cases WHERE store_id=? AND sku=?",
                (STORE, "sku-1"),
            ).fetchone()[0] == 1
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(tenant)
