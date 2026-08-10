import json
import os



class AssistantTaskService:


    def __init__(
        self,
        file_path="data/tasks.json"
    ):

        self.file_path = (
            file_path
        )

        self.tasks = {}

        self.load()



    def load(
        self
    ):


        if os.path.exists(
            self.file_path
        ):

            with open(
                self.file_path,
                "r",
                encoding="utf-8"
            ) as f:

                self.tasks = json.load(
                    f
                )



    def save(
        self
    ):


        os.makedirs(
            os.path.dirname(
                self.file_path
            ),
            exist_ok=True
        )


        with open(
            self.file_path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                self.tasks,
                f,
                ensure_ascii=False,
                indent=4
            )



    def create_task(
        self,
        user_id,
        title,
        actions
    ):


        self.tasks[str(user_id)] = {

            "task": title,

            "actions": actions

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


        task = (
            self.tasks
            .get(
                str(user_id)
            )
        )


        if not task:

            return {
                "error": False,
                "task": None
            }


        return {
            "error": False,
            "task": task
        }



    def get_next_action(
        self,
        user_id
    ):


        result = (
            self.get_task(
                user_id
            )
        )


        task = (
            result.get(
                "task"
            )
        )


        if not task:

            return {
                "error": False,
                "action": None
            }



        for action in task["actions"]:


            if (
                action.get("status")
                ==
                "NEW"
            ):

                return {
                    "error": False,
                    "action": action
                }



        return {
            "error": False,
            "action": None
        }



    def complete_action(
        self,
        user_id,
        title
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



        for action in task["actions"]:


            if action.get("title") == title:

                action["status"] = "DONE"



        self.save()


        return {
            "error": False,
            "updated": True
        }