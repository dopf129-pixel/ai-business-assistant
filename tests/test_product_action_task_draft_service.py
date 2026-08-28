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
    assert summary["counts"] == {"DRAFT": 1, "DISMISSED": 0}
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
