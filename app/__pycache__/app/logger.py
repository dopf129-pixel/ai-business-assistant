import logging


logging.basicConfig(
    filename="assistant.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8"
)


def get_logger():
    return logging.getLogger("ozon_assistant")