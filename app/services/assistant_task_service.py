import json
import os
from copy import deepcopy


from core.task_states import TaskStatus
from core.task_state_machine import TaskStateMachine




class AssistantTaskService:


    def __init__(
        self,
        file_path="data/tasks.json"
    ):

        self.file_path = file_path

        self.tasks = {}

        self.load()



    def load(
        self
    ):


        if not os.path.exists(
            self.file_path
        ):

            self.tasks = {}

            return



        try:

            with open(
                self.file_path,
                "r",
                encoding="utf-8"
            ) as file:

                loaded = json.load(
                    file
                )

                self.tasks = (
                    loaded
                    if isinstance(loaded, dict)
                    else {}
                )


                self._reconcile_loaded_tasks()


        except Exception:

            self.tasks = {}





    def save(
        self
    ):


        folder = os.path.dirname(
            self.file_path
        )


        if (
            folder
            and
            not os.path.exists(
                folder
            )
        ):

            os.makedirs(
                folder
            )



        temporary_path = (
            self.file_path
            + ".tmp"
        )

        try:

            with open(
                temporary_path,
                "w",
                encoding="utf-8"
            ) as file:


                json.dump(
                    self.tasks,
                    file,
                    ensure_ascii=False,
                    indent=4
                )

                file.flush()

                os.fsync(
                    file.fileno()
                )


            os.replace(
                temporary_path,
                self.file_path
            )


        finally:

            if os.path.exists(
                temporary_path
            ):

                os.remove(
                    temporary_path
                )





    def _task_is_terminal(
        self,
        task
    ):


        return (
            isinstance(
                task,
                dict
            )
            and
            task.get(
                "status"
            )
            in (
                TaskStatus.DONE,
                TaskStatus.SKIPPED,
                TaskStatus.CANCELLED
            )
        )


    def _terminal_task_error(
        self,
        task
    ):


        status = (
            task.get(
                "status"
            )
            if isinstance(
                task,
                dict
            )
            else None
        )


        if status == TaskStatus.DONE:

            message = "Задача завершена"


        elif status == TaskStatus.CANCELLED:

            message = "Задача отменена"


        else:

            message = "Задача закрыта"


        return {
            "error": True,
            "message": message,
            "status": status
        }


    def _finalize_if_complete(
        self,
        task
    ):


        if not isinstance(
            task,
            dict
        ):

            return False


        if task.get(
            "status"
        ) in (
            TaskStatus.CANCELLED,
            TaskStatus.SKIPPED
        ):

            return False


        actions = task.get(
            "actions",
            []
        )


        if (
            not isinstance(
                actions,
                list
            )
            or
            not actions
        ):

            return False


        if not all(
            isinstance(
                action,
                dict
            )
            and
            action.get(
                "status"
            )
            in (
                "DONE",
                "SKIPPED"
            )
            for action in actions
        ):

            return False


        changed = (
            task.get(
                "status"
            )
            !=
            TaskStatus.DONE
        )


        task["status"] = TaskStatus.DONE


        task["pending_action"] = None


        return changed


    def _reconcile_loaded_tasks(
        self
    ):


        if not isinstance(
            self.tasks,
            dict
        ):

            return


        for task in self.tasks.values():


            self._finalize_if_complete(
                task
            )


    def create_task(
        self,
        user_id,
        task,
        actions
    ):


        self.tasks[str(user_id)] = {


            "task": task,


            "status": TaskStatus.ACTIVE,


            "actions": actions,


            "pending_action": None


        }



        self.save()



        return {


            "error": False,


            "saved": True


        }





    def get_task(
        self,
        user_id
    ):


        return {


            "error": False,


            "task": self.tasks.get(
                str(user_id)
            )


        }





    def change_task_status(
        self,
        user_id,
        new_status
    ):


        task = self.tasks.get(
            str(user_id)
        )


        if not task:


            return {


                "error": True,


                "message": "Задача не найдена"


            }



        current_status = task.get(
            "status",
            TaskStatus.ACTIVE
        )



        if not TaskStateMachine.can_transition(
            current_status,
            new_status
        ):


            return {


                "error": True,


                "message":
                    (
                        "Недопустимый переход: "
                        +
                        current_status
                        +
                        " -> "
                        +
                        new_status
                    )


            }



        task["status"] = new_status


        self.save()



        return {


            "error": False,


            "status": new_status


        }
    def cancel_task(
        self,
        user_id
    ):


        task = self.tasks.get(
            str(user_id)
        )


        if not task:


            return {


                "error": True,


                "message": "Задача не найдена"


            }



        status_result = self.change_task_status(
            user_id,
            TaskStatus.CANCELLED
        )


        if status_result.get(
            "error"
        ):


            return status_result



        task["pending_action"] = None


        self.save()



        return {


            "error": False,


            "cancelled": True,


            "task": task.get(
                "task"
            )


        }





    def get_current_action(
        self,
        user_id
    ):


        task = self.tasks.get(
            str(user_id)
        )


        if not task:

            return {

                "error":
                    False,

                "action":
                    None

            }


        if self._task_is_terminal(
            task
        ):


            return {

                "error":
                    False,

                "action":
                    None

            }


        pending = task.get(
            "pending_action"
        )


        if pending:

            return {

                "error":
                    False,

                "action":
                    pending

            }



        for action in task.get(
            "actions",
            []
        ):


            if action.get(
                "status"
            ) != "NEW":

                continue



            dependencies = (
                action.get(
                    "depends_on",
                    []
                )
            )


            can_execute = True



            for dependency in dependencies:


                dependency_done = False


                for completed_action in task.get(
                    "actions",
                    []
                ):


                    if (
                        completed_action.get(
                            "title"
                        )
                        ==
                        dependency

                        and

                        completed_action.get(
                            "status"
                        )
                        ==
                        "DONE"
                    ):

                        dependency_done = True



                if not dependency_done:

                    can_execute = False



            if not can_execute:

                continue



            condition = (
                action.get(
                    "condition"
                )
            )


            if condition:


                contains = (
                    condition.get(
                        "contains"
                    )
                )


                if contains:


                    allowed = False


                    for completed_action in task.get(
                        "actions",
                        []
                    ):


                        result = (
                            completed_action.get(
                                "result",
                                {}
                            )
                        )


                        if isinstance(
                            result,
                            dict
                        ):


                            message = (
                                result.get(
                                    "message",
                                    ""
                                )
                            )


                            if contains in message:

                                allowed = True



                    if not allowed:


                        action["status"] = "SKIPPED"


                        action["skip_reason"] = (
                            "Условие не выполнено"
                        )


                        self._finalize_if_complete(
                            task
                        )


                        self.save()


                        continue



            return {

                "error":
                    False,

                "action":
                    action

            }



        return {

            "error":
                False,

            "action":
                None

        }


    def get_next_action(
        self,
        user_id
    ):


        return self.get_current_action(
            user_id
        )





    def set_pending_action(
        self,
        user_id,
        action
    ):


        task = self.tasks.get(
            str(user_id)
        )


        if not task:


            return {


                "error": True,


                "message": "Задача не найдена"


            }



        if self._task_is_terminal(
            task
        ):


            return self._terminal_task_error(
                task
            )


        task["pending_action"] = action


        self.save()



        return {


            "error": False,


            "action": action


        }





    def get_pending_action(
        self,
        user_id
    ):


        task = self.tasks.get(
            str(user_id)
        )


        if not task:


            return {


                "error": False,


                "action": None


            }



        return {


            "error": False,


            "action": task.get(
                "pending_action"
            )


        }





    def clear_pending_action(
        self,
        user_id
    ):


        task = self.tasks.get(
            str(user_id)
        )


        if task:


            task["pending_action"] = None


            self.save()



        return {


            "error": False


        }
    def resolve_action(
        self,
        task,
        action
    ):


        if isinstance(
            action,
            dict
        ):

            return action



        if isinstance(
            action,
            str
        ):


            for item in task.get(
                "actions",
                []
            ):


                if item.get(
                    "title"
                ) == action:


                    return item



        return None





    def start_action(
        self,
        user_id,
        action
    ):


        task = self.tasks.get(
            str(user_id)
        )


        if not task:


            return {


                "error": True,


                "message": "Задача не найдена"


            }



        if self._task_is_terminal(
            task
        ):


            return self._terminal_task_error(
                task
            )



        action = self.resolve_action(
            task,
            action
        )



        if not action:


            return {


                "error": True,


                "message": "Действие не найдено"


            }



        action["status"] = "IN_PROGRESS"



        task["pending_action"] = action



        self.save()



        return {


            "error": False,


            "action": action


        }





    def complete_action(
        self,
        user_id,
        action,
        result=None
    ):


        task = self.tasks.get(
            str(user_id)
        )


        if not task:


            return {


                "error": True,


                "message": "Задача не найдена"


            }



        if self._task_is_terminal(
            task
        ):


            return self._terminal_task_error(
                task
            )



        action = self.resolve_action(
            task,
            action
        )



        if not action:


            return {


                "error": True,


                "message": "Действие не найдено"


            }



        action["status"] = "DONE"



        if result is not None:


            action["result"] = result



        task["pending_action"] = None


        self._finalize_if_complete(
            task
        )



        self.save()



        return {


            "error": False,


            "action": action


        }





    def skip_action(
        self,
        user_id,
        action
    ):


        task = self.tasks.get(
            str(user_id)
        )


        if not task:


            return {


                "error": True,


                "message": "Задача не найдена"


            }



        if self._task_is_terminal(
            task
        ):


            return self._terminal_task_error(
                task
            )



        action = self.resolve_action(
            task,
            action
        )



        if not action:


            return {


                "error": True,


                "message": "Действие не найдено"


            }



        action["status"] = "SKIPPED"



        task["pending_action"] = None


        self._finalize_if_complete(
            task
        )



        self.save()



        return {


            "error": False,


            "action": action


        }
    def update_action_status(
        self,
        user_id,
        action,
        status
    ):


        task = self.tasks.get(
            str(user_id)
        )


        if not task:


            return {


                "error": True,


                "message": "Задача не найдена"


            }



        if self._task_is_terminal(
            task
        ):


            return self._terminal_task_error(
                task
            )


        action = self.resolve_action(
            task,
            action
        )



        if not action:


            return {


                "error": True,


                "message": "Действие не найдено"


            }



        action["status"] = status



        self._finalize_if_complete(
            task
        )


        self.save()



        return {


            "error": False,


            "action": action


        }





    def get_task_progress(
        self,
        user_id
    ):


        task = self.tasks.get(
            str(user_id)
        )


        if not task:


            return {


                "error": False,


                "done": 0,


                "total": 0


            }



        done = 0



        for action in task.get(
            "actions",
            []
        ):


            if action.get(
                "status"
            ) in (
                "DONE",
                "SKIPPED"
            ):


                done += 1



        return {


            "error": False,


            "done": done,


            "total": len(
                task.get(
                    "actions",
                    []
                )
            )


        }





    def is_task_completed(
        self,
        user_id
    ):


        progress = self.get_task_progress(
            user_id
        )


        return {


            "error": False,


            "completed":
                (
                    progress["total"] > 0
                    and
                    progress["done"]
                    ==
                    progress["total"]
                )


        }





    def get_task_status(
        self,
        user_id
    ):


        task = self.tasks.get(
            str(user_id)
        )


        if not task:


            return {


                "error": False,


                "task": None


            }



        progress = self.get_task_progress(
            user_id
        )



        actions = []



        for action in task.get(
            "actions",
            []
        ):


            status = action.get(
                "status",
                "NEW"
            )



            if status == "DONE":

                icon = "✅"


            elif status == "IN_PROGRESS":

                icon = "🔄"


            elif status == "SKIPPED":

                icon = "⏭️"


            else:

                icon = "⏳"



            actions.append({

                "title": action.get(
                    "title",
                    ""
                ),

                "status": status,

                "icon": icon

            })



        return {


            "error": False,


            "task": task.get(
                "task"
            ),


            "status": task.get(
                "status",
                TaskStatus.ACTIVE
            ),


            "progress": {


                "done": progress["done"],


                "total": progress["total"]


            },


            "actions": actions


        }

    def get_task_history(
        self,
        user_id
    ):


        task = self.tasks.get(
            str(user_id)
        )


        if not task:


            return {


                "error": False,


                "task": None,


                "history": []


            }



        history = []



        for action in task.get(
            "actions",
            []
        ):


            if action.get(
                "status"
            ) in (
                "DONE",
                "SKIPPED"
            ):


                history.append({

                    "title":
                        action.get(
                            "title",
                            ""
                        ),

                    "status":
                        action.get(
                            "status"
                        ),

                    "message":
                        (
                            action.get(
                                "skip_reason",
                                "Условие не выполнено"
                            )
                            if
                            action.get(
                                "status"
                            )
                            ==
                            "SKIPPED"
                            else
                            "Действие выполнено"
                        ),

    "result":
        action.get(
            "result"
        )
})



        return {


            "error": False,


            "task": task.get(
                "task"
            ),


            "history": history


        }





    def pause_task(
        self,
        user_id
    ):


        return self.change_task_status(
            user_id,
            TaskStatus.PAUSED
        )





    def resume_task(
        self,
        user_id
    ):


        return self.change_task_status(
            user_id,
            TaskStatus.ACTIVE
        )





    def has_active_task(
        self,
        user_id
    ):


        task = self.tasks.get(
            str(user_id)
        )


        return {


            "error": False,


            "active":
                (
                    task is not None
                    and
                    task.get(
                        "status"
                    )
                    not in
                    (
                        TaskStatus.DONE,
                        TaskStatus.SKIPPED,
                        TaskStatus.CANCELLED
                    )
                )


        }

    def fail_action(
        self,
        user_id,
        title,
        error
    ):


        task = (
            self.tasks
            .get(
                str(user_id)
            )
        )


        if not task:

            return {

                "error": True,

                "message":
                    "Задача не найдена"

            }



        if self._task_is_terminal(
            task
        ):


            return self._terminal_task_error(
                task
            )


        for action in task.get(
            "actions",
            []
        ):


            if (
                action.get(
                    "title"
                )
                ==
                title
            ):


                action["status"] = "FAILED"


                action["error"] = error


                pending = task.get(
                    "pending_action"
                )


                if (
                    isinstance(
                        pending,
                        dict
                    )
                    and
                    pending.get(
                        "title"
                    )
                    ==
                    title
                ):


                    task["pending_action"] = None


                self.save()


                return {

                    "error": False,

                    "action": action

                }



        return {

            "error": True,

            "message":
                "Действие не найдено"

        }


    def prepare_retry_action(
        self,
        user_id,
        title,
        attempt
    ):


        task = (
            self.tasks
            .get(
                str(user_id)
            )
        )


        if not task:

            return {
                "error": True,
                "message": "Задача не найдена"
            }


        if self._task_is_terminal(
            task
        ):


            return self._terminal_task_error(
                task
            )


        action = self.resolve_action(
            task,
            title
        )


        if (
            not action
            or
            action.get(
                "status"
            )
            !=
            "FAILED"
        ):

            return {
                "error": True,
                "message": "FAILED действие не найдено"
            }


        try:

            next_attempt = int(
                attempt
            )


        except (
            TypeError,
            ValueError
        ):

            return {
                "error": True,
                "message": "Invalid retry attempt"
            }


        if next_attempt < 1:

            return {
                "error": True,
                "message": "Invalid retry attempt"
            }


        action["status"] = "NEW"


        action["attempt"] = next_attempt


        action.pop(
            "error",
            None
        )


        action.pop(
            "retry_allowed",
            None
        )


        task["pending_action"] = None


        self.save()


        return {
            "error": False,
            "action": action
        }


    def apply_replan(
        self,
        user_id,
        actions,
        reason=None
    ):


        task = (
            self.tasks
            .get(
                str(user_id)
            )
        )


        if not task:

            return {
                "error": True,
                "message": "Task not found"
            }


        if self._task_is_terminal(
            task
        ):


            return self._terminal_task_error(
                task
            )


        if not isinstance(
            actions,
            list
        ):

            return {
                "error": True,
                "message": "Invalid replanned actions"
            }


        task["actions"] = deepcopy(
            actions
        )


        task["replanned"] = True


        task["replan_requested"] = False


        if reason is not None:

            task["replan_reason"] = reason


        task["pending_action"] = None


        self.save()


        return {
            "error": False,
            "plan": task["actions"]
        }


    def request_replan(
        self,
        user_id,
        reason=None
    ):


        task_result = (
            self.get_task(
                user_id
            )
        )


        task = (
            task_result.get(
                "task"
            )
        )


        if not task:


            return {

                "error":
                    True,

                "message":
                    "Task not found"

            }



        if self._task_is_terminal(
            task
        ):


            return self._terminal_task_error(
                task
            )


        task["replan_requested"] = True


        task["replan_reason"] = (
            reason
            or
            "Execution failed"
        )


        self.save()



        return {

            "error":
                False,

            "replan_requested":
                True,

            "reason":
                task["replan_reason"]

        }


    def get_status(
        self,
        user_id
    ):


        return self.get_task_status(
            user_id
        )