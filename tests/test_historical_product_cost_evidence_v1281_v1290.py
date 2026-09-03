import services.cost_service as cost_module

from period_profit_coverage import (
    build_period_profit_coverage,
)
from period_profit_response import (
    build_period_profit_response,
)
from services.cost_service import (
    ProductCostService,
)
from services.period_profit_return_cogs_recovery_evidence_service import (
    PeriodProfitReturnCogsRecoveryEvidenceService,
)


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


class HistoricalCosts:
    def __init__(
        self,
        historical=None,
        current=30.0,
    ):
        self.historical = dict(
            historical
            or {}
        )
        self.current = current
        self.calls = []

    def get_cost(
        self,
        product_id,
    ):
        return (
            str(product_id),
            "offer-a",
            "42",
            self.current,
            "RUB",
            None,
        )

    def get_historical_cost_evidence(
        self,
        **kwargs,
    ):
        self.calls.append(
            dict(kwargs)
        )
        day = kwargs.get(
            "at_date"
        )
        value = self.historical.get(
            day
        )
        if isinstance(
            value,
            dict,
        ):
            return dict(
                value
            )
        return {
            "error": False,
            "status": (
                "PRODUCT_COST_HISTORY_MISSING"
            ),
            "at_date": day,
            "historical_cost_confirmed": False,
            "cost_price": None,
            "effective_from": None,
            "source": None,
        }


def _history_ready(
    cost,
    effective_from,
    product_id="10",
):
    return {
        "error": False,
        "status": (
            "PRODUCT_COST_HISTORY_READY"
        ),
        "history_id": 1,
        "product_id": product_id,
        "sku": "42",
        "offer_id": "offer-a",
        "cost_price": cost,
        "currency": "RUB",
        "effective_from": (
            effective_from
        ),
        "source": "SELLER_CONFIRMED",
        "recorded_at": (
            "2026-09-03 10:00:00"
        ),
        "at_date": "2026-08-15",
        "historical_cost_confirmed": True,
    }


def _return_record(
    return_id=1,
    posting="p-1",
    quantity=1,
):
    return {
        "id": return_id,
        "posting_number": posting,
        "sku": "42",
        "offer_id": "offer-a",
        "quantity": quantity,
        "type": "ClientReturn",
        "visual_status_sys_name": (
            "ArrivedAtReturnPlace"
        ),
    }


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
    posting="p-1",
    day="2026-08-15",
):
    return {
        "return_id": return_id,
        "posting_number": posting,
        "sku": "42",
        "lineage_status": (
            "MATCHED_IN_SELECTED_PERIOD"
        ),
        "matched_sale_accrual_date": day,
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


def _db_service(
    monkeypatch,
    tmp_path,
):
    db = tmp_path / "costs.db"
    monkeypatch.setattr(
        cost_module,
        "DB_NAME",
        str(db),
    )
    return ProductCostService()


def test_v1281_current_cost_does_not_backfill_history(
    monkeypatch,
    tmp_path,
):
    service = _db_service(
        monkeypatch,
        tmp_path,
    )

    service.set_cost(
        "10",
        "42",
        "offer-a",
        30.0,
    )

    current = service.get_cost(
        "10"
    )
    history = (
        service
        .get_historical_cost_evidence(
            at_date="2026-08-15",
            product_id="10",
        )
    )

    assert current[3] == 30.0
    assert (
        history["status"]
        == "PRODUCT_COST_HISTORY_MISSING"
    )
    assert (
        history[
            "historical_cost_confirmed"
        ]
        is False
    )


def test_v1282_explicit_effective_version_resolves_for_later_sale(
    monkeypatch,
    tmp_path,
):
    service = _db_service(
        monkeypatch,
        tmp_path,
    )

    recorded = (
        service.record_historical_cost(
            product_id="10",
            sku="42",
            offer_id="offer-a",
            cost_price=21.0,
            effective_from="2026-08-01",
        )
    )
    history = (
        service
        .get_historical_cost_evidence(
            at_date="2026-08-15",
            product_id="10",
        )
    )

    assert recorded["error"] is False
    assert (
        recorded["effective_from"]
        == "2026-08-01"
    )
    assert (
        history["status"]
        == "PRODUCT_COST_HISTORY_READY"
    )
    assert history["cost_price"] == 21.0
    assert (
        history[
            "historical_cost_confirmed"
        ]
        is True
    )


def test_v1283_latest_effective_version_wins_without_rewriting_earlier_history(
    monkeypatch,
    tmp_path,
):
    service = _db_service(
        monkeypatch,
        tmp_path,
    )

    service.record_historical_cost(
        "10",
        "42",
        "offer-a",
        21.0,
        "2026-08-01",
    )
    service.record_historical_cost(
        "10",
        "42",
        "offer-a",
        24.0,
        "2026-08-20",
    )

    before = (
        service
        .get_historical_cost_evidence(
            "2026-08-15",
            product_id="10",
        )
    )
    after = (
        service
        .get_historical_cost_evidence(
            "2026-08-25",
            product_id="10",
        )
    )

    assert before["cost_price"] == 21.0
    assert (
        before["effective_from"]
        == "2026-08-01"
    )
    assert after["cost_price"] == 24.0
    assert (
        after["effective_from"]
        == "2026-08-20"
    )


def test_v1284_duplicate_product_date_is_conflict_not_silent_overwrite(
    monkeypatch,
    tmp_path,
):
    service = _db_service(
        monkeypatch,
        tmp_path,
    )

    first = service.record_historical_cost(
        "10",
        "42",
        "offer-a",
        21.0,
        "2026-08-01",
    )
    duplicate = (
        service.record_historical_cost(
            "10",
            "42",
            "offer-a",
            99.0,
            "2026-08-01",
        )
    )
    history = (
        service
        .get_historical_cost_evidence(
            "2026-08-15",
            product_id="10",
        )
    )

    assert first["error"] is False
    assert duplicate["error"] is True
    assert (
        duplicate["code"]
        == "PRODUCT_COST_HISTORY_VERSION_CONFLICT"
    )
    assert history["cost_price"] == 21.0


def test_v1285_identifier_ambiguity_stays_unconfirmed(
    monkeypatch,
    tmp_path,
):
    service = _db_service(
        monkeypatch,
        tmp_path,
    )

    service.record_historical_cost(
        "10",
        "42",
        "offer-a",
        21.0,
        "2026-08-01",
    )
    service.record_historical_cost(
        "20",
        "42",
        "offer-b",
        18.0,
        "2026-08-01",
    )

    history = (
        service
        .get_historical_cost_evidence(
            "2026-08-15",
            sku="42",
        )
    )

    assert (
        history["status"]
        == "PRODUCT_COST_HISTORY_AMBIGUOUS"
    )
    assert (
        history[
            "historical_cost_confirmed"
        ]
        is False
    )
    assert history["cost_price"] is None


def test_v1286_date_before_first_version_is_missing_not_current_cost(
    monkeypatch,
    tmp_path,
):
    service = _db_service(
        monkeypatch,
        tmp_path,
    )

    service.set_cost(
        "10",
        "42",
        "offer-a",
        30.0,
    )
    service.record_historical_cost(
        "10",
        "42",
        "offer-a",
        21.0,
        "2026-08-10",
    )

    history = (
        service
        .get_historical_cost_evidence(
            "2026-08-01",
            product_id="10",
        )
    )

    assert (
        history["status"]
        == "PRODUCT_COST_HISTORY_MISSING"
    )
    assert history["cost_price"] is None


def test_v1287_return_cogs_uses_sale_date_historical_cost_but_keeps_recovery_zero():
    costs = HistoricalCosts({
        "2026-08-15": (
            _history_ready(
                21.0,
                "2026-08-01",
            )
        ),
    })
    service = (
        PeriodProfitReturnCogsRecoveryEvidenceService(
            costs,
            Lineage([
                _lineage_record(),
            ]),
        )
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
            "candidate_value_at_current_cost"
        ]
        == 60.0
    )
    assert (
        result[
            "candidate_value_at_historical_cost"
        ]
        == 42.0
    )
    row = result["candidate_records"][0]
    assert row["product_id"] == "10"
    assert (
        row["historical_cost_per_unit"]
        == 21.0
    )
    assert (
        row[
            "historical_cost_effective_from"
        ]
        == "2026-08-01"
    )
    assert costs.calls == [
        {
            "at_date": "2026-08-15",
            "product_id": "10",
            "sku": "42",
            "offer_id": "offer-a",
        },
    ]
    assert (
        result[
            "confirmed_cogs_recovery_amount"
        ]
        == 0.0
    )
    assert (
        result["profit_adjustment_allowed"]
        is False
    )


def test_v1288_missing_one_historical_version_keeps_aggregate_basis_unconfirmed():
    costs = HistoricalCosts({
        "2026-08-15": (
            _history_ready(
                21.0,
                "2026-08-01",
            )
        ),
    })
    service = (
        PeriodProfitReturnCogsRecoveryEvidenceService(
            costs,
            Lineage([
                _lineage_record(
                    return_id=1,
                    posting="p-1",
                    day="2026-08-15",
                ),
                _lineage_record(
                    return_id=2,
                    posting="p-2",
                    day="2026-08-25",
                ),
            ]),
        )
    )

    result = service.analyze(
        _return_evidence([
            _return_record(
                return_id=1,
                posting="p-1",
            ),
            _return_record(
                return_id=2,
                posting="p-2",
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
            "historical_cost_matched_candidate_record_count"
        ]
        == 1
    )
    assert (
        result[
            "historical_cost_missing_candidate_record_count"
        ]
        == 1
    )
    assert (
        result[
            "historical_cost_basis_confirmed"
        ]
        is False
    )
    assert (
        result["profit_adjustment_allowed"]
        is False
    )


def test_v1289_response_shows_historical_cost_but_keeps_inventory_blocker():
    costs = HistoricalCosts({
        "2026-08-15": (
            _history_ready(
                21.0,
                "2026-08-01",
            )
        ),
    })
    service = (
        PeriodProfitReturnCogsRecoveryEvidenceService(
            costs,
            Lineage([
                _lineage_record(),
            ]),
        )
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
        "Историческая себестоимость исходных продаж: "
        "подтверждена для 1/1 return-records; "
        "21.00 ₽ (2.10%)."
        in text
    )
    assert (
        "остаются неподтверждёнными: "
        "продаваемый/восстановленный остаток."
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


def test_v1290_coverage_confirms_historical_basis_without_accounting_claim():
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
        "saleable_inventory_recovery_confirmed": False,
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
            "return_cogs_historical_cost_status"
        ]
        == "CONFIRMED"
    )
    assert (
        result[
            "return_cogs_historical_cost_basis_confirmed"
        ]
        is True
    )
    assert (
        result[
            "return_cogs_historical_cost_candidate_value"
        ]
        == 21.0
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
