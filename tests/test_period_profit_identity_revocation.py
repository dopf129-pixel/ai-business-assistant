import os
import sqlite3
import tempfile

from services.assistant_period_profit_runtime_service import (
    AssistantPeriodProfitRuntimeService,
)
from services.period_profit_identity_confirmation_runtime_service import (
    PeriodProfitIdentityConfirmationRuntimeService,
)
from services.seller_confirmed_product_identity_repository import (
    SellerConfirmedProductIdentityRepository,
)


OLD_SKU = "3398133813"
CURRENT_SKU = "989101156"


class _CostStorage:
    def __init__(self, path):
        self.path = path

    def get_connection(self):
        return sqlite3.connect(self.path)


def test_exact_mapping_revocation_is_audited_and_allows_safe_remapping():
    handle = tempfile.NamedTemporaryFile(delete=False)
    handle.close()
    try:
        repository = SellerConfirmedProductIdentityRepository(
            _CostStorage(handle.name)
        )
        repository.record_mapping(OLD_SKU, "product-1", CURRENT_SKU, "offer-1")

        mismatch = repository.revoke_mapping(OLD_SKU, "wrong-current")
        assert mismatch["code"] == "SELLER_PRODUCT_IDENTITY_REVOCATION_MISMATCH"
        assert repository.get_mapping(OLD_SKU)["mapping_confirmed"] is True

        revoked = repository.revoke_mapping(OLD_SKU, CURRENT_SKU)
        assert revoked["status"] == "SELLER_PRODUCT_IDENTITY_MAPPING_REVOKED"
        assert repository.get_mapping(OLD_SKU)["mapping_confirmed"] is False

        conn = sqlite3.connect(handle.name)
        audit = conn.execute(
            "SELECT finance_sku, current_sku, event, event_source "
            "FROM seller_confirmed_product_identity_mapping_audit"
        ).fetchall()
        conn.close()
        assert audit == [(
            OLD_SKU, CURRENT_SKU, "REVOKED", "SELLER_REVOKED_BOT_TEXT",
        )]

        remapped = repository.record_mapping(
            OLD_SKU, "product-2", "222222222", "offer-2"
        )
        assert remapped["error"] is False
        assert repository.get_mapping(OLD_SKU)["current_sku"] == "222222222"
    finally:
        os.unlink(handle.name)


def test_active_report_mappings_are_loaded_in_one_batch():
    handle = tempfile.NamedTemporaryFile(delete=False)
    handle.close()
    try:
        repository = SellerConfirmedProductIdentityRepository(
            _CostStorage(handle.name)
        )
        repository.record_mapping(OLD_SKU, "product-1", CURRENT_SKU, "offer-1")

        mappings = repository.get_mappings([OLD_SKU, "missing", OLD_SKU])

        assert list(mappings) == [OLD_SKU]
        assert mappings[OLD_SKU]["current_sku"] == CURRENT_SKU
        assert mappings[OLD_SKU]["mapping_confirmed"] is True
    finally:
        os.unlink(handle.name)


def test_telegram_text_revokes_only_the_exact_active_pair():
    class Repository:
        def __init__(self):
            self.calls = []

        def get_mapping(self, finance_sku):
            if finance_sku != OLD_SKU:
                return {"error": False, "mapping_confirmed": False}
            return {
                "error": False,
                "mapping_confirmed": True,
                "current_sku": CURRENT_SKU,
            }

        def revoke_mapping(self, **kwargs):
            self.calls.append(kwargs)
            return {"error": False, "status": "REVOKED"}

    repository = Repository()
    runtime = PeriodProfitIdentityConfirmationRuntimeService(
        object(), repository=repository
    )
    result = runtime.handle_text(
        f"Отменить связь SKU {OLD_SKU} и SKU {CURRENT_SKU}"
    )

    assert result["code"] == "PERIOD_PROFIT_IDENTITY_REVOCATION_RECORDED"
    assert "недействительными" in result["message"]
    assert repository.calls == [{
        "finance_sku": OLD_SKU,
        "current_sku": CURRENT_SKU,
        "source": "SELLER_REVOKED_BOT_TEXT",
    }]


def test_missing_exact_pair_fails_closed_without_revocation():
    class Repository:
        def get_mapping(self, _finance_sku):
            return {"error": False, "mapping_confirmed": False}

        def revoke_mapping(self, **_kwargs):
            raise AssertionError("missing pair must not be mutated")

    runtime = PeriodProfitIdentityConfirmationRuntimeService(
        object(), repository=Repository()
    )
    result = runtime.handle_text(
        f"Отменить связь SKU {OLD_SKU} и SKU {CURRENT_SKU}"
    )

    assert result["code"] == "PERIOD_PROFIT_IDENTITY_REVOCATION_NOT_FOUND"
    assert result["executed"] is False


def test_assistant_routes_revocation_without_running_profit_query():
    class NeverQuery:
        def query(self, **_kwargs):
            raise AssertionError("profit query must not run")

    class IdentityRuntime:
        def handle_text(self, _text):
            return {"error": False, "code": "IDENTITY_REVOKED"}

    runtime = AssistantPeriodProfitRuntimeService(
        NeverQuery(), identity_confirmation_runtime_service=IdentityRuntime()
    )
    result = runtime.handle_text(
        f"Отменить связь SKU {OLD_SKU} и SKU {CURRENT_SKU}"
    )

    assert result == {"error": False, "code": "IDENTITY_REVOKED"}
