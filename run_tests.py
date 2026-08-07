import unittest
import sys


def main():

    print("=" * 40)
    print("Ozon AI Assistant")
    print("Запуск тестов")
    print("=" * 40)
    print()

    loader = unittest.TestLoader()

    suite = loader.discover(
        ".",
        pattern="test_*.py"
    )

    runner = unittest.TextTestRunner(
        verbosity=2
    )

    result = runner.run(suite)

    print()

    if result.wasSuccessful():

        print("✅ Все тесты успешно пройдены.")
        sys.exit(0)

    else:

        print("❌ Есть ошибки в тестах.")
        sys.exit(1)


if __name__ == "__main__":
    main()