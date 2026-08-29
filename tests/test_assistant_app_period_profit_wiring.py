import inspect

import assistant_app


def test_create_assistant_wires_period_profit_runtime_into_entry():
    source = inspect.getsource(assistant_app.create_assistant)
    assert "create_period_profit_query(" in source
    assert "mapping_registry=mapping_registry" in source
    assert "AssistantPeriodProfitRuntimeService" in source
    assert "period_profit_runtime_service" in source
