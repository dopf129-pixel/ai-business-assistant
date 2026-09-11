import os
import sys
import unittest


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from api.ozon_client import OzonClient  # noqa: E402
from services.returns_buyout_facts_source import ReturnsBuyoutFactsSource  # noqa: E402


class RecordingOzonClient(OzonClient):
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def _post(self, endpoint, data, timeout=20, max_attempts=3):
        self.calls.append(
            {
                "endpoint": endpoint,
                "data": data,
                "timeout": timeout,
                "max_attempts": max_attempts,
            }
        )
        return self.responses.pop(0)


class ReturnsFlowOzon:
    def __init__(self):
        self.client = RecordingOzonClient(
            [
                {
                    "postings": [
                        {
                            "posting_number": "posting-1",
                            "status": "delivered",
                            "cancel_reason_id": 0,
                            "products": [
                                {
                                    "sku": 3921245627,
                                    "offer_id": "hook-2",
                                    "quantity": 1,
                                }
                            ],
                        }
                    ],
                    "cursor": "cursor-1",
                    "has_next": True,
                },
                {
                    "postings": [
                        {
                            "posting_number": "posting-2",
                            "status": "cancelled",
                            "cancel_reason_id": 502,
                            "products": [
                                {
                                    "sku": 3921245627,
                                    "offer_id": "hook-2",
                                    "quantity": 1,
                                }
                            ],
                        }
                    ],
                    "cursor": "cursor-2",
                    "has_next": False,
                },
            ]
        )

    def get_fbo_postings(self, **kwargs):
        return self.client.get_fbo_postings(**kwargs)

    def get_returns(self, **kwargs):
        return {
            "returns": [],
            "has_next": False,
        }


class OzonFboV3ReturnsUnitEconomicsTests(unittest.TestCase):
    def test_fbo_listing_uses_v3_cursor_contract_and_normalizes_old_shape(self):
        client = RecordingOzonClient(
            [
                {
                    "postings": [{"posting_number": "posting-1"}],
                    "cursor": "next-page",
                    "has_next": True,
                },
                {
                    "postings": [{"posting_number": "posting-2"}],
                    "cursor": "done",
                    "has_next": False,
                },
            ]
        )
        client.FBO_POSTINGS_V3_PAGE_SIZE = 1

        result = client.get_fbo_postings(
            since="2026-08-12T00:00:00Z",
            to="2026-09-11T23:59:59Z",
            limit=2,
            offset=0,
            direction="DESC",
        )

        self.assertFalse(result["error"])
        self.assertEqual(
            [item["posting_number"] for item in result["result"]["postings"]],
            ["posting-1", "posting-2"],
        )
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[0]["endpoint"], "/v3/posting/fbo/list")
        self.assertEqual(client.calls[0]["data"]["cursor"], "")
        self.assertEqual(client.calls[1]["data"]["cursor"], "next-page")
        self.assertEqual(client.calls[0]["data"]["sort_dir"], "desc")
        self.assertNotIn("offset", client.calls[0]["data"])
        self.assertNotIn("dir", client.calls[0]["data"])
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])

    def test_hook_2_returns_facts_no_longer_fail_when_v3_postings_are_available(self):
        ozon = ReturnsFlowOzon()
        ozon.client.FBO_POSTINGS_V3_PAGE_SIZE = 1
        source = ReturnsBuyoutFactsSource(ozon)
        source.POSTINGS_PAGE_SIZE = 2

        result = source.get(
            sku="3921245627",
            since="2026-08-12",
            to="2026-09-11",
        )

        self.assertFalse(result["error"])
        self.assertTrue(result["postings_complete"])
        self.assertTrue(result["returns_available"])
        self.assertTrue(result["returns_complete"])
        self.assertEqual(result["total_units"], 2)
        self.assertEqual(result["delivered_units"], 1)
        self.assertEqual(result["cancelled_units"], 1)
        self.assertEqual(result["customer_cancelled_units"], 1)
        self.assertEqual(
            {call["endpoint"] for call in ozon.client.calls},
            {"/v3/posting/fbo/list"},
        )

    def test_repeated_v3_cursor_fails_closed_instead_of_looping(self):
        client = RecordingOzonClient(
            [
                {
                    "postings": [{"posting_number": "posting-1"}],
                    "cursor": "repeat",
                    "has_next": True,
                },
                {
                    "postings": [{"posting_number": "posting-2"}],
                    "cursor": "repeat",
                    "has_next": True,
                },
            ]
        )
        client.FBO_POSTINGS_V3_PAGE_SIZE = 1

        result = client.get_fbo_postings(
            since="2026-08-12",
            to="2026-09-11",
            limit=3,
        )

        self.assertTrue(result["error"])
        self.assertEqual(result["code"], "OZON_FBO_POSTINGS_CURSOR_INVALID")
        self.assertTrue(result["read_only"])
        self.assertFalse(result["executed"])


if __name__ == "__main__":
    unittest.main()
