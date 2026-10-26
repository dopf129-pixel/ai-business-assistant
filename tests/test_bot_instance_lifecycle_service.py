import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from services.bot_instance_lifecycle_service import (
    BotInstanceAlreadyRunning,
    BotInstanceLease,
    BotLifecycleError,
    BotStartupMaintenanceGuard,
    inspect_bot_instance,
    project_root_fingerprint,
    request_graceful_stop,
)


ROOT = Path(__file__).resolve().parents[1]


def test_instance_state_is_token_scoped_and_does_not_persist_token(tmp_path):
    token = "synthetic-test-token-never-a-real-credential"
    lease = BotInstanceLease(token, state_root=tmp_path)
    lease.acquire()
    try:
        payload = json.loads(lease.metadata_path.read_text(encoding="utf-8"))
        assert token not in lease.lock_path.name
        assert token not in lease.metadata_path.read_text(encoding="utf-8")
        assert "token" not in payload
        assert payload["state"] == "STARTING"
        public_status = inspect_bot_instance(token, state_root=tmp_path)
        assert "generation" not in public_status
        assert inspect_bot_instance("another-synthetic-token", state_root=tmp_path)["state"] == "STOPPED"
        stop_status = inspect_bot_instance(
            token, state_root=tmp_path, include_generation=True
        )
        assert stop_status["generation"] == payload["generation"]
    finally:
        lease.close()

    assert inspect_bot_instance(token, state_root=tmp_path)["state"] == "STOPPED"


def test_distinct_bot_tokens_get_distinct_lock_namespaces(tmp_path):
    first = BotInstanceLease("synthetic-bot-one", state_root=tmp_path)
    second = BotInstanceLease("synthetic-bot-two", state_root=tmp_path)

    assert first.lock_path != second.lock_path
    assert first.metadata_path != second.metadata_path


def test_distinct_bot_tokens_can_hold_independent_locks(tmp_path):
    first = BotInstanceLease("synthetic-bot-one", state_root=tmp_path)
    second = BotInstanceLease("synthetic-bot-two", state_root=tmp_path)
    first.acquire()
    try:
        second.acquire()
        assert inspect_bot_instance("synthetic-bot-one", state_root=tmp_path)["state"] == "STARTING"
        assert inspect_bot_instance("synthetic-bot-two", state_root=tmp_path)["state"] == "STARTING"
    finally:
        second.close()
        first.close()


def test_instance_startup_is_excluded_while_backup_holds_maintenance_guard(tmp_path):
    token = "synthetic-backup-maintenance-token"
    guard = BotStartupMaintenanceGuard(token, state_root=tmp_path)
    assert guard.acquire() is True
    lease = BotInstanceLease(token, state_root=tmp_path)

    try:
        with pytest.raises(BotLifecycleError) as error:
            lease.acquire()
        assert error.value.code == "BOT_INSTANCE_MAINTENANCE_ACTIVE"
        assert inspect_bot_instance(token, state_root=tmp_path)["state"] == "STOPPED"
    finally:
        guard.close()

    lease.acquire()
    try:
        assert inspect_bot_instance(token, state_root=tmp_path)["state"] == "STARTING"
    finally:
        lease.close()


def test_failed_start_releases_lock_and_stale_pid_marker_never_targets_process(tmp_path, monkeypatch):
    token = "synthetic-stale-pid-token"
    lease = BotInstanceLease(token, state_root=tmp_path)
    lease.acquire()
    lease.close()  # models startup failure before polling became ready
    payload = json.loads(lease.metadata_path.read_text(encoding="utf-8"))
    payload.update(
        state="RUNNING",
        pid=os.getpid(),  # a stale marker that now names this unrelated test process
        control_port=1,
        control_secret="stale-secret",
    )
    lease.metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        "services.bot_instance_lifecycle_service.os.kill",
        lambda *args, **kwargs: pytest.fail("lifecycle must never signal a PID"),
    )

    assert inspect_bot_instance(token, state_root=tmp_path)["state"] == "STOPPED"
    assert request_graceful_stop(token, state_root=tmp_path) == {
        "stopped": True,
        "state": "STOPPED",
    }


def test_repeated_stop_waits_for_existing_stopping_generation(tmp_path):
    token = "synthetic-repeated-stop-token"
    lease = BotInstanceLease(token, state_root=tmp_path)
    lease.acquire()
    lease.control_port = 12345
    lease._write_state("STOPPING")
    result = {}
    waiter = threading.Thread(
        target=lambda: result.update(
            request_graceful_stop(token, state_root=tmp_path, timeout_seconds=3)
        ),
        daemon=True,
    )
    waiter.start()
    try:
        time.sleep(0.1)
        lease.close()
        waiter.join(timeout=3)
        assert not waiter.is_alive()
        assert result == {"stopped": True, "state": "STOPPED"}
    finally:
        lease.close()
        if waiter.is_alive():
            waiter.join(timeout=3)


def test_stop_timeout_reports_still_running_without_force_termination(tmp_path, monkeypatch):
    token = "synthetic-stop-timeout-token"
    lease = BotInstanceLease(token, state_root=tmp_path)
    lease.acquire()
    lease.control_port = 12346
    lease._write_state("STOPPING")
    monkeypatch.setattr(
        "services.bot_instance_lifecycle_service.os.kill",
        lambda *args, **kwargs: pytest.fail("timeout must not force-kill a process"),
    )
    try:
        result = request_graceful_stop(token, state_root=tmp_path, timeout_seconds=0.15)
        assert result["stopped"] is False
        assert result["code"] == "BOT_INSTANCE_STOP_TIMEOUT"
        assert result["state"] == "STOPPING"
        assert inspect_bot_instance(token, state_root=tmp_path)["state"] == "STOPPING"
    finally:
        lease.close()


def test_status_reports_revision_captured_at_process_start(tmp_path, monkeypatch):
    token = "synthetic-revision-snapshot"
    monkeypatch.setenv("APP_BUILD_REVISION", "abcdef0123456789")
    lease = BotInstanceLease(token, state_root=tmp_path)
    lease.acquire()
    monkeypatch.setenv("APP_BUILD_REVISION", "fedcba9876543210")
    try:
        status = inspect_bot_instance(token, state_root=tmp_path)
        assert status["revision"] == "abcdef0123456789"
    finally:
        lease.close()


def test_status_reports_only_one_way_project_root_fingerprint(tmp_path, monkeypatch):
    token = "synthetic-project-root-fingerprint"
    project_root = tmp_path / "private project path"
    monkeypatch.setenv("APP_BUILD_PROJECT_ROOT", str(project_root))
    lease = BotInstanceLease(token, state_root=tmp_path / "state")
    lease.acquire()
    try:
        status = inspect_bot_instance(token, state_root=tmp_path / "state")
        assert status["project_root_fingerprint"] == project_root_fingerprint(project_root)
        assert str(project_root) not in repr(status)
        assert len(status["project_root_fingerprint"]) == 64
    finally:
        lease.close()


def test_graceful_stop_can_refuse_a_different_checkout_before_control_request(
    tmp_path, monkeypatch
):
    token = "synthetic-stop-checkout-scope"
    other_root = tmp_path / "other checkout"
    current_root = tmp_path / "current checkout"
    monkeypatch.setenv("APP_BUILD_PROJECT_ROOT", str(other_root))
    lease = BotInstanceLease(token, state_root=tmp_path / "state")
    lease.acquire()
    try:
        result = request_graceful_stop(
            token,
            state_root=tmp_path / "state",
            expected_project_root_fingerprint=project_root_fingerprint(current_root),
            timeout_seconds=0.1,
        )
        assert result["stopped"] is False
        assert result["code"] == "BOT_INSTANCE_CHECKOUT_MISMATCH"
        assert inspect_bot_instance(token, state_root=tmp_path / "state")["state"] == "STARTING"
    finally:
        lease.close()


def test_stop_does_not_retarget_a_replacement_generation_while_starting(
    tmp_path, monkeypatch
):
    token = "synthetic-stop-generation-replacement"
    expected_checkout = project_root_fingerprint(tmp_path / "current-checkout")
    foreign_checkout = project_root_fingerprint(tmp_path / "other-checkout")
    statuses = iter([
        {"state": "STARTING", "generation": "a" * 32},
        {"state": "STARTING", "generation": "b" * 32},
    ])
    metadata = iter([
        {
            "state": "STARTING",
            "generation": "a" * 32,
            "project_root_fingerprint": expected_checkout,
        },
        {
            "state": "STARTING",
            "generation": "b" * 32,
            "project_root_fingerprint": foreign_checkout,
            "control_port": 43210,
            "control_secret": "synthetic-foreign-secret",
        },
    ])
    sent = []
    monkeypatch.setattr(
        "services.bot_instance_lifecycle_service.inspect_bot_instance",
        lambda *_args, **_kwargs: next(statuses),
    )
    monkeypatch.setattr(
        "services.bot_instance_lifecycle_service._read_metadata",
        lambda *_args, **_kwargs: next(metadata),
    )
    monkeypatch.setattr(
        "services.bot_instance_lifecycle_service.time.sleep", lambda _seconds: None
    )
    monkeypatch.setattr(
        "services.bot_instance_lifecycle_service.socket.create_connection",
        lambda *args, **kwargs: sent.append((args, kwargs)),
    )

    result = request_graceful_stop(
        token,
        state_root=tmp_path,
        timeout_seconds=1,
        expected_project_root_fingerprint=expected_checkout,
    )

    assert result == {
        "stopped": False,
        "state": "STARTING",
        "code": "BOT_INSTANCE_GENERATION_CHANGED",
    }
    assert sent == []


def test_status_persists_only_allowlisted_failure_code_and_checkout_fingerprint(tmp_path):
    token = "synthetic-safe-failure-code"
    lease = BotInstanceLease(token, state_root=tmp_path)
    lease.acquire()
    try:
        assert lease.record_failure("TELEGRAM_POLLING_FAILED") is True
        assert lease.record_failure("secret traceback must not be saved") is False
        assert lease.record_failure({"secret": "value"}) is False
        status = inspect_bot_instance(token, state_root=tmp_path)
        assert status["state"] == "STARTING"
        assert status["last_failure_code"] == "TELEGRAM_POLLING_FAILED"
        serialized = lease.metadata_path.read_text(encoding="utf-8")
        assert "secret traceback" not in serialized
        assert "private checkout path" not in serialized
    finally:
        lease.close()
    stopped = inspect_bot_instance(token, state_root=tmp_path)
    assert stopped["state"] == "STOPPED"
    assert stopped["last_failure_code"] == "TELEGRAM_POLLING_FAILED"


def test_malformed_live_metadata_fails_closed(tmp_path):
    token = "synthetic-malformed-metadata-token"
    lease = BotInstanceLease(token, state_root=tmp_path)
    lease.acquire()
    lease.metadata_path.write_text("{not valid JSON", encoding="utf-8")
    try:
        assert inspect_bot_instance(token, state_root=tmp_path)["state"] == "UNKNOWN"
        result = request_graceful_stop(token, state_root=tmp_path, timeout_seconds=0.1)
        assert result["stopped"] is False
        assert result["state"] == "UNKNOWN"
    finally:
        lease.close()


def test_competing_process_cannot_start_second_polling_owner(tmp_path):
    ready = tmp_path / "child-ready"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "app")
    environment["TEST_LIFECYCLE_STATE_ROOT"] = str(tmp_path / "state")
    environment["TEST_LIFECYCLE_READY"] = str(ready)
    environment["TEST_LIFECYCLE_TOKEN"] = "synthetic-cross-process-token"
    child_code = (
        "import os,time; from services.bot_instance_lifecycle_service import BotInstanceLease; "
        "lease=BotInstanceLease(os.environ['TEST_LIFECYCLE_TOKEN'], "
        "state_root=os.environ['TEST_LIFECYCLE_STATE_ROOT']); lease.acquire(); "
        "open(os.environ['TEST_LIFECYCLE_READY'],'w').write('ready'); "
        "time.sleep(30); lease.close()"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", child_code],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), "synthetic lock-holder did not become ready"

        second = BotInstanceLease(
            environment["TEST_LIFECYCLE_TOKEN"],
            state_root=environment["TEST_LIFECYCLE_STATE_ROOT"],
        )
        with pytest.raises(BotInstanceAlreadyRunning):
            second.acquire()

        child.terminate()
        child.wait(timeout=10)
        release_deadline = time.monotonic() + 3
        while True:
            try:
                second.acquire()
                break
            except BotInstanceAlreadyRunning:
                if time.monotonic() >= release_deadline:
                    raise
                time.sleep(0.05)
        second.close()
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=10)


def test_authenticated_stop_requests_shutdown_and_waits_for_lock_release(tmp_path):
    token = "synthetic-stop-control-token"
    lease = BotInstanceLease(token, state_root=tmp_path)
    lease.acquire()
    server_ready = threading.Event()
    app_stop_requested = threading.Event()
    loop = asyncio.new_event_loop()

    class FakeApplication:
        def stop_running(self):
            async def shutdown_control():
                await lease.close_control_server()
                app_stop_requested.set()
                loop.stop()

            loop.create_task(shutdown_control())

    application = FakeApplication()

    def run_control_loop():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(lease.start_control_server(application))
        lease.mark_running()
        server_ready.set()
        loop.run_forever()
        loop.close()

    server_thread = threading.Thread(target=run_control_loop, daemon=True)
    server_thread.start()
    stop_result = {}
    stop_thread = threading.Thread(
        target=lambda: stop_result.update(
            request_graceful_stop(token, state_root=tmp_path, timeout_seconds=5)
        ),
        daemon=True,
    )
    try:
        assert server_ready.wait(timeout=5)
        stop_thread.start()
        assert app_stop_requested.wait(timeout=5)
        lease.close()
        server_thread.join(timeout=5)
        stop_thread.join(timeout=5)
        assert not server_thread.is_alive()
        assert not stop_thread.is_alive()
        assert stop_result == {"stopped": True, "state": "STOPPED"}
    finally:
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(
                lease.close_control_server(), loop
            ).result(timeout=5)
        lease.close()
        if loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        server_thread.join(timeout=5)
        if stop_thread.is_alive():
            stop_thread.join(timeout=5)


def test_starting_instance_can_be_stopped_without_claiming_readiness(tmp_path):
    token = "synthetic-starting-stop-token"
    lease = BotInstanceLease(token, state_root=tmp_path)
    lease.acquire()
    server_ready = threading.Event()
    app_stop_requested = threading.Event()
    loop = asyncio.new_event_loop()

    class FakeApplication:
        def stop_running(self):
            async def shutdown_control():
                await lease.close_control_server()
                app_stop_requested.set()
                loop.stop()

            loop.create_task(shutdown_control())

    def run_control_loop():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(lease.start_control_server(FakeApplication()))
        server_ready.set()
        loop.run_forever()
        loop.close()

    server_thread = threading.Thread(target=run_control_loop, daemon=True)
    server_thread.start()
    result = {}
    stop_thread = threading.Thread(
        target=lambda: result.update(
            request_graceful_stop(token, state_root=tmp_path, timeout_seconds=5)
        ),
        daemon=True,
    )
    try:
        assert server_ready.wait(timeout=5)
        assert inspect_bot_instance(token, state_root=tmp_path)["state"] == "STARTING"
        stop_thread.start()
        assert app_stop_requested.wait(timeout=5)
        lease.close()
        server_thread.join(timeout=5)
        stop_thread.join(timeout=5)
        assert not server_thread.is_alive()
        assert not stop_thread.is_alive()
        assert result == {"stopped": True, "state": "STOPPED"}
    finally:
        lease.close()
        if loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        server_thread.join(timeout=5)
        if stop_thread.is_alive():
            stop_thread.join(timeout=5)


def test_stop_rejects_mismatched_generation_secret_without_process_kill(tmp_path):
    token = "synthetic-invalid-stop-token"
    lease = BotInstanceLease(token, state_root=tmp_path)
    lease.acquire()
    server_ready = threading.Event()
    app_stop_requested = threading.Event()
    loop = asyncio.new_event_loop()

    class FakeApplication:
        def stop_running(self):
            app_stop_requested.set()

    def run_control_loop():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(lease.start_control_server(FakeApplication()))
        lease.mark_running()
        server_ready.set()
        loop.run_forever()
        loop.close()

    server_thread = threading.Thread(target=run_control_loop, daemon=True)
    server_thread.start()
    try:
        assert server_ready.wait(timeout=5)
        with socket.create_connection(("127.0.0.1", lease.control_port), timeout=2) as client:
            client.sendall(
                json.dumps(
                    {"action": "stop", "generation": "0" * 32, "secret": "пароль"}
                ).encode("utf-8")
                + b"\n"
            )
            response = json.loads(client.makefile("rb").readline().decode("utf-8"))
        assert response["accepted"] is False
        assert app_stop_requested.is_set() is False
        assert inspect_bot_instance(token, state_root=tmp_path)["state"] == "RUNNING"
    finally:
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(
                lease.close_control_server(), loop
            ).result(timeout=5)
        lease.close()
        if loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        server_thread.join(timeout=5)
