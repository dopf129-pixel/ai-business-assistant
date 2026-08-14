import sys

sys.path.insert(
    0,
    "app"
)

from core.task_states import TaskStatus



def test_task_statuses_exist():


    assert (
        TaskStatus.NEW
        ==
        "NEW"
    )


    assert (
        TaskStatus.DONE
        ==
        "DONE"
    )


    assert (
        TaskStatus.CANCELLED
        ==
        "CANCELLED"
    )


    assert (
        TaskStatus.SKIPPED
        ==
        "SKIPPED"
    )


    assert (
        TaskStatus.PAUSED
        ==
        "PAUSED"
    )



def test_all_statuses_are_available():


    statuses = TaskStatus.all()


    assert (
        "NEW"
        in
        statuses
    )


    assert (
        "PAUSED"
        in
        statuses
    )