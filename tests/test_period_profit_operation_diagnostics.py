import json
import threading

from services.period_profit_operation_diagnostics import PeriodProfitOperationTrace


def test_long_running_trace_writes_secret_free_worker_snapshot(tmp_path):
    trace = PeriodProfitOperationTrace("selected_sku_profit")
    trace.worker_thread_id = threading.get_ident()
    trace.update(
        "posting_identity_probe",
        service="IdentityScope",
        method="recover",
        finance_sku="finance-1",
        catalog_sku="catalog-1",
        endpoint="/v2/posting/fbo/get",
    )
    trace.record_identity_stage(
        "finance_posting",
        sample_count=501,
        record_count=501,
        candidate_count=0,
        status="no_match",
        api_key="must-not-be-recorded",
    )
    target = tmp_path / "diagnostics.log"

    trace.dump_worker_stack(log_path=target)

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["stage"] == "selected_identity_finance_posting"
    assert payload["finance_sku"] == "finance-1"
    assert payload["catalog_sku"] == "catalog-1"
    assert payload["identity_diagnostics"] == {
        "finance_posting": {
            "sample_count": 501,
            "record_count": 501,
            "candidate_count": 0,
            "status": "no_match",
        }
    }
    assert payload["worker_stack"]
    assert "api_key" not in target.read_text(encoding="utf-8").lower()
