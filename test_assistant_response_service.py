import sys
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).parent / "app")
)


from services.assistant_response_service import (
    AssistantResponseService
)


class TestAssistantResponseService(
    unittest.TestCase
):


    def setUp(
        self
    ):

        self.service = (
            AssistantResponseService()
        )


    def test_build_response(
        self
    ):

        report = {
            "period": "28D"
        }


        dashboard = {
            "total": 5,
            "active": 3,
            "completed": 2
        }


        result = (
            self.service
            .build(
                report,
                dashboard
            )
        )


        self.assertFalse(
            result["error"]
        )


        self.assertEqual(
            result["report"],
            report
        )


        self.assertEqual(
            result["actions"],
            dashboard
        )


        self.assertEqual(
            result["message"],
            "Есть активных задач: 3"
        )


    def test_no_active_actions(
        self
    ):

        result = (
            self.service
            .build(
                {},
                {
                    "total": 2,
                    "active": 0,
                    "completed": 2
                }
            )
        )


        self.assertEqual(
            result["message"],
            "Активных задач нет"
        )


if __name__ == "__main__":
    unittest.main()