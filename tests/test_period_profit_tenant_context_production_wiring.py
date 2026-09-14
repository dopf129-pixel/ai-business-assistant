from datetime import date, timedelta

import pytest

from api.base_ozon_client import OzonClient as BaseOzonClient
from api.period_profit_related_sku_ozon_client import PeriodProfitRelatedSkuOzonClient
from services.ozon_credential_provider import OzonCredentialProvider
from services.period_profit_finance_service import PeriodProfitFinanceService
from telegram_app_layer.telegram_bot_service import TelegramBotService


class _AccountRepository:
    def get(self, user_id):
        if str(user_id) != "seller-tenant":
            return None
        return {
            "client_id": "tenant-client",
            "api_key": "tenant-key",
        }


class _PeriodProfitAdapter:
    def __init__(self, finance_service):
        self.finance_service = finance_service

    def handle_button(self, callback, user_id=None):
        period_days = {
            "period_profit:7D": 7,
            "period_profit:28D": 28,
            "period_profit:56D": 56,
            "period_profit:90D": 90,
        }[callback]
        return self._prefetch(period_days)

    def handle_text(self, text, user_id=None):
        assert text == "прибыль 01.09.2026 - 14.09.2026"
        return self._prefetch(14)

    def _prefetch(self, days):
        end = date(2026, 9, 14)
        start = end - timedelta(days=days - 1)
        return self.finance_service.prefetch_daily_accruals(start, end)


def _production_finance_service():
    provider = OzonCredentialProvider(repository=_AccountRepository())
    service = PeriodProfitFinanceService()
    service.ozon = PeriodProfitRelatedSkuOzonClient(
        credential_provider=provider,
    )
    return service


@pytest.mark.parametrize(
    ("callback", "expected_days"),
    (
        ("period_profit:7D", 7),
        ("period_profit:28D", 28),
        ("period_profit:56D", 56),
        ("period_profit:90D", 90),
    ),
)
def test_period_profit_telegram_callback_keeps_tenant_credentials_in_parallel_reads(
    monkeypatch,
    callback,
    expected_days,
):
    headers_seen = []

    def read_only_post(self, endpoint, data, timeout=20, max_attempts=3):
        assert endpoint == "/v1/finance/accrual/by-day"
        headers_seen.append(self.get_headers())
        return {"accruals": [], "last_id": ""}

    monkeypatch.setattr(BaseOzonClient, "_post", read_only_post)
    bot = TelegramBotService(_PeriodProfitAdapter(_production_finance_service()))

    result = bot.on_callback("seller-tenant", callback)

    assert result["error"] is False
    assert result["date_count"] == expected_days
    assert len(headers_seen) == expected_days
    assert all(headers["Client-Id"] == "tenant-client" for headers in headers_seen)
    assert all(headers["Api-Key"] == "tenant-key" for headers in headers_seen)


def test_custom_period_profit_text_keeps_tenant_credentials_in_parallel_reads(
    monkeypatch,
):
    headers_seen = []

    def read_only_post(self, endpoint, data, timeout=20, max_attempts=3):
        assert endpoint == "/v1/finance/accrual/by-day"
        headers_seen.append(self.get_headers())
        return {"accruals": [], "last_id": ""}

    monkeypatch.setattr(BaseOzonClient, "_post", read_only_post)
    bot = TelegramBotService(_PeriodProfitAdapter(_production_finance_service()))

    result = bot.on_message(
        "seller-tenant",
        "прибыль 01.09.2026 - 14.09.2026",
    )

    assert result["error"] is False
    assert result["date_count"] == 14
    assert len(headers_seen) == 14
    assert all(headers["Client-Id"] == "tenant-client" for headers in headers_seen)
    assert all(headers["Api-Key"] == "tenant-key" for headers in headers_seen)
