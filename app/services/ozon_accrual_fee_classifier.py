"""Shared label classifier for Ozon accrual fee categories.

Keep category aliases in one place so reports and unit-economics evidence use
the same interpretation of Ozon's accrual type dictionary.
"""

from __future__ import annotations

import re


FEE_LABEL_MATCHERS = {
    "last_mile": (
        "последняя миля",
        "последней мили",
        "доставка до места выдачи",
        "доставка к месту выдачи",
        "выдача товара",
        "last mile",
        "last-mile",
        "lastmile",
    ),
    "cross_docking": (
        "кросс-док",
        "кросс док",
        "cross-dock",
        "cross dock",
        "crossdock",
    ),
    "paid_storage": (
        "платное хран",
        "плата за хранение",
        "платное размещение",
        "плата за размещение",
        "стоимость размещения",
        "размещение на складе",
        "вынужденное размещение",
        "paid storage",
        "paidstorage",
        "storage fee",
    ),
    "reverse_logistics": (
        "обратная логист",
        "возвратная логист",
        "логистика возврата",
        "return flow logistic",
        "returnflowlogistic",
        "reverse logistics",
    ),
}


def matches_fee_category(labels, category, matchers):
    """Apply the established label matching semantics to type labels."""

    for label in labels:
        normalized = "" if label is None else str(label).strip().casefold()
        if any(matcher in normalized for matcher in matchers):
            return True
        if category == "paid_storage":
            # Ozon's type dictionary may use the short type name "Размещение".
            last_word = re.sub(r"[^a-zа-яё]+", " ", normalized).split()
            if last_word and last_word[-1].startswith(("размещ", "placement")):
                return True
    return False
