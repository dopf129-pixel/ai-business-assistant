import services.return_inventory_recovery_repository as recovery_module

from period_profit_coverage import (
    build_period_profit_coverage,
)
from period_profit_response import (
    build_period_profit_response,
)
from services.period_profit_return_cogs_recovery_evidence_service import (
    PeriodProfitReturnCogsRecoveryEvidenceService,
)
from services.return_inventory_recovery_repository import (
    ReturnInventoryRecoveryRepository,
)


class Costs:
    def get_cost(
        self,
        product_id,
    ):
        return (
            str(product_id),
            "offer-a",
            "42",
            30.0,
            "RUB",
            None,
        )

    def get_historical_cost_evidence(
        self,
        **kwargs,
    ):
        return {
            "error": False,
            "status": (
                "PRODUCT_COST_HISTORY_READY"
            ),
            "history_id": 1,
            "product_id": "10",
            "sku": "42",
            "offer_id": "offer-a",
            "cost_price": 21.0,
            "currency": "RUB",
            "effective_from": (
                "2026-08-01"
            ),
            "source": "SELLER_CONFIRMED",
            "recorded_at": (
                "2026-09-03 10:00:00"
            ),
            "at_date": kwargs.get(
                "at_date"
            ),
            "historical_cost_confirmed": True,
        }


class Lineage:
    def __init__(
        self,
        records,
        complete=True,
    ):
        self.records = list(
            records
        )
        self.complete = complete

    def analyze(
        self,
        evidence,
    ):
        return {
            "error": False,
            "status": (
                "PERIOD_PROFIT_RETURN_SALE_LINEAGE_EVIDENCE_READY"
                if self.complete
                else "PERIOD_PROFIT_RETURN_SALE_LINEAGE_EVIDENCE_PARTIAL"
            ),
            "finance_period_complete": (
                self.complete
            ),
            "matching_basis": (
                "OZON_POSTING_NUMBER_AND_SKU_POSITIVE_SALE_ACCRUAL"
            ),
            "lineage_records": list(
                self.records
            ),
        }


class Recovery:
    def __init__(
        self,
        values,
    ):
        self.values = dict(
            values
        )
        self.calls = []

    def get_latest_recovery(
        self,
        **kwargs,
    ):
        self.calls.append(
            dict(kwargs)
        )
        value = self.values.get(
            kwargs.get("return_id")
        )
        if isinstance(
            value,
            Exception,
        ):
            raise value
        if value is None:
            return {
                "error": False,
                "status": (
                    "RETURN_INVENTORY_RECOVERY_MISSING"
                ),
                "inventory_recovery_confirmed": False,
                "recovery_state": None,
                "quantity": None,
                "confirmed_on": None,
                "source": None,
            }
        return dict(
            value
        )


def _ready_recovery(
    return_id="1",
    quantity=1,
    state="SALEABLE_RESTORED",
):
    return {
        "error": False,
        "status": (
            "RETURN_INVENTORY_RECOVERY_READY"
        ),
        "history_id": 1,
        "return_id": str(
            return_id
        ),
        "posting_number": (
            f"p-{return_id}"
        ),
        "sku": "42",
        "quantity": quantity,
        "recovery_state": state,
        "confirmed_on": "2026-08-20",
        "source": "SELLER_CONFIRMED",
        "recorded_at": (
            "2026-09-03 10:00:00"
        ),
        "inventory_recovery_confirmed": True,
    }


def _return_record(
    return_id=1,
    quantity=1,
    compensation=None,
):
    result = {
        "id": return_id,
        "posting_number": (
            f"p-{return_id}"
        ),
        "sku": "42",
        "offer_id": "offer-a",
        "quantity": quantity,
        "type": "ClientReturn",
        "visual_status_sys_name": (
            "ArrivedAtReturnPlace"
        ),
    }
    if compensation is not None:
        result[
            "compensation_status_sys_name"
        ] = compensation
    return result


def _return_evidence(
    records,
    complete=True,
):
    return {
        "error": False,
        "status": (
            "PERIOD_PROFIT_RETURN_EVIDENCE_READY"
            if complete
            else "PERIOD_PROFIT_RETURN_EVIDENCE_PARTIAL"
        ),
        "date_from": "2026-08-01",
        "date_to": "2026-08-31",
        "complete": complete,
        "return_record_count_exact": (
            complete
        ),
        "records": list(
            records
        ),
    }


def _lineage_record(
    return_id=1,
):
    return {
        "return_id": return_id,
        "posting_number": (
            f"p-{return_id}"
        ),
        "sku": "42",
        "lineage_status": (
            "MATCHED_IN_SELECTED_PERIOD"
        ),
        "matched_sale_accrual_date": (
            "2026-08-15"
        ),
    }


def _products():
    return [
        {
            "product_id": "10",
            "offer_id": "offer-a",
            "sku": "42",
        },
    ]


def _summary():
    return {
        "error": False,
        "status": (
            "PERIOD_PROFIT_SUMMARY_READY"
        ),
        "date_from": "2026-08-01",
        "date_to": "2026-08-31",
        "revenue": 1000.0,
        "net_accrual": 700.0,
        "commission": -100.0,
        "logistics": -100.0,
        "acquiring": -10.0,
        "other_fees": -90.0,
        "product_cost": 300.0,
        "tax": 60.0,
        "profit": 340.0,
        "margin_percent": 34.0,
        "fee_breakdown": {},
        "returns_included": False,
        "advertising_included": False,
        "storage_included": False,
        "fee_components_included": True,
        "account_level_ozon_accruals_included": True,
        "product_revenue_reconciled": True,
        "ozon_account_reconciliation": 0.0,
        "profit_scope": (
            "OZON_ACCOUNT_ACCRUALS_COST_AND_CONFIGURED_TAX_V2"
        ),
    }


def _repository(
    monkeypatch,
    tmp_path,
):
    db = tmp_path / "recovery.db"
    monkeypatch.setattr(
        recovery_module,
        "DB_NAME",
        str(db),
    )
    return (
        ReturnInventoryRecoveryRepository()
    )


def _service(
    recovery,
    return_ids=(1,),
):
    return (
        PeriodProfitReturnCogsRecoveryEvidenceService(
            Costs(),
            Lineage([
                _lineage_record(
                    return_id=value
                )
                for value in return_ids
            ]),
            recovery,
        )
    )


def test_v1291_explicit_saleable_recovery_is_persisted_and_read(
    monkeypatch,
    tmp_path,
):
    repository = _repository(
        monkeypatch,
        tmp_path,
    )

    recorded = repository.record_recovery(
        return_id="1",
        posting_number="p-1",
        sku="42",
        quantity=2,
        recovery_state=(
            "SALEABLE_RESTORED"
        ),
        confirmed_on="2026-08-20",
    )
    loaded = repository.get_latest_recovery(
        return_id="1",
        posting_number="p-1",
        sku="42",
    )

    assert recorded["error"] is False
    assert (
        recorded["recovery_state"]
        == "SALEABLE_RESTORED"
    )
    assert loaded["error"] is False
    assert (
        loaded["status"]
        == "RETURN_INVENTORY_RECOVERY_READY"
    )
    assert loaded["quantity"] == 2
    assert (
        loaded[
            "inventory_recovery_confirmed"
        ]
        is True
    )


def test_v1292_non_saleable_is_explicit_state_not_missing(
    monkeypatch,
    tmp_path,
):
    repository = _repository(
        monkeypatch,
        tmp_path,
    )

    repository.record_recovery(
        "1",
        "p-1",
        "42",
        1,
        "NON_SALEABLE",
        "2026-08-20",
    )
    loaded = repository.get_latest_recovery(
        "1",
        "p-1",
        "42",
    )

    assert (
        loaded["recovery_state"]
        == "NON_SALEABLE"
    )
    assert (
        loaded[
            "inventory_recovery_confirmed"
        ]
        is True
    )


def test_v1293_invalid_state_and_quantity_fail_closed(
    monkeypatch,
    tmp_path,
):
    repository = _repository(
        monkeypatch,
        tmp_path,
    )

    invalid_state = (
        repository.record_recovery(
            "1",
            "p-1",
            "42",
            1,
            "UNKNOWN",
            "2026-08-20",
        )
    )
    invalid_quantity = (
        repository.record_recovery(
            "2",
            "p-2",
            "42",
            0,
            "SALEABLE_RESTORED",
            "2026-08-20",
        )
    )

    assert invalid_state["error"] is True
    assert (
        invalid_state["code"]
        == "RETURN_INVENTORY_RECOVERY_INPUT_INVALID"
    )
    assert invalid_quantity["error"] is True


def test_v1294_duplicate_return_date_conflicts_instead_of_overwriting(
    monkeypatch,
    tmp_path,
):
    repository = _repository(
        monkeypatch,
        tmp_path,
    )

    first = repository.record_recovery(
        "1",
        "p-1",
        "42",
        1,
        "NON_SALEABLE",
        "2026-08-20",
    )
    duplicate = (
        repository.record_recovery(
            "1",
            "p-1",
            "42",
            1,
            "SALEABLE_RESTORED",
            "2026-08-20",
        )
    )
    loaded = repository.get_latest_recovery(
        "1",
        "p-1",
        "42",
    )

    assert first["error"] is False
    assert duplicate["error"] is True
    assert (
        duplicate["code"]
        == "RETURN_INVENTORY_RECOVERY_VERSION_CONFLICT"
    )
    assert (
        loaded["recovery_state"]
        == "NON_SALEABLE"
    )


def test_v1295_identity_drift_for_same_return_is_conflict(
    monkeypatch,
    tmp_path,
):
    repository = _repository(
        monkeypatch,
        tmp_path,
    )

    repository.record_recovery(
        "1",
        "p-1",
        "42",
        1,
        "NON_SALEABLE",
        "2026-08-20",
    )
    repository.record_recovery(
        "1",
        "p-other",
        "99",
        1,
        "SALEABLE_RESTORED",
        "2026-08-21",
    )

    loaded = repository.get_latest_recovery(
        "1",
        "p-1",
        "42",
    )

    assert (
        loaded["status"]
        == "RETURN_INVENTORY_RECOVERY_IDENTITY_CONFLICT"
    )
    assert (
        loaded[
            "inventory_recovery_confirmed"
        ]
        is False
    )


def test_v1296_missing_recovery_stays_unknown_without_stock_inference(
    monkeypatch,
    tmp_path,
):
    repository = _repository(
        monkeypatch,
        tmp_path,
    )

    loaded = repository.get_latest_recovery(
        "1",
        "p-1",
        "42",
    )

    assert loaded["error"] is False
    assert (
        loaded["status"]
        == "RETURN_INVENTORY_RECOVERY_MISSING"
    )
    assert loaded["recovery_state"] is None
    assert (
        loaded[
            "inventory_recovery_confirmed"
        ]
        is False
    )


def test_v1297_saleable_recovery_confirms_state_but_never_changes_profit():
    recovery = Recovery({
        "1": _ready_recovery(
            quantity=2,
        ),
    })
    service = _service(
        recovery
    )

    result = service.analyze(
        _return_evidence([
            _return_record(
                quantity=2,
            ),
        ]),
        _products(),
    )

    assert (
        result[
            "originating_sale_period_confirmed"
        ]
        is True
    )
    assert (
        result[
            "historical_cost_basis_confirmed"
        ]
        is True
    )
    assert (
        result[
            "inventory_recovery_state_complete"
        ]
        is True
    )
    assert (
        result[
            "saleable_inventory_recovery_confirmed"
        ]
        is True
    )
    assert (
        result[
            "inventory_recovery_saleable_candidate_record_count"
        ]
        == 1
    )
    assert (
        result[
            "candidate_value_at_historical_cost"
        ]
        == 42.0
    )
    assert (
        result[
            "confirmed_cogs_recovery_amount"
        ]
        == 0.0
    )
    assert (
        result[
            "recovery_period_attribution_confirmed"
        ]
        is False
    )
    assert (
        result["profit_adjustment_allowed"]
        is False
    )


def test_v1298_quantity_mismatch_never_confirms_saleable_recovery():
    recovery = Recovery({
        "1": _ready_recovery(
            quantity=1,
        ),
    })
    service = _service(
        recovery
    )

    result = service.analyze(
        _return_evidence([
            _return_record(
                quantity=2,
            ),
        ]),
        _products(),
    )

    assert (
        result[
            "inventory_recovery_quantity_mismatch_candidate_record_count"
        ]
        == 1
    )
    assert (
        result[
            "inventory_recovery_state_complete"
        ]
        is False
    )
    assert (
        result[
            "saleable_inventory_recovery_confirmed"
        ]
        is False
    )
    assert (
        result["profit_adjustment_allowed"]
        is False
    )


def test_v1299_non_saleable_complete_state_blocks_saleable_recovery():
    recovery = Recovery({
        "1": _ready_recovery(
            state="NON_SALEABLE",
        ),
    })
    service = _service(
        recovery
    )

    result = service.analyze(
        _return_evidence([
            _return_record(),
        ]),
        _products(),
    )

    assert (
        result[
            "inventory_recovery_state_complete"
        ]
        is True
    )
    assert (
        result[
            "inventory_recovery_non_saleable_candidate_record_count"
        ]
        == 1
    )
    assert (
        result[
            "saleable_inventory_recovery_confirmed"
        ]
        is False
    )
    assert (
        result[
            "confirmed_cogs_recovery_amount"
        ]
        == 0.0
    )


def test_v1300_compensated_return_is_not_inventory_recovery_candidate():
    recovery = Recovery({
        "1": _ready_recovery(),
    })
    service = _service(
        recovery
    )

    result = service.analyze(
        _return_evidence([
            _return_record(
                compensation="Received",
            ),
        ]),
        _products(),
    )

    assert result["compensated_units"] == 1
    assert (
        result["candidate_recovery_units"]
        == 0
    )
    assert (
        result[
            "inventory_recovery_candidate_record_count"
        ]
        == 0
    )
    assert recovery.calls == []
    assert (
        result[
            "saleable_inventory_recovery_confirmed"
        ]
        is False
    )


def test_inventory_repository_exception_is_contained():
    recovery = Recovery({
        "1": RuntimeError(
            "recovery store unavailable"
        ),
    })
    service = _service(
        recovery
    )

    result = service.analyze(
        _return_evidence([
            _return_record(),
        ]),
        _products(),
    )

    assert result["error"] is False
    assert (
        result[
            "inventory_recovery_unavailable_candidate_record_count"
        ]
        == 1
    )
    assert (
        result[
            "saleable_inventory_recovery_confirmed"
        ]
        is False
    )
    assert (
        result["profit_adjustment_allowed"]
        is False
    )


def test_response_explains_saleable_recovery_but_keeps_remaining_blockers():
    recovery = Recovery({
        "1": _ready_recovery(),
    })
    service = _service(
        recovery
    )
    evidence = service.analyze(
        _return_evidence([
            _return_record(),
        ]),
        _products(),
    )

    text = build_period_profit_response(
        _summary(),
        return_cogs_recovery_evidence=(
            evidence
        ),
    )["text"]

    assert (
        "Восстановление продаваемого остатка: "
        "подтверждено для 1/1 return-records."
        in text
    )
    assert (
        "sale-lineage, историческая себестоимость "
        "и saleable recovery подтверждены"
        in text
    )
    assert (
        "период признания recovery"
        in text
    )
    assert (
        "Эта сумма не прибавляется к прибыли"
        in text
    )
    assert (
        "Прибыль: 340.00 ₽ (34.00%)"
        in text
    )


def test_coverage_exposes_inventory_recovery_without_profit_permission():
    evidence = {
        "error": False,
        "status": (
            "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_READY"
        ),
        "candidate_recovery_units": 1,
        "candidate_value_at_current_cost": 30.0,
        "candidate_value_at_historical_cost": 21.0,
        "sale_lineage_evidence_available": True,
        "sale_lineage_finance_period_complete": True,
        "sale_lineage_candidate_record_count": 1,
        "sale_lineage_matched_candidate_record_count": 1,
        "originating_sale_period_confirmed": True,
        "historical_cost_candidate_record_count": 1,
        "historical_cost_matched_candidate_record_count": 1,
        "historical_cost_basis_confirmed": True,
        "inventory_recovery_evidence_available": True,
        "inventory_recovery_state_complete": True,
        "inventory_recovery_candidate_record_count": 1,
        "inventory_recovery_saleable_candidate_record_count": 1,
        "inventory_recovery_non_saleable_candidate_record_count": 0,
        "inventory_recovery_missing_candidate_record_count": 0,
        "inventory_recovery_conflict_candidate_record_count": 0,
        "inventory_recovery_quantity_mismatch_candidate_record_count": 0,
        "saleable_inventory_recovery_confirmed": True,
        "recovery_period_attribution_confirmed": False,
        "profit_adjustment_allowed": False,
    }

    result = build_period_profit_coverage(
        _summary(),
        return_cogs_recovery_evidence=(
            evidence
        ),
    )

    assert (
        result[
            "return_cogs_inventory_recovery_status"
        ]
        == "SALEABLE_CONFIRMED"
    )
    assert (
        result[
            "return_cogs_saleable_inventory_recovery_confirmed"
        ]
        is True
    )
    assert (
        result[
            "return_cogs_inventory_recovery_saleable_records"
        ]
        == 1
    )
    assert (
        result[
            "return_cogs_recovery_period_attribution_confirmed"
        ]
        is False
    )
    assert (
        result[
            "return_cogs_profit_adjustment_allowed"
        ]
        is False
    )
    assert (
        result[
            "accounting_net_profit_claim_allowed"
        ]
        is False
    )
