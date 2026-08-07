import logging


logging.basicConfig(
    filename="assistant.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


def get_logger():
    return logging.getLogger("ozon_assistant")
