class AssistantDependencyValidatorService:


    def validate(
        self,
        actions
    ):


        graph = {}


        action_names = set()



        for action in actions:


            title = action.get(
                "title"
            )


            action_names.add(
                title
            )


            graph[title] = (
                action.get(
                    "depends_on",
                    []
                )
            )



        # Проверка отсутствующих зависимостей

        for action, dependencies in graph.items():


            for dependency in dependencies:


                if dependency not in action_names:


                    return {

                        "error":
                            True,

                        "message":
                            "Dependency not found",

                        "dependency":
                            dependency

                    }



        # Проверка циклов зависимостей

        visited = set()

        recursion_stack = set()



        def check_cycle(
            node
        ):


            if node in recursion_stack:

                return True



            if node in visited:

                return False



            visited.add(
                node
            )


            recursion_stack.add(
                node
            )



            for dependency in graph.get(
                node,
                []
            ):


                if check_cycle(
                    dependency
                ):

                    return True



            recursion_stack.remove(
                node
            )


            return False



        for node in graph:


            if check_cycle(
                node
            ):


                return {

                    "error":
                        True,

                    "message":
                        "Circular dependency detected",

                    "node":
                        node

                }



        return {

            "error":
                False,

            "valid":
                True

        }