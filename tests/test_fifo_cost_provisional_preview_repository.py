from services.fifo_cost_repository import FifoCostRepository
from services.ozon_account_repository import make_store_tenant_scope
from services.tenant_context import (
    reset_current_tenant_user_id,
    set_current_tenant_user_id,
)
from datetime import datetime, timedelta, timezone


def _seed_case(connection, scope, *, current_revision=1, current_state="AWAITING_EVIDENCE"):
    connection.execute(
        """INSERT INTO fifo_cost_transition_cases (
            case_id, schema_version, owner_fingerprint, tenant_fingerprint,
            store_id, product_id, offer_id, sku, current_revision,
            current_state, supply_total_mode, created_at, updated_at
        ) VALUES ('case-pf21-01', 1, ?, ?, 'store-a', 'product-a', 'offer-a',
                  'sku-a', ?, ?, 'LEGACY_OWNER_TOTAL', 'now', 'now')""",
        (scope["owner_fingerprint"], scope["tenant_fingerprint"],
         current_revision, current_state),
    )
    connection.execute(
        """INSERT INTO fifo_cost_transition_case_revisions (
            revision_id, case_id, case_revision, schema_version, state,
            payload_json, payload_fingerprint, idempotency_key, created_at, updated_at
        ) VALUES (?, 'case-pf21-01', ?, 1, ?, '{}', ?, ?, 'now', 'now')""",
        (f"revision-pf21-{current_revision}", current_revision, current_state,
         "c" * 64, f"revision-key-pf21-{current_revision}"),
    )


def _payload(input_fingerprint="f" * 64):
    return {
        "schema_version": 1,
        "model_kind": "SUMMARY_RANGE",
        "currency": "RUB",
        "method": "AGGREGATE_SUMMARY_V1",
        "policy_version": "fifo-provisional-summary-v1",
        "period_from": "2026-11-01",
        "period_to": "2026-11-30",
        "input_fingerprint": input_fingerprint,
        "evidence_fingerprints": ["1" * 64, "2" * 64],
        "assumptions": {
            "opening_all_old": True,
            "all_period_supply_receipts_new": True,
            "closing_old_min": None,
            "closing_old_max": None,
            "timeline_coverage_confirmed": None,
        },
        "rates": {"old_unit_cost_rub": "21.00", "new_unit_cost_rub": "14.65"},
        "result": {
            "redeemed_units": 5931,
            "old_sold_min": 3669,
            "old_sold_max": 3703,
            "new_sold_min": 2228,
            "new_sold_max": 2262,
            "gross_cogs_low_rub": "110187.30",
            "gross_cogs_high_rub": "110403.20",
        },
    }


def _save(repository, *, input_fingerprint="f" * 64, idempotency_key="prov1_" + "f" * 64,
          preview_id="preview-pf21-01", case_revision=1, sku="sku-a"):
    payload = _payload(input_fingerprint)
    return repository.append_provisional_preview(
        preview_id=preview_id,
        case_id="case-pf21-01",
        case_revision=case_revision,
        store_id="store-a",
        product_id="product-a",
        offer_id="offer-a",
        sku=sku,
        input_fingerprint=input_fingerprint,
        idempotency_key=idempotency_key,
        payload=payload,
    )


def test_append_saved_preview_is_exactly_scoped_and_idempotent(tmp_path):
    repo = FifoCostRepository(db_path=tmp_path / "saved.sqlite")
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        connection = repo.get_connection()
        try:
            _seed_case(connection, repo._tenant_scope("store-a"))
        finally:
            connection.close()

        first = _save(repo)
        second = _save(repo, preview_id="preview-pf21-retry")

        assert first["error"] is False, first
        assert first["created"] is True
        assert second["error"] is False, second
        assert second["created"] is False
        assert second["item"]["preview_id"] == first["item"]["preview_id"]
        assert second["item"]["payload"] == _payload()
        conflict = _save(
            repo, input_fingerprint="9" * 64,
            idempotency_key="prov1_" + "f" * 64,
            preview_id="preview-pf21-conflict",
        )
        assert conflict == {
            "error": True, "code": "FIFO_PROVISIONAL_IDEMPOTENCY_CONFLICT",
        }
        connection = repo.get_connection()
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_provisional_previews"
            ).fetchone()[0] == 1
            assert connection.execute(
                "SELECT identity_fingerprint FROM fifo_cost_provisional_previews"
            ).fetchone()[0] == first["item"]["identity_fingerprint"]
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_saved_preview_rejects_stale_case_revision_and_cross_identity(tmp_path):
    repo = FifoCostRepository(db_path=tmp_path / "stale.sqlite")
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        connection = repo.get_connection()
        try:
            _seed_case(connection, repo._tenant_scope("store-a"))
        finally:
            connection.close()

        wrong_sku = _save(repo, sku="sku-other")
        assert wrong_sku == {
            "error": True, "code": "FIFO_PROVISIONAL_CASE_SCOPE_MISMATCH",
        }
        token_other = set_current_tenant_user_id(
            make_store_tenant_scope("owner-other", "store-a")
        )
        try:
            wrong_owner = _save(repo)
        finally:
            reset_current_tenant_user_id(token_other)
        assert wrong_owner["error"] is True

        connection = repo.get_connection()
        try:
            connection.execute(
                "UPDATE fifo_cost_transition_cases SET current_revision=2 WHERE case_id='case-pf21-01'"
            )
            connection.execute(
                """INSERT INTO fifo_cost_transition_case_revisions (
                    revision_id, case_id, case_revision, schema_version, state,
                    payload_json, payload_fingerprint, idempotency_key, created_at, updated_at
                ) VALUES ('revision-pf21-2', 'case-pf21-01', 2, 1,
                          'AWAITING_EVIDENCE', '{}', ?, 'revision-key-pf21-2', 'now', 'now')""",
                ("d" * 64,),
            )
        finally:
            connection.close()

        stale = _save(repo, preview_id="preview-pf21-stale")
        assert stale == {"error": True, "code": "FIFO_PROVISIONAL_CASE_STALE"}
        connection = repo.get_connection()
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_provisional_previews"
            ).fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_saved_preview_payload_is_allowlisted_and_rejects_untrusted_fields(tmp_path):
    repo = FifoCostRepository(db_path=tmp_path / "invalid-payload.sqlite")
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        connection = repo.get_connection()
        try:
            _seed_case(connection, repo._tenant_scope("store-a"))
        finally:
            connection.close()

        payload = _payload()
        payload["raw_csv"] = "personal or source data must never be persisted"
        result = repo.append_provisional_preview(
            preview_id="preview-pf21-invalid",
            case_id="case-pf21-01",
            case_revision=1,
            store_id="store-a",
            product_id="product-a",
            offer_id="offer-a",
            sku="sku-a",
            input_fingerprint="f" * 64,
            idempotency_key="prov1_" + "f" * 64,
            payload=payload,
        )
        assert result == {"error": True, "code": "FIFO_PROVISIONAL_PREVIEW_PAYLOAD_INVALID"}
    finally:
        reset_current_tenant_user_id(token)


def test_saved_preview_requires_complete_model_contract_and_iso_dates(tmp_path):
    repo = FifoCostRepository(db_path=tmp_path / "contract.sqlite")
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        connection = repo.get_connection()
        try:
            _seed_case(connection, repo._tenant_scope("store-a"))
        finally:
            connection.close()

        invalid_payloads = []
        wrong_method = _payload()
        wrong_method["method"] = "EVENT_TIMELINE_V1"
        invalid_payloads.append(wrong_method)
        missing_result = _payload()
        del missing_result["result"]["gross_cogs_high_rub"]
        invalid_payloads.append(missing_result)
        non_iso_date = _payload()
        non_iso_date["period_from"] = "20261101"
        invalid_payloads.append(non_iso_date)

        for index, payload in enumerate(invalid_payloads):
            result = repo.append_provisional_preview(
                preview_id=f"preview-pf21-invalid-{index}",
                case_id="case-pf21-01",
                case_revision=1,
                store_id="store-a",
                product_id="product-a",
                offer_id="offer-a",
                sku="sku-a",
                input_fingerprint="f" * 64,
                idempotency_key=f"prov1-invalid-{index}",
                payload=payload,
            )
            assert result == {
                "error": True, "code": "FIFO_PROVISIONAL_PREVIEW_PAYLOAD_INVALID",
            }

        connection = repo.get_connection()
        try:
            assert connection.execute(
                "SELECT COUNT(*) FROM fifo_cost_provisional_previews"
            ).fetchone()[0] == 0
        finally:
            connection.close()
    finally:
        reset_current_tenant_user_id(token)


def test_closed_transition_case_cannot_accept_new_saved_estimate(tmp_path):
    repo = FifoCostRepository(db_path=tmp_path / "closed.sqlite")
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        connection = repo.get_connection()
        try:
            _seed_case(
                connection, repo._tenant_scope("store-a"), current_state="APPLIED",
            )
        finally:
            connection.close()

        result = _save(repo)
        assert result == {"error": True, "code": "FIFO_PROVISIONAL_CASE_NOT_EDITABLE"}
    finally:
        reset_current_tenant_user_id(token)


def test_saved_preview_history_is_ordered_paginated_and_scope_bound(tmp_path):
    clock = [datetime(2026, 11, 22, tzinfo=timezone.utc)]

    def now():
        value = clock[0]
        clock[0] += timedelta(seconds=1)
        return value

    repo = FifoCostRepository(db_path=tmp_path / "history.sqlite", now_provider=now)
    token = set_current_tenant_user_id(make_store_tenant_scope("owner-a", "store-a"))
    try:
        connection = repo.get_connection()
        try:
            _seed_case(connection, repo._tenant_scope("store-a"))
        finally:
            connection.close()

        for index in range(10):
            fingerprint = f"{index + 1:064x}"
            result = _save(
                repo,
                input_fingerprint=fingerprint,
                idempotency_key="prov1_" + fingerprint,
                preview_id=f"preview-pf21-{index:02d}",
            )
            assert result["error"] is False, result

        first = repo.read_provisional_preview_history(
            case_id="case-pf21-01", store_id="store-a", product_id="product-a",
            offer_id="offer-a", sku="sku-a", limit=4, offset=0,
        )
        second = repo.read_provisional_preview_history(
            case_id="case-pf21-01", store_id="store-a", product_id="product-a",
            offer_id="offer-a", sku="sku-a", limit=4, offset=4,
        )
        assert first["error"] is False and first["total"] == 10
        assert [item["preview_id"] for item in first["items"]] == [
            "preview-pf21-09", "preview-pf21-08", "preview-pf21-07", "preview-pf21-06",
        ]
        assert [item["preview_id"] for item in second["items"]] == [
            "preview-pf21-05", "preview-pf21-04", "preview-pf21-03", "preview-pf21-02",
        ]
        assert all("owner_fingerprint" not in item and "tenant_fingerprint" not in item
                   for item in first["items"])
        wrong_identity = repo.read_provisional_preview_history(
            case_id="case-pf21-01", store_id="store-a", product_id="other-product",
            offer_id="offer-a", sku="sku-a",
        )
        assert wrong_identity == {
            "error": True, "code": "FIFO_PROVISIONAL_CASE_SCOPE_MISMATCH",
        }
        token_other = set_current_tenant_user_id(make_store_tenant_scope("owner-other", "store-a"))
        try:
            wrong_owner = repo.read_provisional_preview_history(
                case_id="case-pf21-01", store_id="store-a", product_id="product-a",
                offer_id="offer-a", sku="sku-a",
            )
        finally:
            reset_current_tenant_user_id(token_other)
        assert wrong_owner == {
            "error": True, "code": "FIFO_PROVISIONAL_CASE_SCOPE_MISMATCH",
        }
        invalid_offset = repo.read_provisional_preview_history(
            case_id="case-pf21-01", store_id="store-a", product_id="product-a",
            offer_id="offer-a", sku="sku-a", offset=True,
        )
        assert invalid_offset == {
            "error": True, "code": "FIFO_PROVISIONAL_HISTORY_OFFSET_INVALID",
        }
    finally:
        reset_current_tenant_user_id(token)
