from services.task_persistence_operational_service import (
    TaskPersistenceOperationalService,
)


class _Fake:
    def __init__(self, load, persistence, lock):
        self.load = load
        self.persistence = persistence
        self.lock = lock

    def get_load_diagnostics(self):
        return self.load

    def get_persistence_diagnostics(self):
        return self.persistence

    def get_write_lock_diagnostics(self):
        return self.lock


def _base():
    load = {
        "error": False,
        "status": "TASK_PERSISTENCE_LOAD_DIAGNOSTICS",
        "source_state": "LOADED",
        "issue_count": 0,
        "issues": [],
        "loaded_task_count": 1,
        "read_only": True,
        "executed": False,
    }
    persistence = {
        "error": False,
        "status": "TASK_PERSISTENCE_DIAGNOSTICS",
        "load_source_state": "LOADED",
        "last_save_state": "SUCCEEDED",
        "last_save_issue": None,
        "last_save_rolled_back": False,
        "optimistic_concurrency_guard": True,
        "write_lock_guard": True,
        "directory_fsync_required": True,
        "last_lock_release_issue": None,
        "loaded_task_count": 1,
        "read_only": True,
        "executed": False,
    }
    lock = {
        "error": False,
        "status": "TASK_WRITE_LOCK_DIAGNOSTICS",
        "inspection_state": "ABSENT",
        "lock_present": False,
        "ownership_state": "NONE",
        "stale_proven": False,
        "automatic_recovery_allowed": False,
        "manual_lock_removal_allowed": False,
        "manual_intervention_required": False,
        "path_exposed": False,
        "read_only": True,
        "executed": False,
    }
    return load, persistence, lock


def test_forged_unreadable_load_without_expected_issue_fails_closed():
    load, persistence, lock = _base()
    load["source_state"] = "UNREADABLE"
    load["loaded_task_count"] = 0

    report = TaskPersistenceOperationalService(
        _Fake(load, persistence, lock)
    ).build_report()

    assert report["error"] is True
    assert report["code"] == "TASK_PERSISTENCE_LOAD_DIAGNOSTICS_INVALID"


def test_forged_success_with_failure_issue_fails_closed():
    load, persistence, lock = _base()
    persistence["last_save_issue"] = "TASK_FILE_WRITE_ERROR"

    report = TaskPersistenceOperationalService(
        _Fake(load, persistence, lock)
    ).build_report()

    assert report["error"] is True
    assert report["code"] == "TASK_PERSISTENCE_DIAGNOSTICS_INVALID"


def test_forged_failed_save_without_rollback_fails_closed():
    load, persistence, lock = _base()
    persistence["last_save_state"] = "FAILED"
    persistence["last_save_issue"] = "TASK_FILE_STALE_WRITE"
    persistence["last_save_rolled_back"] = False

    report = TaskPersistenceOperationalService(
        _Fake(load, persistence, lock)
    ).build_report()

    assert report["error"] is True
    assert report["code"] == "TASK_PERSISTENCE_DIAGNOSTICS_INVALID"


def test_forged_durability_warning_with_wrong_code_fails_closed():
    load, persistence, lock = _base()
    persistence["last_save_state"] = "SUCCEEDED_WITH_DURABILITY_WARNING"
    persistence["last_save_issue"] = "TASK_FILE_WRITE_ERROR"

    report = TaskPersistenceOperationalService(
        _Fake(load, persistence, lock)
    ).build_report()

    assert report["error"] is True
    assert report["code"] == "TASK_PERSISTENCE_DIAGNOSTICS_INVALID"


def test_forged_present_lock_claiming_known_absence_fails_closed():
    load, persistence, lock = _base()
    lock["inspection_state"] = "PRESENT"
    lock["lock_present"] = True
    lock["ownership_state"] = "NONE"
    lock["manual_intervention_required"] = True

    report = TaskPersistenceOperationalService(
        _Fake(load, persistence, lock)
    ).build_report()

    assert report["error"] is True
    assert report["code"] == "TASK_WRITE_LOCK_DIAGNOSTICS_INVALID"


def test_forged_check_error_claiming_absent_lock_fails_closed():
    load, persistence, lock = _base()
    lock["inspection_state"] = "CHECK_ERROR"
    lock["lock_present"] = False
    lock["ownership_state"] = "UNKNOWN"
    lock["manual_intervention_required"] = True

    report = TaskPersistenceOperationalService(
        _Fake(load, persistence, lock)
    ).build_report()

    assert report["error"] is True
    assert report["code"] == "TASK_WRITE_LOCK_DIAGNOSTICS_INVALID"
