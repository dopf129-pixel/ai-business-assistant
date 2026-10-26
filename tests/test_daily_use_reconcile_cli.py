from datetime import date
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import daily_use_reconcile


class _SyntheticSheet:
    title = "Начисления"

    def reset_dimensions(self):
        return None

    def iter_rows(self, *, min_row, max_row=None, values_only=False):
        if min_row == 2:
            return iter([(
                "ID начисления", "Дата начисления", "Тип начисления", "SKU",
                "Сумма итого, руб.",
            )])
        return iter([
            ("synthetic-id", date(2026, 8, 1), "Корректировка", "synthetic-sku", -1.25),
            ("synthetic-id", date(2026, 8, 2), "Продажа", "synthetic-sku", 10.00),
        ])


class _SyntheticWorkbook:
    sheetnames = ["Начисления"]

    def __init__(self):
        self.sheet = _SyntheticSheet()

    def __getitem__(self, key):
        assert key == "Начисления"
        return self.sheet

    def close(self):
        return None


def test_reference_cli_uses_explicit_profile_and_emits_only_aggregate(monkeypatch, capsys):
    monkeypatch.setitem(
        sys.modules,
        "openpyxl",
        SimpleNamespace(load_workbook=lambda *args, **kwargs: _SyntheticWorkbook()),
    )
    monkeypatch.setattr(Path, "stat", lambda self, *args, **kwargs: SimpleNamespace(st_size=128))

    code = daily_use_reconcile.main([
        "reference", "--profile", "ozon_accruals_xlsx_v1", "--report", "synthetic.xlsx",
        "--period-from", "2026-08-01", "--period-to", "2026-08-31",
        "--source-period-from", "2026-08-01", "--source-period-to", "2026-08-31",
        "--scope-alias", "shop-a", "--confirm-full-period",
    ])
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert result["reference"]["metrics"]["net_accrual"]["value"] == "8.75"
    assert result["reference"]["coverage"]["rows_in_period"] == 2
    assert "synthetic-id" not in str(result)
    assert "synthetic-sku" not in str(result)


def test_reference_cli_rejects_unknown_profile_without_opening_workbook(capsys):
    code = daily_use_reconcile.main([
        "reference", "--profile", "unknown", "--report", "private.xlsx",
        "--period-from", "2026-08-01", "--period-to", "2026-08-31",
        "--source-period-from", "2026-08-01", "--source-period-to", "2026-08-31",
        "--scope-alias", "shop-a",
    ])
    result = json.loads(capsys.readouterr().out)

    assert code == 1
    assert result["code"] == "DAILY_USE_REPORT_PROFILE_UNSUPPORTED"
    assert "private.xlsx" not in str(result)
