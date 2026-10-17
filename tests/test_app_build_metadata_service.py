from datetime import datetime, timezone

from services.app_build_metadata_service import AppBuildMetadataService


def test_build_metadata_is_validated_normalized_and_captured_once():
    environment = {
        "APP_BUILD_REVISION": "ABCDEF1234567890",
        "APP_BUILD_STARTED_AT_UTC": "2026-10-17T09:30:00+03:00",
    }
    service = AppBuildMetadataService(environ=environment)

    environment["APP_BUILD_REVISION"] = "different-build-sha"
    environment["APP_BUILD_STARTED_AT_UTC"] = "2099-01-01T00:00:00Z"

    assert service.public_metadata() == {
        "revision": "abcdef1234567890",
        "started_at_utc": "2026-10-17T06:30:00Z",
    }
    assert service.user_message() == (
        "ℹ️ О боте\nВерсия сборки: abcdef1234567890\n"
        "Процесс запущен (UTC): 2026-10-17T06:30:00Z"
    )


def test_missing_or_invalid_revision_is_reported_as_local_build():
    service = AppBuildMetadataService(
        environ={
            "APP_BUILD_REVISION": "not-a-revision",
            "APP_BUILD_STARTED_AT_UTC": "invalid",
        },
        clock=lambda: datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc),
    )

    assert service.public_metadata() == {
        "revision": "UNAVAILABLE",
        "started_at_utc": "2026-10-17T12:00:00Z",
    }
    message = service.user_message()
    assert "локальная, версия не задана" in message
    assert "2026-10-17T12:00:00Z" in message


def test_only_build_metadata_is_read_and_invalid_values_never_echoed():
    secret = "private-api-token-should-not-leak"
    service = AppBuildMetadataService(
        environ={
            "APP_BUILD_REVISION": secret,
            "APP_BUILD_STARTED_AT_UTC": "2026-10-17T12:00:00Z",
            "OZON_API_KEY": secret,
            "TELEGRAM_BOT_TOKEN": secret,
            "CLIENT_ID": secret,
        },
    )

    assert secret not in service.user_message()
    assert service.public_metadata()["revision"] == "UNAVAILABLE"
