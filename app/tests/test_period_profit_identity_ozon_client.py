from unittest.mock import patch

from api.ozon_client import OzonClient
from api.period_profit_identity_ozon_client import PeriodProfitIdentityOzonClient


def test_identity_client_clamps_fbo_network_budget():
    client = PeriodProfitIdentityOzonClient()

    with patch.object(
        OzonClient,
        "_post",
        return_value={"postings": [], "cursor": ""},
    ) as parent_post:
        result = client.get_fbo_postings(
            "2026-01-01T00:00:00Z",
            "2026-01-02T23:59:59Z",
            limit=1000,
            offset=0,
            direction="ASC",
            status="",
        )

    assert result.get("error") is False
    assert parent_post.call_count == 1
    _, kwargs = parent_post.call_args
    assert kwargs["timeout"] == 6
    assert kwargs["max_attempts"] == 1


def test_identity_client_does_not_widen_smaller_caller_budget():
    client = PeriodProfitIdentityOzonClient()

    with patch.object(OzonClient, "_post", return_value={"error": False}) as parent_post:
        client._post("/read-only", {}, timeout=2, max_attempts=1)

    _, kwargs = parent_post.call_args
    assert kwargs["timeout"] == 2
    assert kwargs["max_attempts"] == 1
