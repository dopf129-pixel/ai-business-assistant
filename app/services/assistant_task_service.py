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


                self.tasks = json.load(
                    file
                )



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


            "task":

                task,


            "actions":

                actions,


            "pending_action":

                None

        }



        self.save()



        return {


            "error":

                False,


            "saved":

                True

        }








    def get_task(
        self,
        user_id
    ):


        return {


            "error":

                False,


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


                "error":

                    False,


                "action":

                    None

            }





        for action in task.get(
            "actions",
            []
        ):



            if action.get(
                "status"
            ) == "NEW":



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


                "error":

                    True,


                "message":

                    "Задача не найдена"

            }




        task["pending_action"] = action


        self.save()



        return {


            "error":

                False,


            "action":

                action

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


                "error":

                    False,


                "action":

                    None

            }





        return {


            "error":

                False,


            "action":

                task.get(
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


            "error":

                False

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


                "error":

                    False,


                "done":

                    0,


                "total":

                    0

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


            "error":

                False,


            "done":

                done,


            "total":

                len(
                    task.get(
                        "actions",
                        []
                    )
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


                "error":

                    False,


                "task":

                    None

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


                "title":

                    action.get(
                        "title",
                        ""
                    ),


                "status":

                    status,


                "icon":

                    icon

            })





        return {


            "error":

                False,


            "task":

                task.get(
                    "task"
                ),


            "progress":

                {


                    "done":

                        progress["done"],


                    "total":

                        progress["total"]

                },


            "actions":

                actions

        }








    def skip_action(
        self,
        user_id,
        title=None,
        reason=None
    ):


        task = self.tasks.get(
            str(user_id)
        )



        if not task:


            return {


                "error":

                    True,


                "message":

                    "Задача не найдена"

            }





        target = None



        for action in task.get(
            "actions",
            []
        ):



            if title:


                if action.get(
                    "title"
                ) == title:


                    target = action

                    break



            elif action.get(
                "status"
            ) == "NEW":


                target = action

                break





        if not target:


            return {


                "error":

                    True,


                "message":

                    "Действие не найдено"

            }





        target["status"] = "SKIPPED"



        target["result"] = {


            "message":

                "Шаг пропущен",


            "reason":

                reason

        }



        self.save()



        return {


            "error":

                False,


            "action":

                target

        }








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


                "error":

                    True,


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


                    "error":

                        False,


                    "updated":

                        True,


                    "action":

                        action

                }






        return {


            "error":

                True,


            "message":

                "Действие не найдено"

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