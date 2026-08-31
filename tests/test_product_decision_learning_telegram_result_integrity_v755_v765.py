from copy import deepcopy

from app.services.assistant_button_handler_service import (
    AssistantButtonHandlerService,
)


class StubAssistant:
    pass


class QueryStub:
    def __init__(self, history):
        self.decision_history_service = history


class HistoryStub:
    def __init__(self, summary=None, records=None, error=None):
        self.summary = summary
        self.records = records
        self.error = error
        self.history_calls = []

    def learning_summary(self):
        if self.error is not None:
            raise self.error
        return deepcopy(self.summary)

    def history(self, sku, limit=None):
        self.history_calls.append((sku, limit))
        if self.error is not None:
            raise self.error
        return deepcopy(self.records)


def _handler(history):
    return AssistantButtonHandlerService(
        assistant=StubAssistant(),
        product_business_decision_query=QueryStub(history),
    )


def _summary(**overrides):
    result = {
        "error": False,
        "products_count": 2,
        "decision_snapshots_count": 3,
        "feedback_count": 2,
        "feedback_counts": {
            "USEFUL": 1,
            "NOT_RELEVANT": 1,
        },
        "outcome_count": 1,
        "outcome_counts": {
            "PRIORITY_DECREASED": 1,
            "PRIORITY_INCREASED": 0,
            "DECISION_CHANGED": 0,
        },
    }
    result.update(overrides)
    return result


def _record(**overrides):
    result = {
        "sku": "hook-2",
        "decision_type": "HOLD_STOCK",
        "priority": "LOW",
        "recorded_at": "2026-08-28T10:00:00+00:00",
        "feedback": "USEFUL",
        "outcome": "PRIORITY_DECREASED",
    }
    result.update(overrides)
    return result


def test_v755_learning_summary_non_dict_fails_closed():
    result = _handler(HistoryStub(summary=None)).handle(
        "product_decision_learning_summary"
    )

    assert result["error"] is True
    assert result["message"] == "Итоги обучения решений недоступны"
    assert "Товаров в памяти: 0" not in result["message"]


def test_v756_learning_summary_requires_explicit_boolean_error():
    missing = _handler(HistoryStub(summary={"products_count": 0})).handle(
        "product_decision_learning_summary"
    )
    explicit = _handler(HistoryStub(summary={"error": True})).handle(
        "product_decision_learning_summary"
    )

    assert missing["error"] is True
    assert explicit["error"] is True


def test_v757_learning_summary_missing_count_does_not_become_zero():
    summary = _summary()
    summary.pop("outcome_count")

    result = _handler(HistoryStub(summary=summary)).handle(
        "product_decision_learning_summary"
    )

    assert result["error"] is True
    assert "Наблюдений после оценок: 0" not in result["message"]


def test_v758_learning_summary_rejects_bool_negative_and_inconsistent_counts():
    boolean_count = _summary(feedback_count=True)
    negative_count = _summary(products_count=-1)
    mismatch = _summary(feedback_count=1)

    results = [
        _handler(HistoryStub(summary=item)).handle(
            "product_decision_learning_summary"
        )
        for item in (boolean_count, negative_count, mismatch)
    ]

    assert all(item["error"] is True for item in results)


def test_v759_legitimate_zero_learning_evidence_remains_success():
    zero = {
        "error": False,
        "products_count": 0,
        "decision_snapshots_count": 0,
        "feedback_count": 0,
        "feedback_counts": {
            "USEFUL": 0,
            "NOT_RELEVANT": 0,
        },
        "outcome_count": 0,
        "outcome_counts": {
            "PRIORITY_DECREASED": 0,
            "PRIORITY_INCREASED": 0,
            "DECISION_CHANGED": 0,
        },
    }

    result = _handler(HistoryStub(summary=zero)).handle(
        "product_decision_learning_summary"
    )

    assert result["error"] is False
    assert "Товаров в памяти: 0" in result["message"]
    assert "Оценок: 0" in result["message"]


def test_v760_learning_summary_exception_is_stable_non_secret_failure():
    result = _handler(
        HistoryStub(summary=None, error=OSError("secret path detail"))
    ).handle("product_decision_learning_summary")

    assert result["error"] is True
    assert "secret path detail" not in str(result)


def test_v761_none_history_is_unknown_not_empty_success():
    history = HistoryStub(records=None)

    result = _handler(history).handle(
        "product_decision_history:hook-2"
    )

    assert result["error"] is True
    assert "пока пуста" not in result["message"]
    assert history.history_calls == [("hook-2", 5)]


def test_v762_malformed_history_item_fails_closed():
    result = _handler(
        HistoryStub(records=[None])
    ).handle("product_decision_history:hook-2")

    assert result["error"] is True


def test_v763_cross_sku_history_cannot_be_presented_for_requested_product():
    result = _handler(
        HistoryStub(records=[_record(sku="other")])
    ).handle("product_decision_history:hook-2")

    assert result["error"] is True
    assert "other" not in result["message"]


def test_v764_invalid_feedback_or_outcome_is_not_mislabeled():
    invalid_feedback = _handler(
        HistoryStub(records=[_record(feedback="UNKNOWN")])
    ).handle("product_decision_history:hook-2")
    invalid_outcome = _handler(
        HistoryStub(records=[_record(outcome="UNKNOWN")])
    ).handle("product_decision_history:hook-2")

    assert invalid_feedback["error"] is True
    assert invalid_outcome["error"] is True
    assert "Неактуально" not in invalid_feedback["message"]


def test_v765_valid_empty_and_valid_history_remain_read_only_success():
    empty = _handler(HistoryStub(records=[])).handle(
        "product_decision_history:hook-2"
    )
    populated = _handler(
        HistoryStub(records=[_record()])
    ).handle("product_decision_history:hook-2")

    assert empty["error"] is False
    assert empty["decision_history"] == []
    assert populated["error"] is False
    assert "Оценка: Полезно" in populated["message"]
    assert "Срочность рекомендации снизилась" in populated["message"]
