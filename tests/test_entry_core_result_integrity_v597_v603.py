from services.assistant_core_service import (
    AssistantCoreService,
)
from services.assistant_entry_service import (
    AssistantEntryService,
)


class _Runtime:

    def __init__(self, result):
        self.result = result
        self.calls = []

    def handle_text(
        self,
        text,
        user_id=None,
    ):
        self.calls.append(
            {
                "text": text,
                "user_id": user_id,
            }
        )
        return self.result


class _MainFlow:

    def __init__(self, result=None):
        self.result = (
            {
                "error": False,
                "message": "main",
            }
            if result is None
            else result
        )
        self.calls = []

    def process(
        self,
        text,
        report,
        context=None,
        user_id=None,
    ):
        self.calls.append(
            {
                "text": text,
                "report": report,
                "context": context,
                "user_id": user_id,
            }
        )
        return self.result


class _Orchestrator:

    def __init__(self, result):
        self.result = result

    def process(
        self,
        text,
        context=None,
        user_id=None,
    ):
        return self.result


def _entry(**runtime):
    return AssistantEntryService(
        main_flow_service=_MainFlow(),
        **runtime,
    )


def test_v597_task_persistence_runtime_malformed_result_fails_closed():

    entry = _entry(
        task_persistence_operational_runtime_service=(
            _Runtime({})
        )
    )

    assert entry.handle(
        "diagnostics",
        user_id=42,
    ) == {
        "error": True,
        "message":
            "INVALID_TASK_PERSISTENCE_RUNTIME_RESULT",
    }


def test_v598_freshness_runtime_malformed_result_fails_closed():

    entry = _entry(
        freshness_operational_runtime_service=(
            _Runtime([])
        )
    )

    assert entry.handle(
        "freshness"
    ) == {
        "error": True,
        "message":
            "INVALID_FRESHNESS_RUNTIME_RESULT",
    }


def test_v599_mapping_runtime_malformed_results_fail_closed():

    cases = [
        (
            "period_profit_mapping_recovery_runtime_service",
            None,
            "INVALID_MAPPING_RECOVERY_RUNTIME_RESULT",
        ),
        (
            "period_profit_mapping_admin_runtime_service",
            {
                "error": None,
            },
            "INVALID_MAPPING_ADMIN_RUNTIME_RESULT",
        ),
    ]

    for name, downstream, expected in cases:
        entry = _entry(
            **{
                name: _Runtime(
                    downstream
                )
            }
        )

        result = entry.handle(
            "mapping"
        )

        if downstream is None:
            assert (
                result["error"]
                is False
            )
            continue

        assert result == {
            "error": True,
            "message": expected,
        }


def test_v600_return_review_runtime_malformed_result_fails_closed():

    entry = _entry(
        return_operation_review_runtime_service=(
            _Runtime(
                {
                    "error": "false",
                }
            )
        )
    )

    assert entry.handle(
        "return review"
    ) == {
        "error": True,
        "message":
            "INVALID_RETURN_REVIEW_RUNTIME_RESULT",
    }


def test_v601_period_profit_runtime_malformed_result_fails_closed():

    entry = _entry(
        period_profit_runtime_service=(
            _Runtime(
                "bad"
            )
        )
    )

    assert entry.handle(
        "profit"
    ) == {
        "error": True,
        "message":
            "INVALID_PERIOD_PROFIT_RUNTIME_RESULT",
    }


def test_v602_valid_direct_runtime_failure_is_preserved():

    downstream = {
        "error": True,
        "message":
            "PERIOD_PROFIT_QUERY_UNAVAILABLE",
        "executed": False,
    }

    entry = _entry(
        period_profit_runtime_service=(
            _Runtime(
                downstream
            )
        )
    )

    result = entry.handle(
        "profit"
    )

    assert result is downstream


def test_v603_core_malformed_orchestrator_result_fails_closed():

    cases = [
        None,
        [],
        {},
        {
            "error": None,
        },
        {
            "error": "false",
        },
    ]

    for downstream in cases:
        core = AssistantCoreService(
            orchestrator_service=(
                _Orchestrator(
                    downstream
                )
            )
        )

        assert core.ask(
            "текст"
        ) == {
            "error": True,
            "message":
                "INVALID_ORCHESTRATOR_RESULT",
        }


def test_v603_core_preserves_valid_explicit_failure():

    downstream = {
        "error": True,
        "message":
            "INVALID_BUSINESS_SERVICE_RESULT",
    }

    core = AssistantCoreService(
        orchestrator_service=(
            _Orchestrator(
                downstream
            )
        )
    )

    result = core.ask(
        "текст"
    )

    assert result is downstream
