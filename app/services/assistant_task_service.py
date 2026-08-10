import json
import os



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

                self.tasks = json.load(file)


        except Exception:

            self.tasks = {}



    def save(
        self
    ):


        folder = os.path.dirname(
            self.file_path
        )


        if folder and not os.path.exists(folder):

            os.makedirs(folder)



        with open(
            self.file_path,
            "w",
            encoding="utf-8"
        ) as file:


            json.dump(
                self.tasks,
                file,
                ensure_ascii=False,
                indent=4
            )



    def create_task(
        self,
        user_id,
        task,
        actions
    ):


        self.tasks[str(user_id)] = {

            "task": task,

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


        return {

            "error": False,

            "task":
                self.tasks.get(
                    str(user_id)
                )
        }



    def get_next_action(
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



        for action in task.get(
            "actions",
            []
        ):


            if action.get(
                "status"
            ) == "NEW":


                return {

                    "error": False,

                    "action": action
                }



        return {

            "error": False,

            "action": None
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

                "error": False,

                "action": None
            }



        for action in task.get(
            "actions",
            []
        ):


            if action.get(
                "status"
            ) == "IN_PROGRESS":


                return {

                    "error": False,

                    "action": action
                }



        return {

            "error": False,

            "action": None
        }



    def get_last_completed_action(
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



        completed = None



        for action in task.get(
            "actions",
            []
        ):


            if action.get(
                "status"
            ) == "DONE":

                completed = action



        return {

            "error": False,

            "action":
                completed
        }



    def start_action(
        self,
        user_id,
        title
    ):


        return self.update_action_status(
            user_id,
            title,
            "IN_PROGRESS"
        )



    def complete_action(
        self,
        user_id,
        title,
        result=None
    ):


        return self.update_action_status(
            user_id,
            title,
            "DONE",
            result
        )



    def update_action_status(
        self,
        user_id,
        title,
        status,
        result=None
    ):


        task = self.tasks.get(
            str(user_id)
        )


        if not task:

            return {

                "error": True,

                "message":
                    "Задача не найдена"
            }



        for action in task.get(
            "actions",
            []
        ):


            if action.get(
                "title"
            ) == title:


                action["status"] = status


                if result is not None:

                    action["result"] = result


                self.save()


                return {

                    "error": False,

                    "updated": True,

                    "action": action
                }



        return {

            "error": True,

            "message":
                "Действие не найдено"
        }