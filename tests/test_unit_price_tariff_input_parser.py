import pytest

from services.unit_price_tariff_input_parser import UnitPriceTariffInputParser


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("100 ₽ = 14%", [(10000, 10000, "14")]),
        ("1 234,50 = 12,5", [(123450, 123450, "12.5")]),
        (
            "0,01–99,99 ₽ = 10%\n100–199.99 ₽ = 11.75%",
            [(1, 9999, "10"), (10000, 19999, "11.75")],
        ),
        ("от 100 до 200 = 0%", [(10000, 20000, "0")]),
    ],
)
def test_parser_accepts_price_points_and_non_overlapping_inclusive_ranges(value, expected):
    parsed = UnitPriceTariffInputParser.parse(value, default_date="2026-10-27")
    assert parsed["error"] is False
    assert parsed["effective_from"] == "2026-10-27"
    assert [
        (item["price_from_cents"], item["price_to_cents"], item["commission_rate"])
        for item in parsed["bands"]
    ] == expected


def test_parser_accepts_explicit_effective_date_and_semicolon_separators():
    parsed = UnitPriceTariffInputParser.parse(
        "Действует с: 2026-09-01; 90=13%; 100-199,99=14%",
        default_date="2026-10-27",
    )
    assert parsed["error"] is False
    assert parsed["effective_from"] == "2026-09-01"
    assert len(parsed["bands"]) == 2


@pytest.mark.parametrize(
    "value",
    [
        "100-100,01=10%\n100,01-200=11%",  # adjacent inclusive bands overlap
        "200-100=10%",
        "0=101%",
        "100=NaN%",
        "100=Infinity%",
        "100=10.1234567890123%",
        "100.001=10%",
        "Действует с: 2026-02-30\n100=10%",
        "произвольный текст",
        "",
    ],
)
def test_parser_rejects_malformed_or_unsafe_values(value):
    assert UnitPriceTariffInputParser.parse(value, default_date="2026-10-27")["error"] is True


def test_parser_enforces_band_count_and_message_length_limits():
    bands = "\n".join(f"{i * 2}=10%" for i in range(1, 22))
    assert UnitPriceTariffInputParser.parse(bands, default_date="2026-10-27")["code"] == "TARIFF_BAND_COUNT_LIMIT"
    assert UnitPriceTariffInputParser.parse("x" * 4097, default_date="2026-10-27")["code"] == "TARIFF_INPUT_EMPTY_OR_TOO_LONG"
