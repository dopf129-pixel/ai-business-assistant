from pathlib import Path

from services.action_storage_service import ActionStorageService
from services.assistant_memory_storage_service import AssistantMemoryStorageService
from services.assistant_session_storage_service import AssistantSessionStorageService
from services.assistant_user_memory_storage_service import AssistantUserMemoryStorageService
from services.conversation_history_storage_service import ConversationHistoryStorageService
from services.product_action_task_draft_storage_service import (
    ProductActionTaskDraftStorageService,
)
from services.product_decision_history_storage_service import ProductDecisionHistoryStorageService
from services.product_decision_user_action_completion_storage_service import (
    ProductDecisionUserActionCompletionStorageService,
)
from services.store_analytics_service import StoreAnalyticsService
from services.store_report_storage_service import StoreReportStorageService
from services.tax_configuration_service import TaxConfigurationService
from services.tenant_context import reset_current_tenant_user_id, set_current_tenant_user_id


def _tenant(user_id, callback):
    token = set_current_tenant_user_id(user_id)
    try:
        return callback()
    finally:
        reset_current_tenant_user_id(token)


def test_shared_storage_instances_follow_request_tenant(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    cases = [
        (ActionStorageService(), [{"id": "a"}], [{"id": "b"}], []),
        (AssistantMemoryStorageService(), {"seller": "a"}, {"seller": "b"}, {}),
        (AssistantSessionStorageService(), ["a"], ["b"], []),
        (AssistantUserMemoryStorageService(), {"seller": "a"}, {"seller": "b"}, {}),
        (ConversationHistoryStorageService(), ["a"], ["b"], []),
        (ProductDecisionHistoryStorageService(), [{"seller": "a"}], [{"seller": "b"}], []),
        (ProductActionTaskDraftStorageService(), [{"draft": "a"}], [{"draft": "b"}], []),
        (ProductDecisionUserActionCompletionStorageService(), [{"completion": "a"}], [{"completion": "b"}], []),
        (StoreReportStorageService(), [{"seller": "a"}], [{"seller": "b"}], []),
    ]

    for service, value_a, value_b, legacy_empty in cases:
        path_a = _tenant("seller-a", lambda: Path(service.file_path))
        path_b = _tenant("seller-b", lambda: Path(service.file_path))
        legacy_path = Path(service.file_path)

        assert path_a != path_b
        assert "tenants" in path_a.parts
        assert "tenants" in path_b.parts
        assert "tenants" not in legacy_path.parts

        _tenant("seller-a", lambda: service.save(value_a))
        assert _tenant("seller-a", service.load) == value_a
        assert _tenant("seller-b", service.load) == legacy_empty

        _tenant("seller-b", lambda: service.save(value_b))
        assert _tenant("seller-a", service.load) == value_a
        assert _tenant("seller-b", service.load) == value_b
        assert service.load() == legacy_empty


def test_shared_tax_configuration_follows_request_tenant(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    service = TaxConfigurationService(environment={})

    path_a = _tenant("seller-a", lambda: Path(service.file_path))
    path_b = _tenant("seller-b", lambda: Path(service.file_path))

    assert path_a != path_b
    assert _tenant(
        "seller-a",
        lambda: service.save_policy("USN_INCOME", 6.0)["saved"],
    ) is True
    assert _tenant(
        "seller-b",
        lambda: service.get_policy()["configured"],
    ) is False
    assert _tenant(
        "seller-b",
        lambda: service.save_policy("USN_INCOME", 15.0)["saved"],
    ) is True
    assert _tenant(
        "seller-a",
        lambda: service.get_policy()["policy"]["tax_rate"],
    ) == 6.0
    assert _tenant(
        "seller-b",
        lambda: service.get_policy()["policy"]["tax_rate"],
    ) == 15.0


def test_explicit_storage_paths_remain_request_independent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    custom = tmp_path / "custom.json"
    service = ConversationHistoryStorageService(file_path=custom)

    assert _tenant("seller-a", lambda: Path(service.file_path)) == custom
    assert _tenant("seller-b", lambda: Path(service.file_path)) == custom

    service.save(["legacy-explicit"])
    assert _tenant("seller-a", service.load) == ["legacy-explicit"]
    assert _tenant("seller-b", service.load) == ["legacy-explicit"]


def test_legacy_defaults_are_preserved_without_tenant(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert ActionStorageService().file_path == Path("actions.json")
    assert AssistantMemoryStorageService().file_path == Path("assistant_memory.json")
    assert AssistantSessionStorageService().file_path == "assistant_session.json"
    assert AssistantUserMemoryStorageService().file_path == "assistant_user_memory.json"
    assert ConversationHistoryStorageService().file_path == Path("conversation_history.json")
    assert ProductDecisionHistoryStorageService().file_path == Path("data/product_decision_history.json")
    assert ProductActionTaskDraftStorageService().file_path == Path(
        "data/product_action_task_drafts.json"
    )
    assert ProductDecisionUserActionCompletionStorageService().file_path == Path(
        "data/product_decision_user_action_completion.json"
    )
    assert StoreReportStorageService().file_path == Path("store_reports.json")
    assert Path(TaxConfigurationService(environment={}).file_path) == (
        tmp_path / "data" / "tax_configuration.json"
    )


class _EmptyExpenseRepository:
    def get_expenses_by_date(self, expense_date):
        return []


def test_long_lived_period_profit_analytics_resolves_each_request_tax_policy(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    configuration = TaxConfigurationService(environment={})
    analytics = StoreAnalyticsService(
        tax_mode=None,
        tax_rate=0,
        minimum_tax_rate=0,
        advertising_cost=0,
        analysis_date="2026-09-10",
        expense_repository=_EmptyExpenseRepository(),
        tax_configuration_service=configuration,
    )
    profits = [
        {
            "error": False,
            "sales_count": 1,
            "gross_sales": 1000,
            "net_accrual": 700,
            "total_cost": 300,
            "gross_profit": 400,
        }
    ]

    _tenant(
        "seller-a",
        lambda: configuration.save_policy("USN_INCOME", 6.0),
    )
    _tenant(
        "seller-b",
        lambda: configuration.save_policy("USN_INCOME", 15.0),
    )

    results = [
        _tenant("seller-a", lambda: analytics.analyze(profits)),
        _tenant("seller-b", lambda: analytics.analyze(profits)),
        _tenant("seller-a", lambda: analytics.analyze(profits)),
    ]

    assert [result["tax"]["tax_rate"] for result in results] == [
        6.0,
        15.0,
        6.0,
    ]
    assert [result["tax"]["tax_amount"] for result in results] == [
        60.0,
        150.0,
        60.0,
    ]
