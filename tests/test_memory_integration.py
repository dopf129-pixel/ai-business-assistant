import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core



def test_core_has_memory_service():


    core = create_telegram_core()


    assert (
        "memory_service"
        in core
    )