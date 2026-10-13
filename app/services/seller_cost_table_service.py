import csv
import io
from datetime import date, datetime
from math import isfinite


class SellerCostTableService:
    """Export/import a seller-cost table using a spreadsheet-friendly CSV format."""

    INITIAL_HISTORY_DATE = date.min
    HEADER = ("Артикул", "Ozon SKU", "Себестоимость, ₽", "Действует с (ГГГГ-ММ-ДД)")

    def __init__(self, product_service, cost_service, date_provider=None):
        self.product_service = product_service
        self.cost_service = cost_service
        self.date_provider = date_provider or date.today

    def export_csv(self):
        products = self._products()
        if isinstance(products, dict):
            return products
        current = self._current_cost_values()
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(self.HEADER)
        for offer_id, sku, _product_id in products:
            writer.writerow((offer_id or sku, sku, self._format_cost(current.get(sku)), ""))
        return {
            "error": False,
            "message": "Заполните колонки «Себестоимость, ₽» и «Действует с». Для новых значений бот предложит сегодняшнюю дату; сохранение будет только после подтверждения.",
            "filename": "sebestoymost.csv",
            "mime_type": "text/csv",
            "file_content": "\ufeff" + stream.getvalue(),
            "rows": len(products),
            "read_only_ozon": True,
        }

    def import_csv(self, content):
        """Validate and preview a CSV without writing cost data."""
        text = self._decode(content)
        if text is None:
            return self._error("SELLER_COST_TABLE_ENCODING_INVALID", "Не удалось прочитать таблицу. Сохраните её как CSV UTF-8.")
        try:
            rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff")), delimiter=";"))
        except Exception:
            return self._error("SELLER_COST_TABLE_INVALID", "Не удалось разобрать таблицу. Используйте файл, который выдал бот.")
        if not rows or tuple(cell.strip() for cell in rows[0]) != self.HEADER:
            return self._error("SELLER_COST_TABLE_HEADER_INVALID", "Колонки таблицы изменены. Скачайте новый шаблон из бота.")

        products = self._products()
        if isinstance(products, dict):
            return products
        by_sku = {sku: (offer_id, product_id) for offer_id, sku, product_id in products}
        existing = set(self._current_cost_values())
        parsed, errors = [], []
        seen = set()
        for line_number, row in enumerate(rows[1:], start=2):
            if not row or not any(str(cell).strip() for cell in row):
                continue
            if len(row) < 4:
                errors.append(f"строка {line_number}: не хватает колонок")
                continue
            offer_id, sku, raw_cost, raw_effective = (
                str(row[index]).strip() if len(row) > index else ""
                for index in range(4)
            )
            if not raw_cost:
                continue
            if sku in seen:
                errors.append(f"строка {line_number}: SKU {sku} повторяется")
                continue
            seen.add(sku)
            identity = by_sku.get(sku)
            if identity is None or (offer_id and identity[0] and offer_id != identity[0]):
                errors.append(f"строка {line_number}: товар не найден в активном магазине")
                continue
            cost = self._cost(raw_cost)
            if cost is None:
                errors.append(f"строка {line_number}: неверная себестоимость")
                continue
            effective_from = self._date(raw_effective) if raw_effective else None
            is_initial = sku not in existing
            if raw_effective and effective_from is None:
                errors.append(f"строка {line_number}: дата должна быть в формате ГГГГ-ММ-ДД")
                continue
            if not is_initial and effective_from is None:
                errors.append(f"строка {line_number}: для изменения существующей себестоимости укажите дату действия")
                continue
            if is_initial and effective_from is None:
                effective_from = self._today()
                if effective_from is None:
                    errors.append(f"строка {line_number}: не удалось определить предлагаемую дату")
                    continue
            parsed.append(
                {
                    "sku": sku,
                    "offer_id": identity[0],
                    "product_id": identity[1],
                    "cost_price": cost,
                    "initial": is_initial,
                    "effective_from": effective_from.isoformat(),
                    "date_was_provided": bool(raw_effective),
                }
            )
        if errors:
            return self._error("SELLER_COST_TABLE_VALIDATION_FAILED", "Таблица не импортирована:\n" + "\n".join(errors[:10]))
        if not parsed:
            return self._error("SELLER_COST_TABLE_EMPTY", "В таблице нет заполненной себестоимости.")

        return {
            "error": False,
            "status": "SELLER_COST_TABLE_CONFIRMATION_REQUIRED",
            "message": "Проверьте даты и подтвердите пакетное сохранение. До подтверждения таблица ничего не меняет.",
            "rows": parsed,
            "imported": len(parsed),
            "initial_count": sum(1 for row in parsed if row["initial"]),
            "existing_count": sum(1 for row in parsed if not row["initial"]),
            "all_history_allowed": bool(parsed) and all(row["initial"] for row in parsed),
            "read_only_ozon": True,
        }

    def commit_import(self, parsed, whole_history=False):
        if not isinstance(parsed, list) or not parsed:
            return self._error("SELLER_COST_TABLE_EMPTY", "В таблице нет заполненной себестоимости.")
        if whole_history and not all(row.get("initial") is True for row in parsed):
            return self._error(
                "SELLER_COST_TABLE_WHOLE_HISTORY_NOT_ALLOWED",
                "Применить всю историю можно только для товаров без ранее заданной себестоимости.",
            )
        recorder = getattr(self.cost_service, "record_cost_switches", None)
        if not callable(recorder):
            return self._error(
                "SELLER_COST_ATOMIC_IMPORT_UNAVAILABLE",
                "Пакетное сохранение недоступно: хранилище не поддерживает атомарную запись.",
            )
        source = (
            "SELLER_CONFIRMED_INITIAL_HISTORY_TABLE"
            if whole_history
            else "SELLER_CONFIRMED_COST_TABLE"
        )
        switches = [
            {
                "product_id": row["product_id"],
                "sku": row["sku"],
                "offer_id": row["offer_id"],
                "cost_price": row["cost_price"],
                "effective_from": (
                    self.INITIAL_HISTORY_DATE.isoformat()
                    if whole_history
                    else row["effective_from"]
                ),
                "source": source,
            }
            for row in parsed
        ]
        result = recorder(switches)
        if not isinstance(result, dict) or result.get("error") is not False:
            return self._error(
                "SELLER_COST_TABLE_IMPORT_FAILED",
                "Таблица не сохранена целиком. Проверьте даты и конфликтующие версии; частичного импорта нет.",
            )
        saved = len(parsed)
        effective_note = (
            "Первоначальные значения применены ко всей доступной истории по отдельному подтверждению."
            if whole_history
            else "Даты действия сохранены по строкам таблицы."
        )
        return {
            "error": False,
            "message": f"✅ Себестоимость сохранена для {saved} товаров. {effective_note}",
            "imported": saved,
            "inserted": int(result.get("inserted") or 0),
            "unchanged": int(result.get("unchanged") or 0),
            "historical_default": whole_history,
            "seller_confirmed": True,
            "read_only_ozon": True,
        }

    def _today(self):
        try:
            value = self.date_provider()
        except Exception:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return self._date(value)

    @staticmethod
    def _date(value):
        try:
            return date.fromisoformat(str(value).strip())
        except (TypeError, ValueError):
            return None

    def _products(self):
        try:
            rows = self.product_service.load_products()
        except Exception:
            return self._error("SELLER_COST_PRODUCT_CATALOG_UNAVAILABLE", "Не удалось загрузить каталог товаров.")
        if not isinstance(rows, list):
            return self._error("SELLER_COST_PRODUCT_CATALOG_INVALID", "Каталог товаров повреждён.")
        if not rows:
            refresher = getattr(self.product_service, "refresh_products_for_period_profit", None)
            try:
                refreshed = refresher() if callable(refresher) else None
                rows = self.product_service.load_products() if isinstance(refreshed, dict) and refreshed.get("error") is False else []
            except Exception:
                rows = []
        products = []
        for row in rows:
            if not isinstance(row, (tuple, list)) or len(row) < 3:
                return self._error("SELLER_COST_PRODUCT_CATALOG_INVALID", "Каталог товаров повреждён.")
            product_id, offer_id, sku = (self._text(row[0]), self._text(row[1]), self._text(row[2]))
            if not product_id or not sku:
                return self._error("SELLER_COST_PRODUCT_CATALOG_INVALID", "Каталог товаров повреждён.")
            products.append((offer_id or sku, sku, product_id))
        return sorted(products) if products else self._error("SELLER_COST_PRODUCT_CATALOG_EMPTY", "В активном магазине не найдены товары.")

    def _current_cost_values(self):
        getter = getattr(self.cost_service, "get_all_costs", None)
        try:
            rows = getter() if callable(getter) else []
        except Exception:
            rows = []
        result = {}
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict):
                sku, cost = self._text(row.get("sku")), self._cost(row.get("cost_price"))
            elif isinstance(row, (tuple, list)) and len(row) >= 4:
                sku, cost = self._text(row[1]), self._cost(row[3])
            else:
                continue
            if sku and cost is not None:
                result[sku] = cost
        return result

    @staticmethod
    def _decode(content):
        if isinstance(content, bytes):
            try:
                return content.decode("utf-8-sig")
            except UnicodeDecodeError:
                return None
        return str(content) if isinstance(content, str) else None

    @staticmethod
    def _text(value):
        return "" if value is None else str(value).strip()

    @staticmethod
    def _cost(value):
        if isinstance(value, bool):
            return None
        try:
            number = float(str(value).strip().replace(" ", "").replace(",", "."))
        except (TypeError, ValueError, OverflowError):
            return None
        return number if isfinite(number) and number >= 0 else None

    @staticmethod
    def _format_cost(value):
        if value is None:
            return ""
        return f"{value:.2f}".rstrip("0").rstrip(".")

    @staticmethod
    def _error(code, message):
        return {"error": True, "code": code, "message": message, "read_only_ozon": True}
