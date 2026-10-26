"""Single-instance and local stop control for the Telegram polling process.

The token is used only as an input to a one-way namespace fingerprint. It is
never persisted or included in status output. The kernel lock, not PID metadata,
is the authority for process ownership.
"""

from __future__ import annotations

import asyncio
import errno
import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows runtime
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX runtime
    msvcrt = None


_SCHEMA_VERSION = 1
_VALID_STATES = {"STARTING", "RUNNING", "STOPPING", "STOPPED"}
_SAFE_FAILURE_CODES = frozenset({
    "TELEGRAM_STARTUP_FAILED",
    "TELEGRAM_POLLING_FAILED",
    "BOT_INSTANCE_UPDATER_UNAVAILABLE",
})
_REVISION_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")
_MAX_CONTROL_MESSAGE = 1024


class BotLifecycleError(RuntimeError):
    """A controlled lifecycle error safe to show to the local operator."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class BotInstanceAlreadyRunning(BotLifecycleError):
    def __init__(self):
        super().__init__(
            "BOT_INSTANCE_ALREADY_RUNNING",
            "This Telegram bot already has a polling instance on this account.",
        )


class BotStartupMaintenanceGuard:
    """Serialize bot startup with a stopped-instance data snapshot."""

    def __init__(self, token: str, *, state_root: str | Path | None = None):
        normalized = (token or "").strip()
        if not normalized:
            raise BotLifecycleError(
                "TELEGRAM_BOT_TOKEN_MISSING",
                "TELEGRAM_BOT_TOKEN is not configured.",
            )
        fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        self.state_root = Path(state_root) if state_root is not None else _default_state_root()
        self.lock_path = self.state_root / f"startup-{fingerprint}.lock"
        self._lock_file = None

    @classmethod
    def for_fingerprint(cls, fingerprint: str, *, state_root: str | Path):
        """Build the guard from an existing one-way token fingerprint."""
        instance = cls.__new__(cls)
        instance.state_root = Path(state_root)
        instance.lock_path = instance.state_root / f"startup-{fingerprint}.lock"
        instance._lock_file = None
        return instance

    def acquire(self) -> bool:
        """Acquire the short-lived startup/snapshot gate without waiting."""
        try:
            self.state_root.mkdir(parents=True, exist_ok=True)
            if os.name != "nt":
                os.chmod(self.state_root, 0o700)
            self._lock_file = self.lock_path.open("a+b")
            self._lock_file.seek(0, os.SEEK_END)
            if self._lock_file.tell() == 0:
                self._lock_file.write(b"\0")
                self._lock_file.flush()
            if not _try_kernel_lock(self._lock_file):
                self._lock_file.close()
                self._lock_file = None
                return False
            return True
        except BotLifecycleError:
            self.close()
            raise
        except OSError as error:
            self.close()
            raise BotLifecycleError(
                "BOT_INSTANCE_LOCK_FAILED",
                "Could not safely acquire the bot startup guard.",
            ) from error

    def close(self) -> None:
        if self._lock_file is None:
            return
        try:
            _unlock(self._lock_file)
        except OSError:
            pass
        try:
            self._lock_file.close()
        finally:
            self._lock_file = None

    def __enter__(self):
        if not self.acquire():
            raise BotLifecycleError(
                "BOT_INSTANCE_MAINTENANCE_ACTIVE",
                "Bot startup is temporarily blocked by a data snapshot.",
            )
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        self.close()


def _default_state_root() -> Path:
    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(base) / "AI Assistant" / "bot-lifecycle"
    runtime_dir = os.getenv("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "ai-assistant" / "bot-lifecycle"
    return Path.home() / ".local" / "state" / "ai-assistant" / "bot-lifecycle"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def project_root_fingerprint(project_root=None) -> str:
    """Return a stable, one-way identifier for this checkout path."""
    source = project_root or os.getenv("APP_BUILD_PROJECT_ROOT") or os.getcwd()
    try:
        normalized = os.path.normcase(str(Path(source).resolve(strict=False)))
    except (OSError, RuntimeError):
        normalized = os.path.normcase(os.path.abspath(os.fspath(source)))
    return hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()


def _lock_backend():
    if os.name == "nt":
        return "msvcrt" if msvcrt is not None else None
    if os.name == "posix":
        return "fcntl" if fcntl is not None else None
    return None


def _is_lock_busy(error: OSError) -> bool:
    return (
        error.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
        or getattr(error, "winerror", None) in {33, 36}
    )


def _try_kernel_lock(file_obj) -> bool:
    backend = _lock_backend()
    if backend is None:
        raise BotLifecycleError(
            "BOT_INSTANCE_LOCK_UNAVAILABLE",
            "This operating system does not support the bot instance lock.",
        )
    file_obj.seek(0)
    try:
        if backend == "msvcrt":
            msvcrt.locking(file_obj.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError as error:
        if _is_lock_busy(error):
            return False
        raise


def _unlock(file_obj) -> None:
    backend = _lock_backend()
    file_obj.seek(0)
    if backend == "msvcrt":
        msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 1)
    elif backend == "fcntl":
        fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)


def _write_private_json(path: Path, payload: dict) -> None:
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode(
        "utf-8"
    )
    fd, temporary_name = tempfile.mkstemp(prefix=".bot-state-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(8):
            try:
                os.replace(temporary, path)
                break
            except PermissionError as error:
                # Windows may briefly deny replacement while a status reader
                # releases its handle. Keep the atomic-file contract and retry
                # only that bounded transient case.
                if os.name != "nt" or attempt == 7 or getattr(error, "winerror", None) not in {5, 32}:
                    raise
                time.sleep(0.025 * (attempt + 1))
        if os.name != "nt":
            os.chmod(path, 0o600)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _read_metadata(path: Path, expected_fingerprint: str) -> dict | None:
    try:
        if path.stat().st_size > 16 * 1024:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema_version") != _SCHEMA_VERSION:
        return None
    if payload.get("token_fingerprint") != expected_fingerprint:
        return None
    if payload.get("state") not in _VALID_STATES:
        return None
    if not isinstance(payload.get("generation"), str) or not re.fullmatch(
        r"[0-9a-f]{32}", payload["generation"]
    ):
        return None
    checkout_fingerprint = payload.get("project_root_fingerprint")
    if checkout_fingerprint is not None and (
        not isinstance(checkout_fingerprint, str)
        or not re.fullmatch(r"[0-9a-f]{64}", checkout_fingerprint)
    ):
        return None
    failure_code = payload.get("last_failure_code")
    if failure_code is not None and (
        not isinstance(failure_code, str) or failure_code not in _SAFE_FAILURE_CODES
    ):
        return None
    if "control_port" in payload or "control_secret" in payload:
        if type(payload.get("control_port")) is not int or not 1 <= payload[
            "control_port"
        ] <= 65535:
            return None
        if not isinstance(payload.get("control_secret"), str):
            return None
    return payload


class BotInstanceLease:
    """Own the per-token OS lock and the instance's authenticated control port."""

    def __init__(self, token: str, *, state_root: str | Path | None = None):
        normalized = (token or "").strip()
        if not normalized:
            raise BotLifecycleError(
                "TELEGRAM_BOT_TOKEN_MISSING",
                "TELEGRAM_BOT_TOKEN is not configured.",
            )
        self.token_fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        self.state_root = Path(state_root) if state_root is not None else _default_state_root()
        self.lock_path = self.state_root / f"instance-{self.token_fingerprint}.lock"
        self.metadata_path = self.state_root / f"instance-{self.token_fingerprint}.json"
        self.generation = uuid.uuid4().hex
        self.control_secret = secrets.token_urlsafe(32)
        self.control_server = None
        self.control_port = None
        self._lock_file = None
        self._closed = False
        revision = os.getenv("APP_BUILD_REVISION", "unknown").strip()
        self.revision = revision if _REVISION_RE.fullmatch(revision) else "unknown"
        self.mode = os.getenv("APP_BUILD_MODE", "foreground").strip().lower()
        if self.mode not in {"foreground", "background"}:
            self.mode = "foreground"
        self.started_at_utc = _utc_now()
        self.project_root_fingerprint = project_root_fingerprint()
        self._last_failure_code = None
        self._state = "STARTING"

    def _metadata(self, state: str) -> dict:
        payload = {
            "schema_version": _SCHEMA_VERSION,
            "token_fingerprint": self.token_fingerprint,
            "generation": self.generation,
            "state": state,
            "pid": os.getpid(),
            "started_at_utc": self.started_at_utc,
            "revision": self.revision,
            "mode": self.mode,
            "project_root_fingerprint": self.project_root_fingerprint,
        }
        if self._last_failure_code is not None:
            payload["last_failure_code"] = self._last_failure_code
        if state != "STOPPED" and self.control_port:
            payload["control_port"] = self.control_port
            payload["control_secret"] = self.control_secret
        return payload

    def acquire(self) -> None:
        startup_guard = BotStartupMaintenanceGuard.for_fingerprint(
            self.token_fingerprint, state_root=self.state_root
        )
        try:
            if not startup_guard.acquire():
                raise BotLifecycleError(
                    "BOT_INSTANCE_MAINTENANCE_ACTIVE",
                    "Bot startup is temporarily blocked by a data snapshot.",
                )
            try:
                self.state_root.mkdir(parents=True, exist_ok=True)
                if os.name != "nt":
                    os.chmod(self.state_root, 0o700)
                self._lock_file = self.lock_path.open("a+b")
                self._lock_file.seek(0, os.SEEK_END)
                if self._lock_file.tell() == 0:
                    self._lock_file.write(b"\0")
                    self._lock_file.flush()
                if not _try_kernel_lock(self._lock_file):
                    self._lock_file.close()
                    self._lock_file = None
                    raise BotInstanceAlreadyRunning()
                self._write_state("STARTING")
            finally:
                startup_guard.close()
        except BotLifecycleError:
            self._release_lock()
            raise
        except OSError as error:
            self._release_lock()
            raise BotLifecycleError(
                "BOT_INSTANCE_LOCK_FAILED",
                "Could not safely acquire the bot instance lock.",
            ) from error

    def _write_state(self, state: str) -> None:
        _write_private_json(self.metadata_path, self._metadata(state))
        self._state = state

    def record_failure(self, code: str) -> bool:
        """Persist one allowlisted startup/runtime failure code, never its text."""
        if (
            self._lock_file is None
            or self._closed
            or not isinstance(code, str)
            or code not in _SAFE_FAILURE_CODES
        ):
            return False
        self._last_failure_code = code
        try:
            self._write_state(self._state)
        except OSError:
            self._last_failure_code = None
            return False
        return True

    async def start_control_server(self, application) -> None:
        if self._lock_file is None or self._closed:
            raise BotLifecycleError(
                "BOT_INSTANCE_LEASE_NOT_OWNED", "Bot instance lock is not owned."
            )

        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            accepted = False
            try:
                raw = await asyncio.wait_for(
                    reader.readline(), timeout=2.0
                )
                if len(raw) <= _MAX_CONTROL_MESSAGE:
                    request = json.loads(raw.decode("utf-8"))
                    accepted = (
                        isinstance(request, dict)
                        and request.get("action") == "stop"
                        and request.get("generation") == self.generation
                        and isinstance(request.get("secret"), str)
                        and hmac.compare_digest(
                            request["secret"].encode("utf-8"),
                            self.control_secret.encode("utf-8"),
                        )
                    )
                if accepted:
                    self._write_state("STOPPING")
                writer.write(
                    json.dumps(
                        {"accepted": accepted, "generation": self.generation},
                        separators=(",", ":"),
                    ).encode("utf-8")
                    + b"\n"
                )
                await writer.drain()
            except (
                asyncio.TimeoutError,
                UnicodeError,
                ValueError,
                json.JSONDecodeError,
                OSError,
            ):
                pass
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass
            if accepted:
                asyncio.get_running_loop().call_soon(application.stop_running)

        self.control_server = await asyncio.start_server(
            handle, host="127.0.0.1", port=0, limit=_MAX_CONTROL_MESSAGE
        )
        socket_info = self.control_server.sockets[0].getsockname()
        self.control_port = int(socket_info[1])
        self._write_state("STARTING")

    def mark_running(self) -> None:
        """Publish RUNNING only after PTB's Updater reports polling ready."""
        if self._lock_file is None or self._closed or self.control_port is None:
            raise BotLifecycleError(
                "BOT_INSTANCE_LEASE_NOT_READY",
                "Telegram polling cannot be marked ready before local control is bound.",
            )
        self._write_state("RUNNING")

    async def close_control_server(self) -> None:
        server = self.control_server
        if server is None:
            return
        server.close()
        await server.wait_closed()
        self.control_server = None

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.control_server is not None:
            self.control_server.close()
            self.control_server = None
        if self._lock_file is not None:
            try:
                self._write_state("STOPPED")
            except OSError:
                # Lock release remains authoritative; status readers see the
                # free kernel lock even if stale metadata could not be updated.
                pass
            finally:
                self._release_lock()

    def _release_lock(self) -> None:
        if self._lock_file is None:
            return
        try:
            _unlock(self._lock_file)
        except OSError:
            pass
        try:
            self._lock_file.close()
        finally:
            self._lock_file = None


def inspect_bot_instance(token: str, *, state_root: str | Path | None = None) -> dict:
    """Return a bounded local status without contacting Telegram or Ozon."""
    root = Path(state_root) if state_root is not None else _default_state_root()
    fingerprint = hashlib.sha256((token or "").strip().encode("utf-8")).hexdigest()
    lock_path = root / f"instance-{fingerprint}.lock"
    metadata_path = root / f"instance-{fingerprint}.json"
    if not token or not lock_path.exists():
        return {
            "state": "STOPPED", "revision": None, "started_at_utc": None,
            "mode": None, "project_root_fingerprint": None,
            "last_failure_code": None,
        }
    try:
        lock_file = lock_path.open("r+b")
    except OSError:
        return {
            "state": "UNKNOWN", "revision": None, "started_at_utc": None,
            "mode": None, "project_root_fingerprint": None,
            "last_failure_code": None,
        }
    try:
        if _try_kernel_lock(lock_file):
            _unlock(lock_file)
            metadata = _read_metadata(metadata_path, fingerprint) or {}
            return {
                "state": "STOPPED",
                "revision": metadata.get("revision"),
                "started_at_utc": metadata.get("started_at_utc"),
                "mode": metadata.get("mode"),
                "project_root_fingerprint": metadata.get("project_root_fingerprint"),
                "last_failure_code": metadata.get("last_failure_code"),
            }
        metadata = _read_metadata(metadata_path, fingerprint)
        if metadata is None:
            return {
                "state": "UNKNOWN", "revision": None, "started_at_utc": None,
                "mode": None, "project_root_fingerprint": None,
                "last_failure_code": None,
            }
        return {
            "state": metadata["state"],
            "revision": metadata.get("revision"),
            "started_at_utc": metadata.get("started_at_utc"),
            "mode": metadata.get("mode"),
            "project_root_fingerprint": metadata.get("project_root_fingerprint"),
            "last_failure_code": metadata.get("last_failure_code"),
        }
    except (BotLifecycleError, OSError):
        return {
            "state": "UNKNOWN", "revision": None, "started_at_utc": None,
            "mode": None, "project_root_fingerprint": None,
            "last_failure_code": None,
        }
    finally:
        lock_file.close()


def request_graceful_stop(
    token: str,
    *,
    state_root: str | Path | None = None,
    timeout_seconds: float = 15.0,
    expected_project_root_fingerprint: str | None = None,
) -> dict:
    """Ask the authenticated owner to stop, then confirm lock release."""
    deadline = time.monotonic() + max(0.0, min(float(timeout_seconds), 15.0))
    status = inspect_bot_instance(token, state_root=state_root)
    if status["state"] == "STOPPED":
        return {"stopped": True, "state": "STOPPED"}
    root = Path(state_root) if state_root is not None else _default_state_root()
    fingerprint = hashlib.sha256(token.strip().encode("utf-8")).hexdigest()
    payload = _read_metadata(root / f"instance-{fingerprint}.json", fingerprint)
    if expected_project_root_fingerprint is not None and (
        payload is None
        or payload.get("project_root_fingerprint") != expected_project_root_fingerprint
    ):
        return {
            "stopped": False,
            "state": status["state"],
            "code": "BOT_INSTANCE_CHECKOUT_MISMATCH",
        }
    while status["state"] == "STARTING" and (
        payload is None or "control_port" not in payload
    ) and time.monotonic() < deadline:
        time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
        status = inspect_bot_instance(token, state_root=state_root)
        if status["state"] == "STOPPED":
            return {"stopped": True, "state": "STOPPED"}
        payload = _read_metadata(root / f"instance-{fingerprint}.json", fingerprint)
    if payload is None or payload.get("state") not in {"STARTING", "RUNNING", "STOPPING"}:
        return {"stopped": False, "state": "UNKNOWN", "code": "BOT_INSTANCE_METADATA_INVALID"}
    if status["state"] == "STOPPING":
        return _wait_for_instance_stop(token, state_root, deadline)
    if status["state"] not in {"STARTING", "RUNNING"} or "control_port" not in payload:
        code = "BOT_INSTANCE_STOP_TIMEOUT" if status["state"] == "STARTING" else "BOT_INSTANCE_STATUS_UNCONFIRMED"
        return {"stopped": False, "state": status["state"], "code": code}
    request = {
        "action": "stop",
        "generation": payload["generation"],
        "secret": payload.get("control_secret"),
    }
    try:
        with socket.create_connection(("127.0.0.1", payload["control_port"]), timeout=2.0) as connection:
            connection.settimeout(2.0)
            connection.sendall(json.dumps(request, separators=(",", ":")).encode("utf-8") + b"\n")
            response = b""
            while len(response) <= _MAX_CONTROL_MESSAGE:
                chunk = connection.recv(256)
                if not chunk or b"\n" in chunk:
                    response += chunk
                    break
                response += chunk
        acknowledgement = json.loads(response.split(b"\n", 1)[0].decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError):
        latest = inspect_bot_instance(token, state_root=state_root)
        if latest["state"] == "STOPPED":
            return {"stopped": True, "state": "STOPPED"}
        if latest["state"] in {"STOPPING", "STARTING"}:
            return _wait_for_instance_stop(token, state_root, deadline)
        return {"stopped": False, "state": "UNKNOWN", "code": "BOT_INSTANCE_CONTROL_UNAVAILABLE"}
    if (
        not isinstance(acknowledgement, dict)
        or acknowledgement.get("accepted") is not True
        or acknowledgement.get("generation") != payload["generation"]
    ):
        return {"stopped": False, "state": "UNKNOWN", "code": "BOT_INSTANCE_CONTROL_REJECTED"}

    return _wait_for_instance_stop(token, state_root, deadline)


def _wait_for_instance_stop(token: str, state_root, deadline: float) -> dict:
    while time.monotonic() < deadline:
        status = inspect_bot_instance(token, state_root=state_root)
        if status["state"] == "STOPPED":
            return {"stopped": True, "state": "STOPPED"}
        time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
    final_status = inspect_bot_instance(token, state_root=state_root)
    if final_status["state"] == "STOPPED":
        return {"stopped": True, "state": "STOPPED"}
    return {
        "stopped": False,
        "state": final_status["state"],
        "code": "BOT_INSTANCE_STOP_TIMEOUT",
    }
