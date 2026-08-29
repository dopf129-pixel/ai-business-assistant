import os

from services.period_profit_mapping_registry_service import (
    PeriodProfitMappingRegistryService,
)


DEFAULT_MAPPING_REGISTRY_PATH = "data/period_profit_mapping_registry.json"


def create_period_profit_mapping_registry():
    path = os.getenv(
        "PERIOD_PROFIT_MAPPING_REGISTRY_PATH",
        DEFAULT_MAPPING_REGISTRY_PATH,
    )
    return PeriodProfitMappingRegistryService(path)


def load_active_period_profit_mappings(registry=None):
    service = registry or create_period_profit_mapping_registry()
    return {
        "RETURN": service.load_active("RETURN"),
        "ADVERTISING": service.load_active("ADVERTISING"),
        "STORAGE": service.load_active("STORAGE"),
    }
