import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.action_pipeline_service import (
    ActionPipelineService
)


class FakeActionService:

    def build(
        self,
        recommendations
    ):

        return {
            "error": False,
            "actions": [
                {
                    "title": "Проверить товары",
                    "status": "NEW"
                }
            ]
        }


class FakeHistoryService:

    def __init__(
        self
    ):

        self.actions = []


    def save_action(
        self,
        action
    ):

        self.actions.append(
            action
        )


class TestActionPipelineService(
    unittest.TestCase
):


    def test_build_and_save(
        self
    ):

        history = (
            FakeHistoryService()
        )


        pipeline = (
            ActionPipelineService(
                action_service=(
                    FakeActionService()
                ),
                history_service=history
            )
        )


        result = (
            pipeline.build_and_save(
                [
                    "Проверить товары"
                ]
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            len(result["actions"]),
            1
        )


        self.assertEqual(
            len(history.actions),
            1
        )


    def test_action_error(
        self
    ):

        class ErrorActionService:

            def build(
                self,
                recommendations
            ):

                return {
                    "error": True,
                    "message": "Ошибка создания действий"
                }


        history = (
            FakeHistoryService()
        )


        pipeline = (
            ActionPipelineService(
                action_service=(
                    ErrorActionService()
                ),
                history_service=history
            )
        )


        result = (
            pipeline.build_and_save(
                []
            )
        )


        self.assertTrue(
            result["error"]
        )


        self.assertEqual(
            len(history.actions),
            0
        )


if __name__ == "__main__":
    unittest.main()