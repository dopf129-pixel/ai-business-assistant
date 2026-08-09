import sys
import unittest
from pathlib import Path
import tempfile


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.action_service import (
    ActionService
)

from services.action_pipeline_service import (
    ActionPipelineService
)

from services.action_history_service import (
    ActionHistoryService
)

from services.action_storage_service import (
    ActionStorageService
)


class TestActionFullFlow(
    unittest.TestCase
):


    def test_full_action_flow(
        self
    ):

        with tempfile.TemporaryDirectory() as folder:

            file_path = (
                Path(folder)
                /
                "actions.json"
            )


            storage = (
                ActionStorageService(
                    file_path=file_path
                )
            )


            history = (
                ActionHistoryService(
                    storage_service=storage
                )
            )


            pipeline = (
                ActionPipelineService(
                    action_service=ActionService(),
                    history_service=history
                )
            )


            recommendations = [
                {
                    "title": "Проверить товары роста"
                },
                {
                    "title": "Оценить рекламные расходы"
                }
            ]


            result = (
                pipeline.build_and_save(
                    recommendations
                )
            )


            self.assertFalse(
                result["error"]
            )


            self.assertEqual(
                len(
                    result["actions"]
                ),
                2
            )


            self.assertEqual(
                result["actions"][0]["status"],
                "NEW"
            )


            restored_history = (
                ActionHistoryService(
                    storage_service=storage
                )
            )


            saved = (
                restored_history
                .list_actions()
            )


            self.assertFalse(
                saved["error"]
            )


            self.assertEqual(
                saved["count"],
                2
            )


            self.assertEqual(
                saved["actions"][0]["title"],
                "Проверить товары роста"
            )


if __name__ == "__main__":
    unittest.main()