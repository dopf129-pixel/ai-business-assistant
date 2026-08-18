class AssistantChangeImpactService:


    def __init__(
        self
    ):

        self.service_map = {

            "assistant_action_generator_service.py": {

                "services": [
                    "AssistantActionPlanExecutorService",
                    "AssistantPlanningService"
                ],

                "tests": [
                    "test_action_context.py",
                    "test_memory_guided_actions.py"
                ],

                "docs": [
                    "ARCHITECTURE.md",
                    "TEST_MAP.md"
                ]
            },


            "assistant_task_service.py": {

                "services": [
                    "AssistantTaskService"
                ],

                "tests": [
                    "test_task_flow.py",
                    "test_task_lifecycle_flow.py"
                ],

                "docs": [
                    "ARCHITECTURE.md",
                    "CURRENT_STATE.md"
                ]
            }

        }



    def analyze(
        self,
        changed_file
    ):


        impact = self.service_map.get(
            changed_file,
            {
                "services": [],
                "tests": [],
                "docs": []
            }
        )


        return {

            "changed_file": changed_file,

            "affected_services":
                impact["services"],

            "affected_tests":
                impact["tests"],

            "affected_docs":
                impact["docs"]

        }