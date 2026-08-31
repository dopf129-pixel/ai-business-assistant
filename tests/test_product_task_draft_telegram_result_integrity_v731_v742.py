from services.assistant_button_handler_service import (
    AssistantButtonHandlerService,
)


class _Assistant:

    def ask(
        self,
        text,
        user_id=None,
    ):

        return {
            "error": False,
            "message": "ok",
        }


class _DraftService:

    def __init__(
        self,
        summary_result,
        list_result,
        detail_result,
        archive_result,
    ):

        self.summary_result = summary_result
        self.list_result = list_result
        self.detail_result = detail_result
        self.archive_result = archive_result

    def summary(self):
        return self.summary_result

    def list_drafts(self):
        return self.list_result

    def get(
        self,
        draft_id,
    ):
        return self.detail_result

    def archive(
        self,
        draft_id,
    ):
        return self.archive_result


class _QueueService:

    def __init__(
        self,
        result,
    ):

        self.result = result

    def prioritize(
        self,
        drafts,
        limit=10,
    ):

        return self.result


class _ReadinessService:

    def __init__(
        self,
        summary_result=None,
        detail_result=None,
    ):

        self.summary_result = summary_result
        self.detail_result = detail_result

    def summarize(
        self,
        drafts,
    ):

        return self.summary_result

    def evaluate(
        self,
        draft,
    ):

        return self.detail_result


class _Query:

    def __init__(
        self,
        draft_service,
        queue_service=None,
        readiness_service=None,
    ):

        self.action_task_draft_service = draft_service
        self.task_draft_review_queue_service = (
            queue_service
        )
        self.task_draft_readiness_service = (
            readiness_service
        )


def _draft(
    status="DRAFT",
):

    return {
        "draft_id": "d1",
        "sku": "hook-2",
        "proposal_type":
            "REVIEW_REPLENISHMENT",
        "status": status,
        "priority": "HIGH",
        "execution_allowed": False,
        "executed": False,
    }


def _summary():

    return {
        "error": False,
        "total": 1,
        "counts": {
            "DRAFT": 1,
            "STALE": 0,
            "DISMISSED": 0,
            "ARCHIVED": 0,
        },
        "drafts": [
            _draft(),
        ],
        "audit_events_count": 1,
        "executed_count": 0,
    }


def _queue():

    item = _draft()
    item.update({
        "review_priority": "HIGH",
        "review_score": 140,
        "review_reasons": [
            "CURRENT_DRAFT",
            "SOURCE_PRIORITY_HIGH",
            "REPLENISHMENT_REVIEW",
        ],
    })

    return {
        "error": False,
        "total_reviewable": 1,
        "priority_counts": {
            "URGENT": 0,
            "HIGH": 1,
            "NORMAL": 0,
            "LOW": 0,
        },
        "items": [
            item,
        ],
        "executed_count": 0,
    }


def _readiness():

    return {
        "error": False,
        "draft_id": "d1",
        "review_status":
            "READY_FOR_REVIEW",
        "review_ready": True,
        "required_checks": [],
        "missing_fields": [],
        "review_blockers": [],
        "execution_ready": False,
        "execution_blockers": [
            "EXECUTION_WORKFLOW_NOT_CONNECTED",
            "REPLENISHMENT_QUANTITY_POLICY_MISSING",
        ],
        "executed": False,
    }


def _readiness_summary():

    item = _draft()
    item[
        "readiness"
    ] = _readiness()

    return {
        "error": False,
        "counts": {
            "READY_FOR_REVIEW": 1,
            "NEEDS_DATA_OR_REFRESH": 0,
        },
        "items": [
            item,
        ],
        "execution_ready_count": 0,
        "executed_count": 0,
    }


def _detail():

    return {
        "error": False,
        "code": None,
        "task_draft": _draft(),
        "audit_events": [],
        "legacy_history_unavailable":
            True,
        "executed": False,
        "execution_allowed": False,
    }


def _archive(
    saved=True,
):

    return {
        "error": False,
        "code": None,
        "task_draft": _draft(
            status="ARCHIVED"
        ),
        "saved": saved,
        "executed": False,
        "execution_allowed": False,
    }


_DEFAULT = object()


def _handler(
    summary_result=_DEFAULT,
    list_result=_DEFAULT,
    detail_result=_DEFAULT,
    archive_result=_DEFAULT,
    queue_result=_DEFAULT,
    readiness_summary=_DEFAULT,
    readiness_detail=_DEFAULT,
):

    service = _DraftService(
        (
            _summary()
            if summary_result is _DEFAULT
            else summary_result
        ),
        (
            [
                _draft(),
            ]
            if list_result is _DEFAULT
            else list_result
        ),
        (
            _detail()
            if detail_result is _DEFAULT
            else detail_result
        ),
        (
            _archive()
            if archive_result is _DEFAULT
            else archive_result
        ),
    )
    queue_service = (
        _QueueService(
            (
                _queue()
                if queue_result is _DEFAULT
                else queue_result
            )
        )
        if queue_result is not False
        else None
    )
    readiness_service = (
        _ReadinessService(
            (
                _readiness_summary()
                if readiness_summary is _DEFAULT
                else readiness_summary
            ),
            (
                _readiness()
                if readiness_detail is _DEFAULT
                else readiness_detail
            ),
        )
        if (
            readiness_summary is not False
            or readiness_detail is not False
        )
        else None
    )
    query = _Query(
        service,
        queue_service,
        readiness_service,
    )

    return AssistantButtonHandlerService(
        assistant=_Assistant(),
        product_business_decision_query=query,
    )


def test_v731_malformed_summary_fails_closed():

    for malformed in (
        None,
        [],
        {},
        {
            "error": False,
        },
    ):

        handler = _handler(
            summary_result=malformed,
            queue_result=False,
            readiness_summary=False,
            readiness_detail=False,
        )

        assert handler.handle(
            "product_action_task_drafts"
        ) == {
            "error": True,
            "message":
                "INVALID_PRODUCT_TASK_DRAFT_SUMMARY_RESULT",
            "executed": False,
        }


def test_v732_explicit_summary_failure_remains_failure():

    handler = _handler(
        summary_result={
            "error": True,
            "message":
                "draft storage unavailable",
        },
        queue_result=False,
        readiness_summary=False,
        readiness_detail=False,
    )

    result = handler.handle(
        "product_action_task_drafts"
    )

    assert result["error"] is True
    assert result[
        "message"
    ] == "draft storage unavailable"
    assert result[
        "executed"
    ] is False


def test_v733_summary_counts_cannot_invent_zero_states():

    invalid = _summary()
    invalid[
        "counts"
    ].pop(
        "ARCHIVED"
    )

    handler = _handler(
        summary_result=invalid,
        queue_result=False,
        readiness_summary=False,
        readiness_detail=False,
    )

    assert handler.handle(
        "product_action_task_drafts"
    )[
        "message"
    ] == "INVALID_PRODUCT_TASK_DRAFT_SUMMARY_RESULT"


def test_v734_malformed_list_stops_before_review_queue():

    handler = _handler(
        list_result={
            "bad": True,
        },
        readiness_summary=False,
        readiness_detail=False,
    )

    assert handler.handle(
        "product_action_task_drafts"
    ) == {
        "error": True,
        "message":
            "INVALID_PRODUCT_TASK_DRAFT_LIST_RESULT",
        "executed": False,
    }


def test_v735_malformed_review_queue_fails_closed():

    handler = _handler(
        queue_result={
            "error": False,
            "items": [],
        },
        readiness_summary=False,
        readiness_detail=False,
    )

    assert handler.handle(
        "product_action_task_drafts"
    ) == {
        "error": True,
        "message":
            "INVALID_PRODUCT_TASK_DRAFT_REVIEW_QUEUE_RESULT",
        "executed": False,
    }


def test_v736_malformed_readiness_summary_fails_closed():

    handler = _handler(
        readiness_summary={
            "error": False,
            "counts": {},
            "items": [],
            "execution_ready_count": 0,
            "executed_count": 0,
        },
    )

    assert handler.handle(
        "product_action_task_drafts"
    ) == {
        "error": True,
        "message":
            "INVALID_PRODUCT_TASK_DRAFT_READINESS_SUMMARY_RESULT",
        "executed": False,
    }


def test_v737_valid_summary_queue_readiness_remain_non_executable():

    handler = _handler()

    result = handler.handle(
        "product_action_task_drafts"
    )

    assert result["error"] is False
    assert result[
        "executed"
    ] is False
    assert result[
        "summary"
    ]["executed_count"] == 0
    assert result[
        "review_queue"
    ]["executed_count"] == 0
    assert result[
        "readiness_summary"
    ]["execution_ready_count"] == 0
    assert "Готово к исполнению: 0" in result[
        "message"
    ]


def test_v738_malformed_detail_result_fails_closed():

    handler = _handler(
        detail_result={
            "error": False,
        },
    )

    assert handler.handle(
        "product_task_draft:view:d1"
    ) == {
        "error": True,
        "message":
            "INVALID_PRODUCT_TASK_DRAFT_DETAIL_RESULT",
        "executed": False,
    }


def test_v739_explicit_detail_failure_remains_failure():

    handler = _handler(
        detail_result={
            "error": True,
            "code":
                "TASK_DRAFT_NOT_FOUND",
            "task_draft": None,
            "saved": False,
            "executed": False,
            "execution_allowed": False,
        },
    )

    result = handler.handle(
        "product_task_draft:view:d1"
    )

    assert result == {
        "error": True,
        "message":
            "Черновик задачи не найден",
        "executed": False,
    }


def test_v740_malformed_detail_readiness_fails_closed():

    handler = _handler(
        readiness_detail={
            "error": False,
            "review_status":
                "READY_FOR_REVIEW",
        },
    )

    assert handler.handle(
        "product_task_draft:view:d1"
    ) == {
        "error": True,
        "message":
            "INVALID_PRODUCT_TASK_DRAFT_READINESS_RESULT",
        "executed": False,
    }


def test_v741_malformed_archive_result_cannot_claim_archived():

    handler = _handler(
        archive_result={
            "error": False,
            "saved": True,
        },
    )

    result = handler.handle(
        "product_task_draft:archive:d1"
    )

    assert result == {
        "error": True,
        "message":
            "INVALID_PRODUCT_TASK_DRAFT_ARCHIVE_RESULT",
        "executed": False,
    }
    assert "архивирован" not in result[
        "message"
    ]


def test_v742_valid_idempotent_archive_remains_non_executable():

    handler = _handler(
        archive_result=_archive(
            saved=False
        ),
    )

    result = handler.handle(
        "product_task_draft:archive:d1"
    )

    assert result["error"] is False
    assert result[
        "saved"
    ] is False
    assert result[
        "task_draft"
    ][
        "status"
    ] == "ARCHIVED"
    assert result[
        "executed"
    ] is False
    assert "Выполнение не запускалось" in result[
        "message"
    ]
