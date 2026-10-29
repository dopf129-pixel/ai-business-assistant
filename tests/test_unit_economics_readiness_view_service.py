from services.unit_economics_readiness_view_service import UnitEconomicsReadinessViewService as Service


def _snapshot(
    *, status="COMPLETE", amount="0.00", units=100, unit_amount="0.00",
    scope="REFERENCE_56_COMPLETED_LOCAL_DAYS",
):
    is_phase = scope == "EXPERIMENT_PHASE_WINDOW"
    return {
        "error": False,
        "schema_version": 1,
        "identity": {
            "owner_id": "owner-secret", "store_id": "store-secret", "product_id": "product-secret",
            "offer_id": "offer-secret", "sku": "sku-secret", "sale_schema": "FBO",
        },
        "scope_kind": scope,
        "model_scope": "WINDOW_COST_ALLOCATION",
        "as_of_local_date": "2026-03-01" if is_phase else "2026-02-26",
        "window": {
            "from_date": "2026-02-26" if is_phase else "2026-01-01",
            "to_date": "2026-02-28" if is_phase else "2026-02-25",
            "date_basis": "LOCAL_CALENDAR_DAY", "timezone": "Europe/Moscow",
        },
        "coverage": {"status": status, "complete": status == "COMPLETE"},
        "denominator": {"units": units, "kind": "SOLD_UNITS_WINDOW"},
        "components": {
            "ADS": {
                "status": "COMPLETE" if status == "COMPLETE" else "PARTIAL",
                "observed_numerator_rub": amount,
                "observed_denominator_units": units,
                "unit_expense_rub": unit_amount if status == "COMPLETE" and units else None,
                "rate_status": "AVAILABLE" if units else "ZERO_DENOMINATOR",
                "covered_days": (3 if is_phase else 56) if status == "COMPLETE" else 10,
                "missing_segments": 0 if status == "COMPLETE" else 1,
            },
        },
        "source_revision": "a" * 64,
        "read_only": True,
        "executed": False,
    }


def _metadata(*, source="OZON_SELLER_FINANCE", applicability="WINDOW_MODEL_INPUT"):
    return {"ADS": {"source": source, "applicability": applicability}}


def test_complete_zero_component_is_included_as_zero_not_unknown():
    result = Service.build(_snapshot(), _metadata())
    assert result["error"] is False
    row = result["components"][0]
    assert row["status"] == "INCLUDED"
    assert row["observed_amount_rub"] == "0.00"
    assert row["applied_amount_rub"] == "0.00"
    assert row["unit_amount_rub"] == "0.00"
    assert "COMPLETE_ZERO_AMOUNT" in row["reason_codes"]
    assert result["component_counts"] == {"INCLUDED": 1, "EXCLUDED": 0, "UNKNOWN": 0}


def test_complete_positive_component_exposes_source_amount_units_and_rate():
    result = Service.build(_snapshot(amount="50.00", units=10, unit_amount="5.00"), _metadata())
    row = result["components"][0]
    assert row == {
        "component_key": "ADS", "status": "INCLUDED", "source": "OZON_SELLER_FINANCE",
        "applicability": "WINDOW_MODEL_INPUT", "evidence_status": "COMPLETE",
        "observed_amount_rub": "50.00", "observed_units": 10,
        "applied_amount_rub": "50.00", "applied_units": 10,
        "unit_amount_rub": "5.00", "reason_codes": [],
    }


def test_missing_metadata_is_unknown_and_does_not_claim_zero_source():
    result = Service.build(_snapshot())
    row = result["components"][0]
    assert row["status"] == "UNKNOWN"
    assert row["source"] == "UNKNOWN"
    assert row["applied_amount_rub"] is None
    assert "SOURCE_METADATA_MISSING_OR_INVALID" in row["reason_codes"]


def test_reconciliation_only_known_amount_is_excluded_not_added_to_model():
    snapshot = _snapshot(amount="25.00", unit_amount="0.25")
    metadata = _metadata(applicability="RECONCILIATION_ONLY")
    result = Service.build(snapshot, metadata)
    row = result["components"][0]
    assert row["status"] == "EXCLUDED"
    assert row["observed_amount_rub"] == "25.00"
    assert row["applied_amount_rub"] is None
    assert row["unit_amount_rub"] is None


def test_partial_snapshot_keeps_observed_values_but_never_marks_them_applied():
    result = Service.build(_snapshot(status="PARTIAL", amount="10.00", units=3), _metadata())
    row = result["components"][0]
    assert row["status"] == "UNKNOWN"
    assert row["observed_amount_rub"] == "10.00"
    assert row["observed_units"] == 3
    assert row["applied_amount_rub"] is None
    assert row["unit_amount_rub"] is None
    assert result["status"] == "PARTIAL"


def test_zero_denominator_keeps_amount_but_unit_rate_is_unknown():
    result = Service.build(_snapshot(amount="12.00", units=0, unit_amount=None), _metadata())
    row = result["components"][0]
    assert row["status"] == "UNKNOWN"
    assert row["observed_amount_rub"] == "12.00"
    assert row["observed_units"] == 0
    assert row["applied_amount_rub"] is None
    assert "ZERO_DENOMINATOR" in row["reason_codes"]


def test_invalid_source_and_free_text_metadata_fail_closed_without_echo():
    invalid = {
        "ADS": {
            "source": "someone's key", "applicability": "WINDOW_MODEL_INPUT",
        },
    }
    result = Service.build(_snapshot(), invalid)
    assert result["components"][0]["status"] == "UNKNOWN"
    assert result["components"][0]["source"] == "UNKNOWN"
    assert "private text" not in repr(result)


def test_unknown_extra_metadata_component_is_rejected():
    metadata = _metadata()
    metadata["FOREIGN"] = {"source": "OZON_SELLER_FINANCE", "applicability": "WINDOW_MODEL_INPUT", "reason_codes": []}
    assert Service.build(_snapshot(), metadata)["error"] is True


def test_projection_does_not_return_sku_or_owner_identity():
    result = Service.build(_snapshot(amount="20.00", unit_amount="0.20"), _metadata())
    assert "identity" not in result
    assert "source_revision" not in result
    assert "sku-secret" not in repr(result)
    assert "owner-secret" not in repr(result)
    assert result["api_calls"] == 0
    assert result["read_only"] is True


def test_reference_and_phase_pair_are_projected_separately_without_combining():
    reference = _snapshot(amount="20.00", unit_amount="0.20")
    phase = _snapshot(amount="40.00", unit_amount="0.40", scope="EXPERIMENT_PHASE_WINDOW")
    pair = {
        "error": False, "reference": reference, "phase": phase,
        "combined": False, "comparison_eligibility": "DENOMINATOR_COMPATIBLE",
    }
    result = Service.build_pair(pair, _metadata(), _metadata())
    assert result["error"] is False
    assert result["combined"] is False
    assert result["reference"]["components"][0]["observed_amount_rub"] == "20.00"
    assert result["phase"]["components"][0]["observed_amount_rub"] == "40.00"
    assert "observed_amount_rub" not in result
    assert result["api_calls"] == 0


def test_pair_rejects_wrong_scope_or_combined_input():
    snapshot = _snapshot()
    pair = {
        "error": False, "reference": snapshot, "phase": snapshot,
        "combined": True, "comparison_eligibility": "DENOMINATOR_COMPATIBLE",
    }
    assert Service.build_pair(pair)["error"] is True


def test_overlapping_reference_and_phase_remain_separate_and_incomparable():
    reference = _snapshot()
    phase = _snapshot(scope="EXPERIMENT_PHASE_WINDOW")
    phase["window"]["from_date"] = "2026-02-20"
    phase["window"]["to_date"] = "2026-02-22"
    pair = {
        "error": False, "reference": reference, "phase": phase,
        "combined": False, "comparison_eligibility": "DENOMINATOR_COMPATIBLE",
    }
    result = Service.build_pair(pair, _metadata(), _metadata())
    assert result["error"] is False
    assert result["comparison_eligibility"] == "INCOMPARABLE"
    assert result["comparison_reasons"] == ["WINDOWS_OVERLAP"]
    assert result["reference"]["components"][0]["observed_amount_rub"] == "0.00"
    assert result["phase"]["components"][0]["observed_amount_rub"] == "0.00"


def test_invalid_snapshot_is_sanitized_as_unavailable_error():
    snapshot = _snapshot()
    snapshot["components"]["ADS"]["observed_numerator_rub"] = "secret"
    result = Service.build(snapshot, _metadata())
    assert result == {
        "error": True, "code": "UNIT_ECONOMICS_READINESS_SNAPSHOT_INVALID",
        "read_only": True, "api_calls": 0,
    }


def test_reason_codes_are_generated_as_bounded_machine_codes():
    result = Service.build(_snapshot(status="PARTIAL", amount="10.00", units=3), _metadata())
    assert "COMPONENT_EVIDENCE_PARTIAL" in result["components"][0]["reason_codes"]
    assert all(Service._KEY_RE.fullmatch(item) for item in result["components"][0]["reason_codes"])


def test_unrecognized_metadata_fields_are_rejected_without_echo():
    invalid = {
        "ADS": {
            "source": "OZON_SELLER_FINANCE",
            "applicability": "WINDOW_MODEL_INPUT",
            "reason": "private text",
        },
    }
    result = Service.build(_snapshot(), invalid)
    assert result["components"][0]["status"] == "UNKNOWN"
    assert "private text" not in repr(result)
