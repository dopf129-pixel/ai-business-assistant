import csv
import io
from datetime import date
from math import isfinite


class SellerCostTableService:
    """Export/import a seller-cost table using a spreadsheet-friendly CSV format."""

    INITIAL_HISTORY_DATE = date.min
    HEADER = ("Артикул", "Ozon SKU", "Себестоимость, ₽")

    def __init__(self, product_service, cost_service):
        self.product_service = product_service
        self.cost_service = cost_service

    def export_csv(self):
        products = self._products()
        if isinstance(products, dict):
            return products
        current = self._current_cost_values()
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(self.HEADER)
        for offer_id, sku, _product_id in products:
            writer.writerow((offer_id or sku, sku, self._format_cost(current.get(sku))))
        return {
            "error": False,
            "message": "Заполните колонку «Себестоимость, ₽» и отправьте таблицу обратно боту.",
            "filename": "sebestoymost.csv",
            "mime_type": "text/csv",
            "file_content": "\ufeff" + stream.getvalue(),
            "rows": len(products),
            "read_only_ozon": True,
        }

    def import_csv(self, content):
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
            if len(row) < 3:
                errors.append(f"строка {line_number}: не хватает колонок")
                continue
            offer_id, sku, raw_cost = (str(row[0]).strip(), str(row[1]).strip(), str(row[2]).strip())
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
            parsed.append((sku, identity[0], identity[1], cost, sku in existing))
        if errors:
            return self._error("SELLER_COST_TABLE_VALIDATION_FAILED", "Таблица не импортирована:\n" + "\n".join(errors[:10]))
        if not parsed:
            return self._error("SELLER_COST_TABLE_EMPTY", "В таблице нет заполненной себестоимости.")

        # Fail closed before writes: all rows above are validated first. Existing
        # costs are intentionally rejected here because changing them requires an
        # effective date; the guided flow handles that separately.
        changing = [sku for sku, _offer, _pid, _cost, exists in parsed if exists]
        if changing:
            return self._error(
                "SELLER_COST_TABLE_EXISTING_COST_REQUIRES_DATE",
                "В таблице есть товары с уже заданной себестоимостью. Массовая загрузка сейчас предназначена для первичного заполнения истории; изменения существующей цены задайте через карточку товара.",
            )

        recorder = getattr(self.cost_service, "record_cost_switch", None)
        if not callable(recorder):
            return self._error("SELLER_COST_SWITCH_RECORDER_UNAVAILABLE", "Хранилище себестоимости недоступно.")
        saved = []
        for sku, offer_id, product_id, cost, _exists in parsed:
            result = recorder(
                product_id=product_id,
                sku=sku,
                offer_id=offer_id,
                cost_price=cost,
                effective_from=self.INITIAL_HISTORY_DATE.isoformat(),
                source="SELLER_CONFIRMED_INITIAL_HISTORY_TABLE",
            )
            if not isinstance(result, dict) or result.get("error") is not False:
                return self._error("SELLER_COST_TABLE_IMPORT_FAILED", f"Не удалось сохранить SKU {sku}. Проверьте таблицу и попробуйте снова.")
            saved.append(sku)
        return {
            "error": False,
            "message": f"✅ Себестоимость загружена для {len(saved)} товаров. Первые значения применены ко всей доступной истории продаж.",
            "imported": len(saved),
            "historical_default": True,
            "seller_confirmed": True,
            "read_only_ozon": True,
        }

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
