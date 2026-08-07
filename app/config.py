import os

from dotenv import load_dotenv


load_dotenv()


PROJECT_NAME = os.getenv(
    "PROJECT_NAME",
    "Ozon AI Assistant"
)

VERSION = os.getenv(
    "VERSION",
    "0.0.1"
)

OZON_CLIENT_ID = os.getenv(
    "OZON_CLIENT_ID"
)

OZON_API_KEY = os.getenv(
    "OZON_API_KEY"
)


# Модель работы магазина:
#
# FBO     - только FBO
# HYBRID  - FBO + FBS
# FBS     - только FBS

SELLING_MODEL = os.getenv(
    "SELLING_MODEL",
    "FBO"
).upper()


# Налоговый режим:
#
# USN_INCOME
# USN_INCOME_MINUS_EXPENSES
# NONE

TAX_MODE = os.getenv(
    "TAX_MODE",
    "NONE"
).upper()


def get_float_env(
    name,
    default
):

    try:
        return float(
            os.getenv(
                name,
                default
            )
        )

    except (
        TypeError,
        ValueError
    ):

        return float(
            default
        )


TAX_RATE = get_float_env(
    "TAX_RATE",
    0
)

MINIMUM_TAX_RATE = get_float_env(
    "MINIMUM_TAX_RATE",
    1
)