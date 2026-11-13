from datetime import datetime, timezone
import json
import sqlite3

from cryptography.fernet import Fernet

from services.fifo_cost_repository import FifoCostRepository
from services.fifo_cost_transition_contracts import (
    CostInputMode,
    EvidenceCompleteness,
    EvidenceSourceKind,
    ScopeIdentity,
    TransitionCase,
    TransitionMetadata,
    TransitionReasonCode,
    TransitionState,
    UnknownValue,
)
from services.fifo_cost_transition_service import FifoCostTransitionService
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_cipher_provider import decrypt_tenant_value
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)


def _case(*, case_id="case-supply-0001", store_id="store-a", sku="sku-1", total=6982):
    metadata = TransitionMetadata(
        scope=ScopeIdentity(
            owner_id="owner-a", store_id=store_id, sku=sku,
            product_id="product-1", offer_id="offer-1",
        ),
        source_kind=EvidenceSourceKind.OWNER_INPUT,
        completeness=EvidenceCompleteness.PARTIAL,
        source_fingerprint="a" * 64,
    )
    return TransitionCase(
        metadata=metadata,
        case_id=case_id,
        case_revision=1,
        state=TransitionState.DRAFT,
        created_at="2026-11-08T10:00:00Z",
        updated_at="2026-11-08T10:00:00Z",
        dispatch_date="2026-11-05",
        old_unit_cost_rub="21.00",
        new_unit_cost_rub="14.65",
        cost_input_mode=CostInputMode.TOTAL_LANDED,
        cost_components=None,
        owner_old_home_units=0,
        owner_old_transit_units=0,
        new_home_quantity=None,
        declared_shipped_units=total,
        unknown_values={
            "new_home_quantity": UnknownValue(
                TransitionReasonCode.SOURCE_PROOF_UNAVAILABLE,
                EvidenceSourceKind.OWNER_INPUT,
            ),
        },
    )


def _open_case(repository, store_id="store-a", *, sku="sku-1", case_id="case-supply-0001", total=6982):
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", store_id))
    try:
        service = FifoCostTransitionService(repository)
        result = service.create_case(
            case=_case(case_id=case_id, store_id=store_id, sku=sku, total=total),
            idempotency_key=f"create-{case_id}",
        )
        assert result["error"] is False, result
        return service
    finally:
        reset_current_tenant_user_id(tenant)


def _repository(path):
    return FifoCostRepository(
        db_path=path,
        now_provider=lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc),
    )


def _declare(service, *, store_id="store-a", sku="sku-1", case_id="case-supply-0001",
             reference_id="2000070135564", quantity=100, revision=1, key="declare-supply-01",
             reference_kind="SUPPLY"):
    return service.declare_supply(
        case_id=case_id,
        store_id=store_id,
        product_id="product-1",
        offer_id="offer-1",
        sku=sku,
        reference_kind=reference_kind,
        reference_id=reference_id,
        declared_shipped_units=quantity,
        dispatch_date="2026-11-05",
        expected_case_revision=revision,
        idempotency_key=key,
    )


def test_three_typed_supply_declarations_reconcile_to_owner_total_without_ids(tmp_path, monkeypatch):
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", key)
    repository = _repository(tmp_path / "fifo-supplies.sqlite")
    service = _open_case(repository)
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        for index, (reference_id, quantity) in enumerate(
            (("220000000001", 6234), ("220000000002", 600), ("220000000003", 148)),
            start=1,
        ):
            result = _declare(
                service,
                reference_id=reference_id,
                quantity=quantity,
                revision=index,
                key=f"declare-supply-{index:02d}",
            )
            assert result["error"] is False, result

        manifest = service.get_supply_manifest(
            case_id="case-supply-0001", store_id="store-a",
            product_id="product-1", offer_id="offer-1", sku="sku-1",
        )
        assert manifest["error"] is False, manifest
        assert manifest["owner_declared_total"] == 6982
        assert manifest["known_assigned_units"] == 6982
        assert manifest["assignment_complete"] is True
        assert manifest["undistributed_units"] == 0
        assert len(manifest["declarations"]) == 3
        assert {item["reference_kind"] for item in manifest["declarations"]} == {"SUPPLY"}
        assert {item["lookup_status"] for item in manifest["declarations"]} == {"AVAILABLE"}
        serialized = json.dumps(manifest)
        assert "220000000001" not in serialized
        assert "reference_digest" not in serialized
        assert "encrypted_lookup_reference" not in serialized

        connection = sqlite3.connect(repository.db_path)
        try:
            rows = connection.execute(
                "SELECT encrypted_lookup_reference, payload_json FROM fifo_cost_supply_declarations "
                "WHERE case_id=? ORDER BY declared_shipped_units DESC",
                ("case-supply-0001",),
            ).fetchall()
            assert len(rows) == 3
            decrypted = {decrypt_tenant_value(row[0]) for row in rows}
            assert decrypted == {"220000000001", "220000000002", "220000000003"}
            assert all("22000000000" not in row[1] for row in rows)
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(tenant)


def test_undistributed_units_remain_a_number_not_a_synthetic_supply(tmp_path, monkeypatch):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    repository = _repository(tmp_path / "fifo-remainder.sqlite")
    service = _open_case(repository)
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        result = _declare(service, quantity=6234)
        assert result["error"] is False, result
        manifest = service.get_supply_manifest(
            case_id="case-supply-0001", store_id="store-a",
            product_id="product-1", offer_id="offer-1", sku="sku-1",
        )
        assert manifest["known_assigned_units"] == 6234
        assert manifest["undistributed_units"] == 748
        assert len(manifest["declarations"]) == 1
        assert all(item["declaration_id"] != "undistributed" for item in manifest["declarations"])
    finally:
        reset_current_tenant_user_id(tenant)


def test_duplicate_and_mixed_sku_supply_references_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    repository = _repository(tmp_path / "fifo-duplicate.sqlite")
    service = _open_case(repository)
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        assert _declare(service, reference_id="220000000099", quantity=100)["error"] is False
        duplicate = _declare(
            service, reference_id="220000000099", quantity=100, revision=2,
            key="declare-supply-duplicate",
        )
        assert duplicate["code"] == "FIFO_TRANSITION_SUPPLY_REFERENCE_DUPLICATE"

        other_service = _open_case(
            repository, sku="sku-2", case_id="case-supply-0002",
        )
        mixed_sku = _declare(
            other_service, sku="sku-2", case_id="case-supply-0002",
            reference_id="220000000099", quantity=100, key="declare-mixed-sku-01",
        )
        assert mixed_sku["code"] == "FIFO_TRANSITION_SUPPLY_SKU_CONFLICT"
    finally:
        reset_current_tenant_user_id(tenant)


def test_same_reference_id_is_scoped_by_store(tmp_path, monkeypatch):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    repository = _repository(tmp_path / "fifo-store-scope.sqlite")
    first_service = _open_case(repository, store_id="store-a", case_id="case-store-a")
    second_service = _open_case(repository, store_id="store-b", case_id="case-store-b")

    for store_id, case_id, service, key in (
        ("store-a", "case-store-a", first_service, "declare-store-a-01"),
        ("store-b", "case-store-b", second_service, "declare-store-b-01"),
    ):
        tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", store_id))
        try:
            result = _declare(
                service, store_id=store_id, case_id=case_id,
                reference_id="220000000099", quantity=100, key=key,
            )
            assert result["error"] is False, result
        finally:
            reset_current_tenant_user_id(tenant)


def test_order_and_supply_are_typed_separately_and_act_is_not_a_reference(tmp_path, monkeypatch):
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    repository = _repository(tmp_path / "fifo-reference-types.sqlite")
    service = _open_case(repository, total=200)
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        order = _declare(
            service, reference_id="220000000099", quantity=100,
            reference_kind="ORDER", key="declare-order-0001",
        )
        assert order["error"] is False, order
        supply = _declare(
            service, reference_id="220000000099", quantity=100, revision=2,
            reference_kind="SUPPLY", key="declare-supply-typed",
        )
        assert supply["error"] is False, supply
        act = _declare(
            service, reference_id="220000000099", quantity=0, revision=3,
            reference_kind="ACT", key="declare-act-typed",
        )
        assert act["code"] == "FIFO_TRANSITION_DECLARATION_INVALID"

        manifest = service.get_supply_manifest(
            case_id="case-supply-0001", store_id="store-a",
            product_id="product-1", offer_id="offer-1", sku="sku-1",
        )
        assert {item["reference_kind"] for item in manifest["declarations"]} == {"ORDER", "SUPPLY"}
    finally:
        reset_current_tenant_user_id(tenant)


def test_missing_cipher_preserves_declaration_but_disables_lookup(tmp_path, monkeypatch):
    monkeypatch.delenv("OZON_CREDENTIAL_MASTER_KEY", raising=False)
    repository = _repository(tmp_path / "fifo-no-cipher.sqlite")
    service = _open_case(repository, total=6982)
    tenant = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        result = _declare(service, reference_id="220000000099", quantity=148)
        assert result["error"] is False, result
        manifest = service.get_supply_manifest(
            case_id="case-supply-0001", store_id="store-a",
            product_id="product-1", offer_id="offer-1", sku="sku-1",
        )
        assert manifest["declarations"][0]["declared_shipped_units"] == 148
        assert manifest["declarations"][0]["lookup_status"] == "LOOKUP_REFERENCE_UNAVAILABLE"
        assert manifest["undistributed_units"] == 6834
        evidence = repository.read_transition_evidence(
            case_id="case-supply-0001", store_id="store-a", product_id="product-1",
            offer_id="offer-1", sku="sku-1", kind="SUPPLY_DECLARATION",
        )
        assert evidence["items"][0]["payload"]["unknown_values"]["lookup_reference"] == {
            "reason_code": "LOOKUP_REFERENCE_UNAVAILABLE",
            "source_kind": "OWNER_INPUT",
        }
        connection = sqlite3.connect(repository.db_path)
        try:
            assert connection.execute(
                "SELECT encrypted_lookup_reference FROM fifo_cost_supply_declarations"
            ).fetchone()[0] is None
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(tenant)
