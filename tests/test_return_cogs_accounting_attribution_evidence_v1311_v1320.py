import services.return_cogs_accounting_attribution_repository as accounting_module

from services.period_profit_return_cogs_accounting_evidence_service import (
    PeriodProfitReturnCogsAccountingEvidenceService,
)
from services.return_cogs_accounting_attribution_repository import (
    ReturnCogsAccountingAttributionRepository,
)


class BaseEvidence:
    def __init__(self, candidates=None):
        self.candidates = list(candidates or [_candidate()])

    def analyze(self, return_evidence, products):
        return {
            "error": False,
            "status": "PERIOD_PROFIT_RETURN_COGS_RECOVERY_EVIDENCE_READY",
            "candidate_records": list(self.candidates),
            "originating_sale_period_confirmed": True,
            "historical_cost_basis_confirmed": True,
            "saleable_inventory_recovery_confirmed": True,
            "originating_sale_quantity_evidence_confirmed": True,
            "originating_sale_quantity_confirmed": False,
            "originating_sale_quantity_gate_promoted": False,
            "recovery_period_attribution_confirmed": False,
            "compensation_accounting_treatment_confirmed": False,
            "period_cogs_recovery_confirmed": False,
            "accounting_cogs_recovery_confirmed": False,
            "confirmed_cogs_recovery_amount": 0.0,
            "profit_adjustment_allowed": False,
            "automatic_recovery_allowed": False,
            "read_only": True,
            "executed": False,
        }


class Attribution:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def get_latest_attribution(self, **kwargs):
        self.calls.append(dict(kwargs))
        if isinstance(self.value, Exception):
            raise self.value
        if callable(self.value):
            return self.value(**kwargs)
        return dict(self.value)


def _candidate(return_id="1", posting_number="p-1", sku="42"):
    return {
        "return_id": return_id,
        "posting_number": posting_number,
        "sku": sku,
        "quantity": 1,
    }


def _return_evidence(date_from="2026-08-01", date_to="2026-08-31"):
    return {
        "error": False,
        "status": "PERIOD_PROFIT_RETURN_EVIDENCE_READY",
        "date_from": date_from,
        "date_to": date_to,
        "complete": True,
        "return_record_count_exact": True,
        "records": [],
    }


def _ready(
    accounting_date="2026-08-20",
    compensation_state="NO_COMPENSATION_CONFIRMED",
    double_count_clear=True,
    confirmed_on="2026-09-03",
):
    return {
        "error": False,
        "status": "RETURN_COGS_ACCOUNTING_ATTRIBUTION_READY",
        "return_id": "1",
        "posting_number": "p-1",
        "sku": "42",
        "recovery_accounting_date": accounting_date,
        "compensation_state": compensation_state,
        "compensation_double_count_clear": double_count_clear,
        "confirmed_on": confirmed_on,
        "source": "SELLER_ACCOUNTING_CONFIRMED",
        "accounting_attribution_confirmed": True,
    }


def _repository(monkeypatch, tmp_path):
    db = tmp_path / "return-accounting.db"
    monkeypatch.setattr(accounting_module, "DB_NAME", str(db))
    return ReturnCogsAccountingAttributionRepository()


def _service(value):
    return PeriodProfitReturnCogsAccountingEvidenceService(
        BaseEvidence(),
        Attribution(value),
    )


def test_v1311_explicit_accounting_date_and_no_compensation_are_persisted(
    monkeypatch,
    tmp_path,
):
    repository = _repository(monkeypatch, tmp_path)
    recorded = repository.record_attribution(
        "1",
        "p-1",
        "42",
        "2026-08-20",
        "NO_COMPENSATION_CONFIRMED",
        True,
        "2026-09-03",
    )
    loaded = repository.get_latest_attribution("1", "p-1", "42")

    assert recorded["error"] is False
    assert loaded["error"] is False
    assert loaded["status"] == "RETURN_COGS_ACCOUNTING_ATTRIBUTION_READY"
    assert loaded["recovery_accounting_date"] == "2026-08-20"
    assert loaded["compensation_state"] == "NO_COMPENSATION_CONFIRMED"
    assert loaded["compensation_double_count_clear"] is True
    assert loaded["accounting_attribution_confirmed"] is True


def test_v1312_duplicate_confirmation_version_is_rejected(monkeypatch, tmp_path):
    repository = _repository(monkeypatch, tmp_path)
    first = repository.record_attribution(
        "1", "p-1", "42", "2026-08-20",
        "NO_COMPENSATION_CONFIRMED", True, "2026-09-03",
    )
    duplicate = repository.record_attribution(
        "1", "p-1", "42", "2026-08-21",
        "NO_COMPENSATION_CONFIRMED", True, "2026-09-03",
    )

    assert first["error"] is False
    assert duplicate["error"] is True
    assert duplicate["code"] == "RETURN_COGS_ACCOUNTING_ATTRIBUTION_VERSION_CONFLICT"


def test_v1313_identity_drift_and_malformed_accounting_date_fail_closed(
    monkeypatch,
    tmp_path,
):
    repository = _repository(monkeypatch, tmp_path)
    invalid = repository.record_attribution(
        "2", "p-2", "42", "not-a-date",
        "NO_COMPENSATION_CONFIRMED", True, "2026-09-03",
    )
    repository.record_attribution(
        "1", "p-1", "42", "2026-08-20",
        "NO_COMPENSATION_CONFIRMED", True, "2026-09-03",
    )
    repository.record_attribution(
        "1", "p-other", "99", "2026-08-21",
        "NO_COMPENSATION_CONFIRMED", True, "2026-09-04",
    )
    loaded = repository.get_latest_attribution("1", "p-1", "42")

    assert invalid["error"] is True
    assert invalid["code"] == "RETURN_COGS_ACCOUNTING_ATTRIBUTION_INPUT_INVALID"
    assert loaded["status"] == "RETURN_COGS_ACCOUNTING_ATTRIBUTION_IDENTITY_CONFLICT"
    assert loaded["accounting_attribution_confirmed"] is False


def test_v1314_missing_accounting_evidence_stays_unknown(monkeypatch, tmp_path):
    repository = _repository(monkeypatch, tmp_path)
    loaded = repository.get_latest_attribution("1", "p-1", "42")

    assert loaded["error"] is False
    assert loaded["status"] == "RETURN_COGS_ACCOUNTING_ATTRIBUTION_MISSING"
    assert loaded["recovery_accounting_date"] is None
    assert loaded["compensation_state"] is None
    assert loaded["compensation_double_count_clear"] is None


def test_v1315_explicit_accounting_date_inside_requested_period_is_evidence():
    result = _service(_ready()).analyze(_return_evidence(), [])

    assert result["recovery_period_attribution_evidence_complete"] is True
    assert result["recovery_period_attribution_evidence_confirmed"] is True
    assert result["accounting_attribution_in_period_candidate_record_count"] == 1
    assert result["accounting_attribution_evidence_records"][0][
        "recovery_accounting_period_matches_request"
    ] is True


def test_v1316_explicit_accounting_date_outside_requested_period_is_not_promoted():
    result = _service(_ready(accounting_date="2026-09-01")).analyze(
        _return_evidence(),
        [],
    )

    assert result["recovery_period_attribution_evidence_complete"] is True
    assert result["recovery_period_attribution_evidence_confirmed"] is False
    assert result["accounting_attribution_outside_period_candidate_record_count"] == 1
    assert result["accounting_attribution_evidence_confirmed"] is False


def test_v1317_confirmation_timestamp_is_never_used_as_accounting_date():
    evidence = _ready(accounting_date=None, confirmed_on="2026-08-20")
    result = _service(evidence).analyze(_return_evidence(), [])

    assert result["recovery_period_attribution_evidence_complete"] is False
    assert result["recovery_period_attribution_evidence_confirmed"] is False
    assert result["accounting_attribution_unavailable_candidate_record_count"] == 1
    assert result["accounting_attribution_evidence_records"][0][
        "recovery_accounting_date"
    ] is None


def test_v1318_no_compensation_requires_explicit_double_count_clearance():
    result = _service(_ready()).analyze(_return_evidence(), [])

    assert result["compensation_accounting_treatment_evidence_confirmed"] is True
    assert result["compensation_double_count_clear"] is True
    assert result["accounting_attribution_evidence_confirmed"] is True
    assert result["compensation_accounting_treatment_confirmed"] is False


def test_v1319_compensation_present_can_be_known_without_double_count_clearance():
    result = _service(
        _ready(
            compensation_state="COMPENSATION_PRESENT",
            double_count_clear=False,
        )
    ).analyze(_return_evidence(), [])

    assert result["compensation_accounting_treatment_evidence_confirmed"] is True
    assert result["compensation_double_count_clear"] is False
    assert result["accounting_attribution_evidence_confirmed"] is False
    assert result["compensation_accounting_treatment_confirmed"] is False


def test_v1320_repository_failure_is_contained_and_never_changes_profit():
    result = _service(RuntimeError("boom")).analyze(_return_evidence(), [])

    assert result["accounting_attribution_unavailable_candidate_record_count"] == 1
    assert result["recovery_period_attribution_evidence_confirmed"] is False
    assert result["compensation_accounting_treatment_evidence_confirmed"] is False
    assert result["recovery_period_attribution_confirmed"] is False
    assert result["compensation_accounting_treatment_confirmed"] is False
    assert result["originating_sale_quantity_confirmed"] is False
    assert result["period_cogs_recovery_confirmed"] is False
    assert result["accounting_cogs_recovery_confirmed"] is False
    assert result["confirmed_cogs_recovery_amount"] == 0.0
    assert result["profit_adjustment_allowed"] is False
    assert result["automatic_recovery_allowed"] is False
    assert result["read_only"] is True
    assert result["executed"] is False
