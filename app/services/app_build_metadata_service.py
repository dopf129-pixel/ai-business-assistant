"""Immutable, process-start build metadata for user-visible diagnostics."""

import os
import re
from datetime import datetime, timezone


class AppBuildMetadataService:
    REVISION_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")

    def __init__(self, revision=None, started_at_utc=None, mode=None, environ=None, clock=None):
        values = os.environ if environ is None else environ
        if revision is None:
            revision = values.get("APP_BUILD_REVISION")
        if started_at_utc is None:
            started_at_utc = values.get("APP_BUILD_STARTED_AT_UTC")
        if mode is None:
            mode = values.get("APP_BUILD_MODE")
        self._revision = self._normalize_revision(revision)
        self._mode = self._normalize_mode(mode)
        self._started_at_utc = (
            self._normalize_timestamp(started_at_utc)
            or self._now_timestamp(clock)
        )

    def public_metadata(self):
        """Return only validated process-start metadata approved for support."""
        return {
            "revision": self._revision or "UNAVAILABLE",
            "started_at_utc": self._started_at_utc,
            "mode": self._mode or "UNAVAILABLE",
        }

    def user_message(self):
        metadata = self.public_metadata()
        if metadata["revision"] == "UNAVAILABLE":
            version = "Сборка: локальная, версия не задана"
        else:
            version = "Версия сборки: " + metadata["revision"]
        return (
            "ℹ️ О боте\n"
            + version
            + "\nРежим запуска: "
            + ("фоновый" if metadata["mode"] == "background" else
               "обычный" if metadata["mode"] == "foreground" else "не определён")
            + "\nПроцесс запущен (UTC): "
            + metadata["started_at_utc"]
        )

    @classmethod
    def _normalize_revision(cls, value):
        if not isinstance(value, str) or not cls.REVISION_RE.fullmatch(value.strip()):
            return None
        return value.strip().lower()

    @staticmethod
    def _normalize_mode(value):
        if not isinstance(value, str):
            return None
        normalized = value.strip().lower()
        return normalized if normalized in {"foreground", "background"} else None

    @staticmethod
    def _normalize_timestamp(value):
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str) and len(value) <= 40:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _now_timestamp(clock=None):
        value = clock() if callable(clock) else datetime.now(timezone.utc)
        if not isinstance(value, datetime):
            value = datetime.now(timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
