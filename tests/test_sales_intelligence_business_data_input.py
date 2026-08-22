import sys

sys.path.insert(
    0,
    "app"
)

from services.assistant_entry_service import (
    AssistantEntryService
)
from services.assistant_recommendation_service import (
    AssistantRecommendationService
)
from services.assistant_planning_service import (
    AssistantPlanningService
)
from services.assistant_action_generator_service import (
    AssistantActionGeneratorService
)


class FakeProductService:

    def load_products(self):

        return [
            (
                "product-1",
                "offer-1",
                "sku-1"
            )
        ]


class FakePeriodProfitService:

    def calculate_period_profit(
        self,
        date_from,
        date_to,
        products
    ):

        assert products == [
            {
                "product_id": "product-1",
                "offer_id": "offer-1",
                "sku": "sku-1"
            }
        ]

        gross_sales = (
            150
            if date_from == "2026-08-22"
            else 200
        )

        return {
            "error": False,
            "profits": [
                {
                    "sales_count": 1,
                    "gross_sales": gross_sales,
                    "net_accrual": gross_sales,
                    "total_cost": 50,
                    "gross_profit": (
                        gross_sales - 50
                    )
                }
            ]
        }


class FakeAnalyticsService:

    def get_period(self):

        return {
            "error": False,
            "date_from": "2026-08-22",
            "date_to": "2026-08-22"
        }

    def get_previous_period(self):

        return {
            "error": False,
            "date_from": "2026-08-21",
            "date_to": "2026-08-21"
        }

    def analyze(
        self,
        profits,
        previous_result=None
    ):

        gross_sales = profits[0][
            "gross_sales"
        ]

        result = {
            "error": False,
            "store_profit": {
                "gross_sales": gross_sales,
                "gross_profit": (
                    gross_sales - 50
                )
            },
            "business_profit": {
                "business_profit": (
                    gross_sales - 50
                ),
                "margin_percent": 50
            }
        }

        if previous_result:

            result["comparison"] = {
                "error": False,
                "comparison": {
                    "revenue": {
                        "change_percent": -25
                    }
                }
            }

        return result


class UserPathMainFlow:

    def process(
        self,
        text,
        report,
        context=None,
        user_id=None
    ):

        recommendations = (
            AssistantRecommendationService()
            .analyze(
                report
            )
        )

        plan = (
            AssistantPlanningService()
            .build_plan(
                recommendations[
                    "recommendations"
                ]
            )
        )

        action = (
            AssistantActionGeneratorService()
            .generate(
                plan["plan"][0]
            )
            ["action"]
        )

        return {
            "error": False,
            "text": text,
            "report": report,
            "action": action
        }


def test_user_request_builds_sales_context_from_existing_data_layer():

    entry = (
        AssistantEntryService(
            main_flow_service=(
                UserPathMainFlow()
            ),
            product_service=(
                FakeProductService()
            ),
            period_profit_service=(
                FakePeriodProfitService()
            ),
            analytics_service=(
                FakeAnalyticsService()
            )
        )
    )

    result = entry.handle(
        "Почему упали продажи?",
        user_id=1
    )

    report = result["report"]
    action = result["action"]

    assert report["sales_down"] is True

    assert report[
        "sales_context"
    ]["profits"][0][
        "gross_sales"
    ] == 150

    assert report[
        "sales_context"
    ]["previous_result"][
        "store_profit"
    ]["gross_sales"] == 200

    assert action["type"] == "sales"

    assert action[
        "context"
    ]["profits"][0][
        "gross_sales"
    ] == 150

    assert action[
        "context"
    ]["previous_result"][
        "store_profit"
    ]["gross_sales"] == 200


def test_entry_preserves_legacy_report_without_data_dependencies():

    class RecordingMainFlow:

        def process(
            self,
            text,
            report,
            context=None,
            user_id=None
        ):

            return report

    entry = AssistantEntryService(
        main_flow_service=(
            RecordingMainFlow()
        )
    )

    report = entry.handle(
        "Покажи состояние бизнеса"
    )

    assert report == {
        "sales_down": True,
        "low_stock": True
    }
