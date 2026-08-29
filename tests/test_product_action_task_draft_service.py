from app.services.product_action_task_draft_service import (
    ProductActionTaskDraftService,
)
from app.services.product_action_task_draft_storage_service import (
    ProductActionTaskDraftStorageService,
)


class MemoryStorage:
    def __init__(self):
        self.records = []
        self.save_calls = 0

    def load(self):
        return list(self.records)

    def save(self, records):
        self.records = list(records)
        self.save_calls += 1


def _decision():
    return {
        "sku": "hook-2",
        "decision_type": "REPLENISH_NORMAL",
        "priority": "HIGH",
        "recorded_at": "decision-time",
        "profit_per_unit": 35.1,
        "margin_percent": 36.5,
        "current_stock": 8,
        "sales_velocity": 4.0,
        "days_of_stock": 2.0,
        "economics_basis": "ESTIMATED_RETURNS",
    }


def _proposal():
    return {
        "proposal_type": "REVIEW_REPLENISHMENT",
        "action_required": True,
    }


def test_confirmation_creates_non_executable_task_draft_once():
    storage = MemoryStorage()
    service = ProductActionTaskDraftService(
        storage_service=storage,
        clock=lambda: "draft-time",
    )

    first = service.create_from_confirmation(_decision(), _proposal())
    repeated = service.create_from_confirmation(_decision(), _proposal())

    assert first["saved"] is True
    assert repeated["saved"] is False
    assert first["task_draft"]["status"] == "DRAFT"
    assert first["task_draft"]["execution_allowed"] is False
    assert first["task_draft"]["executed"] is False
    assert len(service.list_drafts()) == 1
    assert storage.save_calls == 1
    assert first["task_draft"]["current_stock"] == 8
    assert first["task_draft"]["economics_basis"] == "ESTIMATED_RETURNS"
    assert first["task_draft"]["events"] == [{
        "event_id": "e1",
        "event_type": "CREATED",
        "from_status": None,
        "to_status": "DRAFT",
        "source": "CONFIRMATION",
        "occurred_at": "draft-time",
        "executed": False,
    }]


def test_dismissal_closes_matching_draft_without_execution():
    service = ProductActionTaskDraftService(clock=lambda: "now")
    service.create_from_confirmation(_decision(), _proposal())

    dismissed = service.dismiss(
        "hook-2", "REVIEW_REPLENISHMENT", "decision-time"
    )
    repeated = service.dismiss(
        "hook-2", "REVIEW_REPLENISHMENT", "decision-time"
    )

    assert dismissed["task_draft"]["status"] == "DISMISSED"
    assert repeated["saved"] is False
    assert dismissed["executed"] is False


def test_summary_exposes_drafts_but_no_executions():
    service = ProductActionTaskDraftService(clock=lambda: "now")
    service.create_from_confirmation(_decision(), _proposal())

    summary = service.summary()

    assert summary["total"] == 1
    assert summary["counts"] == {
        "DRAFT": 1,
        "STALE": 0,
        "DISMISSED": 0,
        "ARCHIVED": 0,
    }
    assert summary["executed_count"] == 0
    assert summary["drafts"][0]["sku"] == "hook-2"


def test_draft_requires_stable_decision_snapshot_and_actionable_proposal():
    service = ProductActionTaskDraftService()

    missing_time = service.create_from_confirmation(
        {**_decision(), "recorded_at": None}, _proposal()
    )
    monitoring = service.create_from_confirmation(
        _decision(), {**_proposal(), "action_required": False}
    )

    assert missing_time["code"] == "INVALID_TASK_DRAFT_SOURCE"
    assert monitoring["code"] == "INVALID_TASK_DRAFT_SOURCE"


def test_json_storage_recovers_task_drafts(tmp_path):
    path = tmp_path / "task-drafts.json"
    storage = ProductActionTaskDraftStorageService(file_path=path)
    service = ProductActionTaskDraftService(
        storage_service=storage,
        clock=lambda: "now",
    )
    service.create_from_confirmation(_decision(), _proposal())

    restored = ProductActionTaskDraftService(storage_service=storage)

    assert restored.latest_for_sku("hook-2")["status"] == "DRAFT"
    assert not path.with_suffix(".json.tmp").exists()


def test_reconcile_marks_previous_decision_draft_stale():
    service = ProductActionTaskDraftService(clock=lambda: "now")
    created = service.create_from_confirmation(_decision(), _proposal())

    result = service.reconcile(
        sku="hook-2",
        current_proposal_type="REVIEW_MARGIN",
        current_decision_recorded_at="new-decision-time",
    )

    assert result["stale_count"] == 1
    assert result["executed"] is False
    assert service.latest_for_sku("hook-2")["status"] == "STALE"
    assert created["task_draft"]["status"] == "DRAFT"


def test_reconcile_keeps_current_snapshot_draft_active():
    service = ProductActionTaskDraftService(clock=lambda: "now")
    service.create_from_confirmation(_decision(), _proposal())

    result = service.reconcile(
        sku="hook-2",
        current_proposal_type="REVIEW_REPLENISHMENT",
        current_decision_recorded_at="decision-time",
    )

    assert result["stale_count"] == 0
    assert service.latest_for_sku("hook-2")["status"] == "DRAFT"


def test_archive_is_idempotent_terminal_and_non_executable():
    service = ProductActionTaskDraftService(clock=lambda: "now")
    created = service.create_from_confirmation(_decision(), _proposal())
    draft_id = created["task_draft"]["draft_id"]

    archived = service.archive(draft_id)
    repeated = service.archive(draft_id)
    reconfirmed = service.create_from_confirmation(_decision(), _proposal())

    assert archived["task_draft"]["status"] == "ARCHIVED"
    assert repeated["saved"] is False
    assert reconfirmed["task_draft"]["status"] == "ARCHIVED"
    assert reconfirmed["saved"] is False
    assert archived["executed"] is False
    assert [
        event["event_type"]
        for event in archived["task_draft"]["events"]
    ] == ["CREATED", "ARCHIVED"]


def test_loaded_legacy_drafts_receive_review_identifier():
    storage = MemoryStorage()
    storage.records = [{
        "draft_key": "hook-2|REVIEW_REPLENISHMENT|decision-time",
        "sku": "hook-2",
        "status": "DRAFT",
    }]

    service = ProductActionTaskDraftService(storage_service=storage)

    assert service.latest_for_sku("hook-2")["draft_id"] == "d1"
    detail = service.get("d1")
    assert detail["legacy_history_unavailable"] is True
    assert detail["audit_events"] == []


def test_audit_trail_records_real_transitions_without_idempotent_noise():
    timestamps = iter(["created", "dismissed", "reopened", "stale"])
    service = ProductActionTaskDraftService(clock=lambda: next(timestamps))
    created = service.create_from_confirmation(_decision(), _proposal())
    service.dismiss("hook-2", "REVIEW_REPLENISHMENT", "decision-time")
    service.dismiss("hook-2", "REVIEW_REPLENISHMENT", "decision-time")
    service.create_from_confirmation(_decision(), _proposal())
    service.reconcile("hook-2", "REVIEW_MARGIN", "new-time")

    detail = service.get(created["task_draft"]["draft_id"])
    event_types = [
        event["event_type"] for event in detail["audit_events"]
    ]

    assert event_types == [
        "CREATED",
        "DISMISSED",
        "REOPENED",
        "MARKED_STALE",
    ]
    assert all(event["executed"] is False for event in detail["audit_events"])
    assert detail["legacy_history_unavailable"] is False


def test_archived_draft_cannot_be_dismissed_or_reopened():
    service = ProductActionTaskDraftService(clock=lambda: "now")
    created = service.create_from_confirmation(_decision(), _proposal())
    draft_id = created["task_draft"]["draft_id"]
    service.archive(draft_id)

    dismissed = service.dismiss(
        "hook-2", "REVIEW_REPLENISHMENT", "decision-time"
    )
    reopened = service.create_from_confirmation(_decision(), _proposal())

    assert dismissed["task_draft"]["status"] == "ARCHIVED"
    assert dismissed["saved"] is False
    assert reopened["task_draft"]["status"] == "ARCHIVED"
    assert len(service.get(draft_id)["audit_events"]) == 2
