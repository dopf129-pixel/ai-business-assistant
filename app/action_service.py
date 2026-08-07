from database import (
    save_action,
    get_actions
)


class ActionService:


    def create_actions(
        self,
        product_id,
        decisions
    ):

        created = 0

        existing = get_actions(product_id)


        existing_actions = []


        for row in existing:

            existing_actions.append(
                row[2]
            )


        for decision in decisions:


            action_name = decision.get(
                "action"
            )


            # защита от дублей
            if action_name in existing_actions:

                continue



            save_action(

                product_id,

                decision

            )


            created += 1



        return created



    def get_product_actions(
        self,
        product_id
    ):

        return get_actions(
            product_id
        )