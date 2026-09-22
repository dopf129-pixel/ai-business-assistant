import os
import sqlite3
import sys
import tempfile


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

import period_profit_factory  # noqa: E402
from services.assistant_period_profit_runtime_service import (  # noqa: E402
    AssistantPeriodProfitRuntimeService,
)
from services.period_profit_identity_confirmation_runtime_service import (  # noqa: E402
    PeriodProfitIdentityConfirmationRuntimeService,
)
from services.period_profit_seller_confirmed_identity_scope_service import (  # noqa: E402
    PeriodProfitSellerConfirmedIdentityScopeService,
)
from services.seller_confirmed_product_identity_repository import (  # noqa: E402
    SellerConfirmedProductIdentityRepository,
)


OLD_SKU = "3398133813"
CURRENT_SKU = "3921245627"
CURRENT_PRODUCT_ID = "4108512640"
OFFER_ID = "hook-2"


class _FileCostService:
    def __init__(self, path):
        self.path = path

    def get_connection(self):
        return sqlite3.connect(self.path)


class _CurrentCostService:
    def get_all_costs(self):
        return [
            (CURRENT_PRODUCT_ID, CURRENT_SKU, OFFER_ID, 21.0, "RUB"),
        ]

    def get_historical_cost_evidence(self, *_args, **_kwargs):
        return {
            "error": False,
            "status": "PRODUCT_COST_HISTORY_MISSING",
            "historical_cost_confirmed": False,
        }


class _Summary:
    def __init__(self):
        self.cost_service = _CurrentCostService()
        self.tax_rate = 0.0


class _MappingRepository:
    def __init__(self, product_id=CURRENT_PRODUCT_ID, sku=CURRENT_SKU, offer_id=OFFER_ID):
        self.product_id = product_id
        self.sku = sku
        self.offer_id = offer_id

    def get_mapping(self, finance_sku):
        return {
            "error": False,
            "status": "SELLER_PRODUCT_IDENTITY_MAPPING_READY",
            "mapping_confirmed": True,
            "seller_confirmed": True,
            "finance_sku": finance_sku,
            "current_product_id": self.product_id,
            "current_sku": self.sku,
            "current_offer_id": self.offer_id,
        }


class _Recorder:
    def __init__(self):
        self.calls = []

    def record_mapping(self, **kwargs):
        self.calls.append(dict(kwargs))
        return {
            "error": False,
            "status": "SELLER_PRODUCT_IDENTITY_MAPPING_RECORDED",
        }


def test_repository_is_idempotent_and_rejects_conflicting_alias():
    handle = tempfile.NamedTemporaryFile(delete=False)
    handle.close()
    try:
        repository = SellerConfirmedProductIdentityRepository(
            _FileCostService(handle.name)
        )
        first = repository.record_mapping(
            OLD_SKU,
            CURRENT_PRODUCT_ID,
            CURRENT_SKU,
            OFFER_ID,
        )
        assert first["error"] is False
        assert first["status"] == "SELLER_PRODUCT_IDENTITY_MAPPING_RECORDED"

        same = repository.record_mapping(
            OLD_SKU,
            CURRENT_PRODUCT_ID,
            CURRENT_SKU,
            OFFER_ID,
        )
        assert same["error"] is False
        assert same["status"] == "SELLER_PRODUCT_IDENTITY_MAPPING_ALREADY_RECORDED"

        conflict = repository.record_mapping(
            OLD_SKU,
            "different-product",
            "different-sku",
            "different-offer",
        )
        assert conflict["error"] is True
        assert conflict["code"] == "SELLER_PRODUCT_IDENTITY_MAPPING_CONFLICT"

        loaded = repository.get_mapping(OLD_SKU)
        assert loaded["mapping_confirmed"] is True
        assert loaded["current_product_id"] == CURRENT_PRODUCT_ID
        assert loaded["current_sku"] == CURRENT_SKU
        assert loaded["current_offer_id"] == OFFER_ID
    finally:
        os.unlink(handle.name)


def test_repository_revokes_only_exact_mapping_and_preserves_audit():
    handle = tempfile.NamedTemporaryFile(delete=False)
    handle.close()
    try:
        repository = SellerConfirmedProductIdentityRepository(
            _FileCostService(handle.name)
        )
        assert repository.record_mapping(
            OLD_SKU, CURRENT_PRODUCT_ID, CURRENT_SKU, OFFER_ID
        )["error"] is False

        mismatch = repository.revoke_mapping(OLD_SKU, "wrong-current-sku")
        assert mismatch["error"] is True
        assert mismatch["code"] == "SELLER_PRODUCT_IDENTITY_REVOCATION_MISMATCH"
        assert repository.get_mapping(OLD_SKU)["mapping_confirmed"] is True

        revoked = repository.revoke_mapping(OLD_SKU, CURRENT_SKU)
        assert revoked["error"] is False
        assert revoked["status"] == "SELLER_PRODUCT_IDENTITY_MAPPING_REVOKED"
        assert repository.get_mapping(OLD_SKU)["mapping_confirmed"] is False

        conn = sqlite3.connect(handle.name)
        audit = conn.execute(
            "SELECT finance_sku, current_sku, current_offer_id, event, event_source "
            "FROM seller_confirmed_product_identity_mapping_audit"
        ).fetchall()
        conn.close()
        assert audit == [(
            OLD_SKU, CURRENT_SKU, OFFER_ID, "REVOKED", "SELLER_REVOKED_BOT_TEXT",
        )]

        replacement = repository.record_mapping(
            OLD_SKU, "new-product", "new-current-sku", "new-offer"
        )
        assert replacement["error"] is False
        assert repository.get_mapping(OLD_SKU)["current_sku"] == "new-current-sku"
    finally:
        os.unlink(handle.name)


def test_text_confirmation_requires_exactly_one_current_seller_identity():
    recorder = _Recorder()
    runtime = PeriodProfitIdentityConfirmationRuntimeService(
        _CurrentCostService(),
        repository=recorder,
    )

    result = runtime.handle_text(
        f"Подтверждаю: SKU {OLD_SKU} и SKU {CURRENT_SKU} — один товар"
    )

    assert result["error"] is False
    assert result["seller_confirmed"] is True
    assert result["read_only_ozon"] is True
    assert recorder.calls == [
        {
            "finance_sku": OLD_SKU,
            "current_product_id": CURRENT_PRODUCT_ID,
            "current_sku": CURRENT_SKU,
            "current_offer_id": OFFER_ID,
            "source": "SELLER_CONFIRMED_BOT_TEXT",
        }
    ]


def test_text_revocation_requires_and_removes_one_exact_active_pair():
    class Repository:
        def __init__(self):
            self.revocations = []

        def get_mapping(self, finance_sku):
            if finance_sku != OLD_SKU:
                return {"error": False, "mapping_confirmed": False}
            return {
                "error": False,
                "mapping_confirmed": True,
                "current_sku": CURRENT_SKU,
            }

        def revoke_mapping(self, **kwargs):
            self.revocations.append(kwargs)
            return {"error": False, "status": "REVOKED"}

    repository = Repository()
    runtime = PeriodProfitIdentityConfirmationRuntimeService(
        _CurrentCostService(), repository=repository
    )

    result = runtime.handle_text(
        f"Отменить связь SKU {OLD_SKU} и SKU {CURRENT_SKU}"
    )

    assert result["error"] is False
    assert result["code"] == "PERIOD_PROFIT_IDENTITY_REVOCATION_RECORDED"
    assert "недействительными" in result["message"]
    assert repository.revocations == [{
        "finance_sku": OLD_SKU,
        "current_sku": CURRENT_SKU,
        "source": "SELLER_REVOKED_BOT_TEXT",
    }]


def test_text_revocation_fails_closed_when_exact_pair_is_absent():
    class Repository:
        def get_mapping(self, _finance_sku):
            return {"error": False, "mapping_confirmed": False}

        def revoke_mapping(self, **_kwargs):
            raise AssertionError("missing mapping must not be revoked")

    runtime = PeriodProfitIdentityConfirmationRuntimeService(
        _CurrentCostService(), repository=Repository()
    )
    result = runtime.handle_text(
        f"Отменить связь SKU {OLD_SKU} и SKU {CURRENT_SKU}"
    )

    assert result["error"] is True
    assert result["code"] == "PERIOD_PROFIT_IDENTITY_REVOCATION_NOT_FOUND"


def test_scope_uses_seller_mapping_before_ozon_identity_fallbacks():
    service = PeriodProfitSellerConfirmedIdentityScopeService(
        _Summary(),
        finance_service=object(),
        sku_ozon_client=None,
        identity_mapping_repository=_MappingRepository(),
    )
    service._catalog_by_sku = {
        CURRENT_SKU: {
            "product_id": CURRENT_PRODUCT_ID,
            "sku": CURRENT_SKU,
            "offer_id": OFFER_ID,
        }
    }

    recovered = service._recover_missing_product(OLD_SKU, "2026-09-14")

    assert recovered is not None
    assert recovered["sku"] == OLD_SKU
    assert recovered["catalog_sku"] == CURRENT_SKU
    assert recovered["product_id"] == CURRENT_PRODUCT_ID
    assert recovered["offer_id"] == OFFER_ID
    assert recovered["seller_confirmed_identity_mapping"] is True
    assert recovered["historical_sku_identity_source"] == (
        "SELLER_CONFIRMED_PRODUCT_IDENTITY_MAPPING"
    )


def test_scope_fails_closed_when_confirmed_mapping_conflicts_with_catalog():
    service = PeriodProfitSellerConfirmedIdentityScopeService(
        _Summary(),
        finance_service=object(),
        sku_ozon_client=None,
        identity_mapping_repository=_MappingRepository(product_id="other-product"),
    )
    service._catalog_by_sku = {
        CURRENT_SKU: {
            "product_id": CURRENT_PRODUCT_ID,
            "sku": CURRENT_SKU,
            "offer_id": OFFER_ID,
        }
    }

    recovered = service._recover_missing_product(OLD_SKU, "2026-09-14")

    assert recovered is None
    assert (
        "PERIOD_PROFIT_FINANCE_SKU_IDENTITY_SELLER_MAPPING_PRODUCT_CONFLICT"
        in service._sku_recovery_diagnostic_codes
    )


def test_assistant_routes_identity_confirmation_without_profit_or_cost_words():
    class _NeverQuery:
        def query(self, **_kwargs):
            raise AssertionError("Period Profit query must not run for confirmation text")

    class _IdentityRuntime:
        def handle_text(self, text):
            assert OLD_SKU in text
            return {"error": False, "code": "IDENTITY_RECORDED"}

    runtime = AssistantPeriodProfitRuntimeService(
        _NeverQuery(),
        identity_confirmation_runtime_service=_IdentityRuntime(),
    )

    result = runtime.handle_text(
        f"SKU {OLD_SKU} и SKU {CURRENT_SKU} — один товар"
    )
    assert result == {"error": False, "code": "IDENTITY_RECORDED"}


def test_assistant_routes_identity_revocation_without_running_profit_query():
    class _NeverQuery:
        def query(self, **_kwargs):
            raise AssertionError("Period Profit query must not run for revocation text")

    class _IdentityRuntime:
        def handle_text(self, text):
            assert "Отменить связь" in text
            return {"error": False, "code": "IDENTITY_REVOKED"}

    runtime = AssistantPeriodProfitRuntimeService(
        _NeverQuery(), identity_confirmation_runtime_service=_IdentityRuntime()
    )
    result = runtime.handle_text(
        f"Отменить связь SKU {OLD_SKU} и SKU {CURRENT_SKU}"
    )

    assert result == {"error": False, "code": "IDENTITY_REVOKED"}


def test_production_factory_uses_seller_confirmed_identity_scope():
    assert period_profit_factory.PeriodProfitFinanceSkuScopeService is (
        PeriodProfitSellerConfirmedIdentityScopeService
    )
