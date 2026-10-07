from types import SimpleNamespace

from telegram_assistant_factory import _finance_transaction_client_for


def test_factory_reuses_period_profit_finance_client_for_transaction_categories():
    transaction_client = object()
    runtime = SimpleNamespace(
        query_service=SimpleNamespace(
            summary_service=SimpleNamespace(
                finance_service=SimpleNamespace(ozon=transaction_client)
            )
        )
    )

    assert _finance_transaction_client_for(runtime) is transaction_client


def test_factory_keeps_transaction_client_optional_without_period_profit():
    assert _finance_transaction_client_for(None) is None
