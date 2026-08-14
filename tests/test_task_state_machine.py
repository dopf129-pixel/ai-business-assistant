import sys

sys.path.insert(
    0,
    "app"
)

from core.task_states import TaskStatus
from core.task_state_machine import TaskStateMachine



def test_allowed_transitions():


    assert (
        TaskStateMachine.can_transition(
            TaskStatus.NEW,
            TaskStatus.DONE
        )
        is
        True
    )


    assert (
        TaskStateMachine.can_transition(
            TaskStatus.NEW,
            TaskStatus.CANCELLED
        )
        is
        True
    )


    assert (
        TaskStateMachine.can_transition(
            TaskStatus.PAUSED,
            TaskStatus.ACTIVE
        )
        is
        True
    )





def test_forbidden_transitions():


    assert (
        TaskStateMachine.can_transition(
            TaskStatus.CANCELLED,
            TaskStatus.DONE
        )
        is
        False
    )


    assert (
        TaskStateMachine.can_transition(
            TaskStatus.DONE,
            TaskStatus.ACTIVE
        )
        is
        False
    )