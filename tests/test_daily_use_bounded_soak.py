"""Finite synthetic soak for daily-use calculations, persistence, and lifecycle."""

import asyncio
import gc
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from services.analytics_export_service import AnalyticsExportService
from services.analytics_export_serializer import AnalyticsExportSerializer
from services.bot_instance_lifecycle_service import (
    inspect_bot_instance,
    request_graceful_stop,
)
from services.planning_workspace_repository import PlanningWorkspaceRepository
from services.cost_service import ProductCostService
from services.expense_repository import ExpenseRepository
from services.tax_service import TaxService
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id
from services.unit_price_scenario_service import UnitPriceScenarioService


ROOT = Path(__file__).resolve().parents[1]


def _plan_payload(store_id, sku):
    return {
        "plan_kind": "single",
        "schema_version": 1,
        "calculation_version": 1,
        "target_margin_percent": "25.00",
        "items": [{
            "identity": {
                "product_id": f"product-{sku}", "offer_id": f"offer-{sku}",
                "sku": sku, "product_name": "Synthetic item", "store_id": store_id,
                "scheme": "FBO",
            },
            "inputs": {
                "price": "500.00", "cost": "120.00", "commission_rate": "15",
                "advertising_rate": "8", "discount_points_rate": "20",
                "logistics_per_unit": "40", "last_mile_per_unit": "10",
                "acquiring_per_unit": "5", "tax_mode": "USN_INCOME",
                "tax_rate": "6", "minimum_tax_rate": "1",
            },
            "provenance": {"price": "synthetic", "cost": "synthetic"},
            "sources": {"periods": {}, "completeness": {}},
            "projection": {"available": True, "missing_inputs": [], "invalid_inputs": []},
        }],
    }


def _lifecycle_child_code():
    return """
import asyncio, os
from pathlib import Path
from services.bot_instance_lifecycle_service import BotInstanceLease

class FakeApplication:
    def __init__(self):
        self.stopped = asyncio.Event()
    def stop_running(self):
        self.stopped.set()

async def main():
    lease = BotInstanceLease(os.environ['SOAK_TOKEN'], state_root=os.environ['SOAK_STATE_ROOT'])
    lease.acquire()
    app = FakeApplication()
    try:
        await lease.start_control_server(app)
        lease.mark_running()
        Path(os.environ['SOAK_READY']).write_text(str(lease.control_port), encoding='utf-8')
        await app.stopped.wait()
        await lease.close_control_server()
    finally:
        lease.close()

asyncio.run(main())
"""


def _process_handle_count():
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetProcessHandleCount.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.GetProcessHandleCount.restype = wintypes.BOOL
        count = wintypes.DWORD()
        current = kernel32.GetCurrentProcess()
        assert kernel32.GetProcessHandleCount(current, ctypes.byref(count)), ctypes.get_last_error()
        return count.value
    fd_root = Path("/proc/self/fd")
    return len(list(fd_root.iterdir())) if fd_root.exists() else None


def test_fake_daily_use_repetition_preserves_results_bounds_and_plan_revisions(tmp_path, monkeypatch):
    scenario = UnitPriceScenarioService(TaxService())
    inputs = {
        "price": "500", "cost": "120", "commission_rate": "15",
        "logistics_per_unit": "40", "last_mile_per_unit": "10",
        "acquiring_per_unit": "5", "advertising_rate": "8",
        "discount_points_rate": "20", "tax_mode": "USN_INCOME", "tax_rate": "6",
        "minimum_tax_rate": "1",
    }
    expected = scenario.calculate(inputs)["calculated"]
    report_snapshot = {
        "schema_version": 1,
        "periods": {"current": {"from": "2026-08-01", "to": "2026-08-31"}},
        "generated_at": "2026-10-25T00:00:00Z",
        "comparison_status": "UNAVAILABLE",
        "coverage_status": "PARTIAL",
        "scope": {"owner_id": "private-owner", "store_id": "private-store"},
    }
    exporter = AnalyticsExportService(
        serializer=AnalyticsExportSerializer(
            clock=lambda: datetime(2026, 10, 25, tzinfo=timezone.utc),
        ),
    )
    baseline_export = exporter.export_period_profit(report_snapshot, "json")
    assert baseline_export["error"] is False

    database = tmp_path / "plans.sqlite"
    repository = PlanningWorkspaceRepository(db_path=database)
    tenant = set_current_tenant_user_id("synthetic-owner::ozon::store-a")
    try:
        created = repository.save_document(
            title="Soak scenario", payload=_plan_payload("store-a", "synthetic-sku-a"),
            idempotency_key="daily-soak-create-01",
        )
        assert created["error"] is False
        revision = created["revision"]
        state_revision = created["state_revision"]
        document_id = created["document_id"]
        for index in range(2, 13):
            updated = repository.save_document(
                title=f"Soak scenario {index}",
                payload=_plan_payload("store-a", "synthetic-sku-a"),
                document_id=document_id,
                expected_revision=revision,
                expected_state_revision=state_revision,
                idempotency_key=f"daily-soak-revise-{index:02d}",
            )
            assert updated["error"] is False
            revision, state_revision = updated["revision"], updated["state_revision"]
        other_store = set_current_tenant_user_id("synthetic-owner::ozon::store-b")
        try:
            assert repository.get_document(document_id)["error"] is True
            other = repository.save_document(
                title="Other synthetic store",
                payload=_plan_payload("store-b", "synthetic-sku-b"),
                idempotency_key="daily-soak-other-01",
            )
            assert other["error"] is False
        finally:
            reset_current_tenant_user_id(other_store)
    finally:
        reset_current_tenant_user_id(tenant)

    # A new service instance models process restart; snapshots/caches stay transient.
    restarted = PlanningWorkspaceRepository(db_path=database)
    tenant = set_current_tenant_user_id("synthetic-owner::ozon::store-a")
    try:
        restored = restarted.get_document(document_id)
        assert restored["error"] is False
        assert restored["document"]["revision"] == 12
        assert restored["document"]["payload"]["items"][0]["identity"]["sku"] == "synthetic-sku-a"
        assert len(restarted.list_revisions(document_id)["items"]) == 12
    finally:
        reset_current_tenant_user_id(tenant)

    for _ in range(64):
        assert scenario.calculate(inputs)["calculated"] == expected
        exported = exporter.export_period_profit(report_snapshot, "json")
        assert exported["error"] is False
        assert exported["file_content"] == baseline_export["file_content"]
        assert len(exported["file_content"]) <= 64 * 1024

    assert "private-owner" not in baseline_export["file_content"].decode("utf-8")
    assert "private-store" not in baseline_export["file_content"].decode("utf-8")
    assert database.stat().st_size <= 2 * 1024 * 1024
    assert len(list(tmp_path.iterdir())) <= 3

    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(tmp_path / "tenant-storage"))
    for store_id, cost, expense in (("store-a", 120.0, 15.5), ("store-b", 240.0, 31.0)):
        tenant = set_current_tenant_user_id(f"synthetic-owner::ozon::{store_id}")
        try:
            ProductCostService().set_cost(
                product_id="synthetic-product", sku="synthetic-sku",
                offer_id="synthetic-offer", cost_price=cost,
            )
            saved_expense = ExpenseRepository().add_expense(
                "2026-10-20", "synthetic-advertising", expense, "synthetic soak",
            )
            assert saved_expense["error"] is False
        finally:
            reset_current_tenant_user_id(tenant)

    for store_id, expected_cost, expected_expense in (
        ("store-a", 120.0, 15.5), ("store-b", 240.0, 31.0),
    ):
        tenant = set_current_tenant_user_id(f"synthetic-owner::ozon::{store_id}")
        try:
            assert ProductCostService().get_cost("synthetic-product")[3] == expected_cost
            expenses = ExpenseRepository().get_expenses_by_period("2026-10-20", "2026-10-20")
            assert len(expenses) == 1
            assert expenses[0]["amount"] == expected_expense
            assert expenses[0]["description"] == "synthetic soak"
        finally:
            reset_current_tenant_user_id(tenant)

    tenant_files = list((tmp_path / "tenant-storage").rglob("*"))
    tenant_file_bytes = sum(path.stat().st_size for path in tenant_files if path.is_file())
    tenant_file_count = sum(path.is_file() for path in tenant_files)
    assert tenant_file_count == 2
    assert tenant_file_bytes <= 2 * 1024 * 1024
    print(
        "synthetic daily-use repetition: calculations=64, exports=64, "
        f"plan_revisions=12, plan_db_bytes={database.stat().st_size}, "
        f"tenant_storage_files={tenant_file_count}, "
        f"tenant_storage_bytes={tenant_file_bytes}"
    )


def test_fake_polling_lifecycle_repeated_start_status_stop_has_bounded_resources(tmp_path):
    cycle_count = 8
    state_root = tmp_path / "isolated lifecycle"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "app")
    environment["SOAK_STATE_ROOT"] = str(state_root)
    environment["SOAK_TOKEN"] = "synthetic-daily-use-token"
    child_code = _lifecycle_child_code()
    baseline_threads = threading.active_count()
    baseline_handles = _process_handle_count()
    cycle_durations = []

    for cycle in range(cycle_count):
        ready_file = tmp_path / f"ready-{cycle}.txt"
        cycle_env = {**environment, "SOAK_READY": str(ready_file)}
        started = time.monotonic()
        process = subprocess.Popen(
            [sys.executable, "-c", child_code], cwd=ROOT, env=cycle_env,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
        )
        try:
            deadline = time.monotonic() + 8
            while not ready_file.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            assert ready_file.exists(), "synthetic polling process failed to start"
            status = inspect_bot_instance(environment["SOAK_TOKEN"], state_root=state_root)
            assert status["state"] == "RUNNING"
            assert status["revision"] == "unknown"
            stopped = request_graceful_stop(
                environment["SOAK_TOKEN"], state_root=state_root, timeout_seconds=5,
            )
            assert stopped == {"stopped": True, "state": "STOPPED"}
            process.wait(timeout=5)
            assert process.returncode == 0, process.stderr.read()
            assert inspect_bot_instance(environment["SOAK_TOKEN"], state_root=state_root)["state"] == "STOPPED"
            cycle_durations.append(time.monotonic() - started)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            if process.stderr:
                process.stderr.close()
            del process
            gc.collect()

    state_files = list(state_root.iterdir())
    # The lifecycle uses persistent kernel-lock files for both the instance
    # lease and the startup/snapshot gate. Keep the count bounded across all
    # cycles; unlinking either lock could let concurrent processes lock
    # different inodes for the same token namespace.
    assert len(state_files) == 3
    assert sum(path.name.startswith("instance-") for path in state_files) == 2
    assert sum(path.name.startswith("startup-") for path in state_files) == 1
    assert all(path.stat().st_size <= 16 * 1024 for path in state_files)
    assert len(cycle_durations) == cycle_count
    assert max(cycle_durations) < 14
    assert threading.active_count() <= baseline_threads + 2
    final_handles = _process_handle_count()
    if baseline_handles is not None and final_handles is not None:
        assert final_handles <= baseline_handles + 4
    assert json.loads(next(path for path in state_files if path.suffix == ".json").read_text(encoding="utf-8"))["state"] == "STOPPED"
    handle_delta = (
        final_handles - baseline_handles
        if baseline_handles is not None and final_handles is not None
        else "unavailable"
    )
    print(
        "synthetic lifecycle soak: "
        f"cycles={cycle_count}, max_cycle_seconds={max(cycle_durations):.3f}, "
        f"state_files={len(state_files)}, state_file_bytes={sum(path.stat().st_size for path in state_files)}, "
        f"thread_delta={threading.active_count() - baseline_threads}, handle_delta={handle_delta}"
    )
