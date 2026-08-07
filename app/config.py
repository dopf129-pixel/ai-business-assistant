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
# FBO     - только FBO
# HYBRID  - FBO + FBS
# FBS     - только FBS

SELLING_MODEL = os.getenv(
    "SELLING_MODEL",
    "FBO"
).upper()