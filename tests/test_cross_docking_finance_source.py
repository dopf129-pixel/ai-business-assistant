from datetime import date, timedelta

from api.ozon_client import OzonClient
from services.cross_docking_finance_source import OzonCrossDockingFinanceSource


class _PagedFinanceClient:
    def __init__(self):
        self.calls = []

    def get_accruals_by_day_page(self, day, **options):
        self.calls.append((day, options.get("last_id")))
        observer = options.get("request_attempt_observer")
        if callable(observer):
            observer("/v1/finance/accrual/by-day")
        if not options.get("last_id"):
            return {"error": False, "accruals": [], "last_id": "next"}
        return {"error": False, "accruals": [], "last_id": ""}


def test_finance_pages_resume_and_only_publish_after_all_days_are_complete():
    client = _PagedFinanceClient()
    source = OzonCrossDockingFinanceSource(client)
    start = date(2026, 8, 24)
    end = date(2026, 8, 25)

    first = source.collect_window(
        date_from=start,
        date_to=end,
        max_requests=3,
    )

    assert first.complete is False
    assert first.days_complete == 1
    assert first.checkpoint is not None
    assert first.request_count == 3
    assert "2026-08-24" in first.responses_by_day()
    assert "2026-08-25" not in first.responses_by_day()

    second = source.collect_window(
        date_from=start,
        date_to=end,
        checkpoint=first.checkpoint,
        max_requests=2,
    )

    assert second.complete is True
    assert second.days_complete == 2
    assert set(second.responses_by_day()) == {"2026-08-24", "2026-08-25"}
    assert second.request_count == 1
    assert client.calls == [
        ("2026-08-24", ""),
        ("2026-08-24", "next"),
        ("2026-08-25", ""),
        ("2026-08-25", "next"),
    ]


def test_finance_source_reuses_cached_complete_days_without_refetching():
    client = _PagedFinanceClient()
    source = OzonCrossDockingFinanceSource(client)
    start = date(2026, 8, 24)
    end = date(2026, 8, 25)
    cached = {
        start.isoformat(): {
            "error": False,
            "accruals": [],
            "last_id": "",
            "pages_loaded": 1,
        }
    }

    result = source.collect_window(
        date_from=start,
        date_to=end,
        cached_responses=cached,
    )

    assert result.complete is True
    assert result.days_complete == 2
    assert result.request_count == 2
    assert client.calls == [("2026-08-25", ""), ("2026-08-25", "next")]


def test_finance_source_rejects_cached_page_with_unfinished_cursor():
    client = _PagedFinanceClient()
    source = OzonCrossDockingFinanceSource(client)
    start = date(2026, 8, 24)

    result = source.collect_window(
        date_from=start,
        date_to=start,
        cached_responses={
            start.isoformat(): {
                "error": False,
                "accruals": [],
                "last_id": "unfinished",
                "pages_loaded": 1,
            }
        },
    )

    assert result.complete is True
    assert result.request_count == 2
    assert client.calls == [("2026-08-24", ""), ("2026-08-24", "next")]


def test_accrual_type_api_adapter_accepts_one_attempt_budget_options():
    client = object.__new__(OzonClient)
    calls = []
    observer = lambda _endpoint=None: None
    client._post = lambda endpoint, data, **options: calls.append(
        (endpoint, data, options)
    ) or {"error": False, "accrual_types": []}

    response = client.get_accrual_types(
        timeout=8,
        max_attempts=1,
        total_timeout=10,
        request_attempt_observer=observer,
    )

    assert response["error"] is False
    assert calls == [
        (
            "/v1/finance/accrual/types",
            {},
            {
                "timeout": 8,
                "max_attempts": 1,
                "total_timeout": 10,
                "request_attempt_observer": observer,
            },
        )
    ]
