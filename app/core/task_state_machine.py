from core.task_states import TaskStatus



class TaskStateMachine:


    transitions = {


        TaskStatus.NEW: [

            TaskStatus.ACTIVE,

            TaskStatus.DONE,

            TaskStatus.SKIPPED,

            TaskStatus.CANCELLED

        ],


        TaskStatus.ACTIVE: [

            TaskStatus.DONE,

            TaskStatus.PAUSED,

            TaskStatus.CANCELLED

        ],


        TaskStatus.PAUSED: [

            TaskStatus.ACTIVE,

            TaskStatus.CANCELLED

        ],


        TaskStatus.DONE: [],


        TaskStatus.SKIPPED: [],


        TaskStatus.CANCELLED: []

    }





    @classmethod
    def can_transition(
        cls,
        current,
        target
    ):


        return (
            target
            in
            cls.transitions.get(
                current,
                []
            )
        )