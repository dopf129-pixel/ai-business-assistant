from decimal import Decimal
from unittest.mock import patch

import pytest

from api.ozon_performance_historical_reports import (
    HistoricalPerformanceReports, HistoricalReportError, parse_report_csv,
)
from services.period_profit_sku_advertising_service import PeriodProfitSkuAdvertisingService


def test_cpc_and_cpo_columns_do_not_double_count():
    cpc = ("Кампания;123\nSKU;Название товара;Расход, Р, с НДС;Клики\n"
           "3921245627;Test;12,50;3\nВсего;;12,50;3\n").encode()
    cpo = ("SKU;Расход, ₽;Расход (Оплата за клик), ₽\n"
           "3921245627;7,25;12,50\n").encode()
    assert parse_report_csv(cpc, "CPC")[0]["expense"] == Decimal("12.50")
    assert parse_report_csv(cpo, "CPO")[0]["expense"] == Decimal("7.25")


def test_unknown_columns_fail_closed():
    with pytest.raises(HistoricalReportError):
        parse_report_csv(b"sku;revenue\n123;200\n", "CPC")


class _Client:
    def __init__(self):
        self._token = {"access_token": "token"}

    def _access_token(self, force=False):
        return self._token


def test_historical_requests_all_windows_and_types_without_manual_files():
    service = HistoricalPerformanceReports(_Client())
    service._campaign_ids = lambda: ["123"]
    seen = []

    def generate(endpoint, payload, kind):
        seen.append((endpoint, payload, kind))
        return [{"sku": "3921245627", "expense": Decimal("1"), "kind": kind}]

    service._generate = generate
    result = service.load("2026-05-03", "2026-09-23")
    assert "error" not in result
    assert len([s for s in seen if s[2] == "CPC"]) == 3
    assert len([s for s in seen if s[2] == "CPO"]) == 3
    assert len(result["rows"]) == 6


def test_historical_failure_never_becomes_zero():
    service = HistoricalPerformanceReports(_Client())
    service._campaign_ids = lambda: ["123"]
    def failed(*_args):
        raise HistoricalReportError("OZON_HISTORICAL_REPORT_FAILED")
    service._generate = failed
    assert service.load("2026-05-03", "2026-09-23")["error"] is True
