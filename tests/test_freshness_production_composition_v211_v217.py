import inspect

import assistant_app
from freshness_operational_runtime_factory import (
    create_freshness_operational_runtime,
    evaluate_freshness_operational_runtime_activation,
)


class _CompleteReader:
    def get_preparation_audit(self):
        return None

    def get_executor_admission_audit(self):
        return None

    def get_write_protocol_audit(self):
        return None

    def get_adapter_boundary_audit(self):
        return None


class _IncompleteReader:
    def get_preparation_audit(self):
        return None


def _entry(assistant):
    return assistant.orchestrator_service.entry_service


def test_v211_factory_activation_audit_is_read_only_and_not_lifecycle_readiness():
    result = evaluate_freshness_operational_runtime_activation(_CompleteReader())
    assert result["status"] == "FRESHNESS_DIAGNOSTICS_AUDIT_READY"
    assert result["activation_ready"] is True
    assert result["lifecycle_ready"] is False
    assert result["mutation_ready"] is False
    assert result["business_execution_ready"] is False
    assert result["persistent"] is False
    assert result["executed"] is False


def test_v212_factory_rejects_incomplete_reader_instead_of_wiring_broken_runtime():
    activation = evaluate_freshness_operational_runtime_activation(_IncompleteReader())
    assert activation["activation_ready"] is False
    assert create_freshness_operational_runtime(_IncompleteReader()) is None


def test_v213_create_assistant_default_signature_keeps_freshness_opt_in():
    signature = inspect.signature(assistant_app.create_assistant)
    parameter = signature.parameters["freshness_audit_reader"]
    assert parameter.default is None


def test_v214_default_create_assistant_does_not_wire_freshness_runtime():
    assistant = assistant_app.create_assistant()
    assert _entry(assistant).freshness_operational_runtime_service is None


def test_v215_explicit_complete_reader_wires_read_only_runtime():
    assistant = assistant_app.create_assistant(freshness_audit_reader=_CompleteReader())
    runtime = _entry(assistant).freshness_operational_runtime_service
    assert runtime is not None
    result = runtime.handle_text("freshness diagnostics")
    assert result["status"] == "FRESHNESS_DIAGNOSTICS_AUDIT_READY"
    assert result["activation_ready"] is True
    assert result["mutation_ready"] is False
    assert result["executed"] is False


def test_v216_incomplete_reader_fails_closed_to_old_composition():
    assistant = assistant_app.create_assistant(freshness_audit_reader=_IncompleteReader())
    assert _entry(assistant).freshness_operational_runtime_service is None


def test_v217_existing_period_profit_wiring_remains_in_create_assistant():
    source = inspect.getsource(assistant_app.create_assistant)
    assert "create_period_profit_query(" in source
    assert "mapping_registry=mapping_registry" in source
    assert "AssistantPeriodProfitRuntimeService" in source
    assert "period_profit_runtime_service" in source
    assert "freshness_operational_runtime_service" in source


def test_factory_never_creates_runtime_for_missing_reader():
    assert create_freshness_operational_runtime(None) is None
