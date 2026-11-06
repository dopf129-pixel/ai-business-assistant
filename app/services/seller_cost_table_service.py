import csv
import hashlib
import io
import json
import re
from datetime import date, datetime
from math import isfinite


class SellerCostTableService:
    """Export/import a seller-cost table using a spreadsheet-friendly CSV format."""

    INITIAL_HISTORY_DATE = date.min
    HEADER = ("Артикул", "Ozon SKU", "Себестоимость, ₽", "Действует с (ГГГГ-ММ-ДД)")
    MAX_UPLOAD_BYTES = 1_000_000
    MAX_ROWS = 1_000
    MAX_CELL_CHARS = 4_096
    FORMULA_PREFIXES = "=+-@"
    IMPORT_REFERENCE = re.compile(r"^seller-cost-file-[0-9a-f]{20}$")
    IMPORT_REVISION = re.compile(r"^seller-cost-rev-[0-9a-f]{24}$")

    def __init__(
        self, product_service, cost_service, date_provider=None,
        fifo_cost_repository=None,
    ):
        self.product_service = product_service
        self.cost_service = cost_service
        self.date_provider = date_provider or date.today
        self.fifo_cost_repository = fifo_cost_repository

    def export_csv(self):
        products = self._products()
        if isinstance(products, dict):
            return products
        current = self._current_cost_values()
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(self.HEADER)
        for offer_id, sku, _product_id in products:
            writer.writerow((
                self._spreadsheet_safe(offer_id or sku),
                self._spreadsheet_safe(sku),
                self._format_cost(current.get(sku)),
                "",
            ))
        return {
            "error": False,
            "message": "Заполните колонки «Себестоимость, ₽» и «Действует с». Для новых значений бот предложит сегодняшнюю дату; сохранение будет только после подтверждения.",
            "filename": "sebestoymost.csv",
            "mime_type": "text/csv",
            "document_kind": "seller_cost_import_template",
            "file_content": "\ufeff" + stream.getvalue(),
            "rows": len(products),
            "read_only_ozon": True,
        }

    def export_history_csv(self):
        """Export read-only legacy cost history; this file is not an import template."""
        getter = getattr(self.cost_service, "get_cost_history_snapshot", None)
        try:
            snapshot = getter() if callable(getter) else None
        except Exception:
            snapshot = None
        if not isinstance(snapshot, dict) or snapshot.get("error") is not False:
            return self._error(
                "SELLER_COST_HISTORY_EXPORT_UNAVAILABLE",
                "Не удалось получить историю себестоимости. Данные не изменены.",
            )
        records = snapshot.get("records")
        revision = snapshot.get("revision")
        if (
            not isinstance(records, list) or len(records) > 10_000
            or not isinstance(revision, str)
            or not re.fullmatch(r"legacy-cost-[0-9a-f]{24}", revision)
        ):
            return self._error(
                "SELLER_COST_HISTORY_EXPORT_INVALID",
                "История себестоимости имеет неподдерживаемый формат.",
            )
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, delimiter=";")
        writer.writerow((
            "Режим", "Артикул", "Ozon SKU", "Себестоимость, ₽",
            "Действует с", "Действует по", "Источник", "Ссылка импорта",
            "Версия при импорте", "Ревизия истории",
        ))
        for row in records:
            if not isinstance(row, dict):
                return self._error(
                    "SELLER_COST_HISTORY_EXPORT_INVALID",
                    "История себестоимости имеет неподдерживаемый формат.",
                )
            cost = self._cost(row.get("cost_price"))
            sku = self._text(row.get("sku"))
            if cost is None or not sku:
                return self._error(
                    "SELLER_COST_HISTORY_EXPORT_INVALID",
                    "В истории найдена неполная запись; файл не сформирован.",
                )
            source, source_reference, import_revision = self._parse_import_source(
                row.get("source"),
            )
            writer.writerow((
                row.get("record_type") if row.get("record_type") in {
                    "product_cost_history", "product_cost_switch_history",
                } else "UNKNOWN",
                self._spreadsheet_safe(row.get("offer_id") or sku),
                self._spreadsheet_safe(sku),
                self._format_cost(cost),
                self._text(row.get("effective_from")),
                self._text(row.get("effective_through")),
                self._spreadsheet_safe(source),
                source_reference or "",
                import_revision or "",
                revision,
            ))
        content = "\ufeff" + stream.getvalue()
        if len(content.encode("utf-8")) > self.MAX_UPLOAD_BYTES:
            return self._error(
                "SELLER_COST_HISTORY_EXPORT_TOO_LARGE",
                "История слишком большая для одной выгрузки. Обратитесь к администратору проекта.",
            )
        return {
            "error": False,
            "message": "История выгружена для просмотра. Файл содержит даты, источник и ревизию; он не является шаблоном импорта.",
            "filename": "seller-cost-history.csv",
            "mime_type": "text/csv",
            "document_kind": "analytics_export",
            "file_content": content,
            "rows": len(records),
            "revision": revision,
            "cost_mode": "LEGACY_DATED",
            "read_only_ozon": True,
        }

    def import_csv(self, content, *, store_id=None):
        """Validate and preview a CSV without writing cost data."""
        raw = self._content_bytes(content)
        if raw is None:
            return self._error("SELLER_COST_TABLE_ENCODING_INVALID", "Не удалось прочитать таблицу. Сохраните её как CSV UTF-8.")
        if len(raw) > self.MAX_UPLOAD_BYTES:
            return self._error(
                "SELLER_COST_TABLE_TOO_LARGE",
                f"Размер таблицы превышает {self.MAX_UPLOAD_BYTES // 1000} КБ. Разделите файл на несколько таблиц.",
            )
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = None
        if text is None:
            return self._error("SELLER_COST_TABLE_ENCODING_INVALID", "Не удалось прочитать таблицу. Сохраните её как CSV UTF-8.")
        try:
            rows = []
            for row in csv.reader(io.StringIO(text), delimiter=";"):
                if len(rows) >= self.MAX_ROWS + 1:
                    return self._error(
                        "SELLER_COST_TABLE_TOO_MANY_ROWS",
                        f"В таблице больше {self.MAX_ROWS} строк данных. Разделите файл на несколько таблиц.",
                    )
                if any(len(str(cell)) > self.MAX_CELL_CHARS for cell in row):
                    return self._error(
                        "SELLER_COST_TABLE_CELL_TOO_LARGE",
                        "В таблице найдена слишком длинная ячейка.",
                    )
                rows.append(row)
        except Exception:
            return self._error("SELLER_COST_TABLE_INVALID", "Не удалось разобрать таблицу. Используйте файл, который выдал бот.")
        if not rows:
            return self._error("SELLER_COST_TABLE_HEADER_INVALID", "Колонки таблицы изменены. Скачайте новый шаблон из бота.")
        header = tuple(cell.strip() for cell in rows[0])
        if header != self.HEADER:
            if "Режим" in header and any(
                str(cell).strip().upper() == "FIFO"
                for row in rows[1:3] for cell in row[:1]
            ):
                return self._error(
                    "SELLER_COST_TABLE_FIFO_MODE_CONFLICT",
                    "Это выгрузка истории FIFO только для просмотра. FIFO нельзя импортировать через legacy-таблицу; используйте подтверждённый сценарий FIFO.",
                )
            return self._error("SELLER_COST_TABLE_HEADER_INVALID", "Колонки таблицы изменены. Скачайте новый шаблон из бота.")

        products = self._products()
        if isinstance(products, dict):
            return products
        by_sku = {sku: (offer_id, product_id) for offer_id, sku, product_id in products}
        existing = set(self._current_cost_values())
        history_skus = self._existing_history_skus(products)
        if history_skus is None:
            return self._error(
                "SELLER_COST_TABLE_HISTORY_UNAVAILABLE",
                "Не удалось проверить, задана ли себестоимость раньше. Импорт не выполнен.",
            )
        existing.update(history_skus)
        history_revision = self._cost_history_revision()
        source_revision = self._source_revision(products, history_revision)
        if source_revision is None:
            return self._error(
                "SELLER_COST_TABLE_REVISION_UNAVAILABLE",
                "Не удалось зафиксировать версию истории себестоимости. Повторите импорт позже.",
            )
        if self.fifo_cost_repository is not None and not self._text(store_id):
            return self._error(
                "SELLER_COST_TABLE_STORE_REQUIRED",
                "Не удалось определить активный магазин. Выберите магазин и загрузите таблицу заново.",
            )
        parsed, errors = [], []
        seen = set()
        for line_number, row in enumerate(rows[1:], start=2):
            if not row or not any(str(cell).strip() for cell in row):
                continue
            if len(row) != len(self.HEADER):
                errors.append(f"строка {line_number}: должно быть ровно {len(self.HEADER)} колонки")
                continue
            offer_id, sku, raw_cost, raw_effective = (
                str(row[index]).strip() if len(row) > index else ""
                for index in range(4)
            )
            offer_id = self._unprotect_identifier(offer_id)
            sku = self._unprotect_identifier(sku)
            if not raw_cost:
                continue
            identity = by_sku.get(sku)
            if identity is None or (offer_id and identity[0] and offer_id != identity[0]):
                errors.append(f"строка {line_number}: товар не найден в активном магазине")
                continue
            mode_error = self._fifo_mode_conflict(
                store_id=store_id, sku=sku, product_id=identity[1], offer_id=identity[0],
            )
            if mode_error is not None:
                return mode_error
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
            row_identity = (sku, effective_from.isoformat())
            if row_identity in seen:
                errors.append(
                    f"строка {line_number}: для SKU {sku} повторяется дата действия"
                )
                continue
            seen.add(row_identity)
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
        rows_by_sku = {}
        for row in parsed:
            rows_by_sku.setdefault(row["sku"], []).append(row)
        for sku, sku_rows in rows_by_sku.items():
            if len(sku_rows) > 1 and any(
                row["date_was_provided"] is not True for row in sku_rows
            ):
                errors.append(
                    f"SKU {sku}: при нескольких ставках укажите дату в каждой строке"
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
            "all_history_allowed": (
                bool(parsed) and all(row["initial"] for row in parsed)
                and len(parsed) == len(rows_by_sku)
            ),
            "history_revision": history_revision,
            "source_reference": "seller-cost-file-" + hashlib.sha256(raw).hexdigest()[:20],
            "source_revision": source_revision,
            "cost_mode": "LEGACY_DATED",
            "read_only_ozon": True,
        }

    def commit_import(
        self, parsed, whole_history=False, *, expected_source_revision=None,
        expected_history_revision=None, source_reference=None,
        source_revision=None, store_id=None,
    ):
        if not isinstance(parsed, list) or not parsed:
            return self._error("SELLER_COST_TABLE_EMPTY", "В таблице нет заполненной себестоимости.")
        if whole_history and not all(row.get("initial") is True for row in parsed):
            return self._error(
                "SELLER_COST_TABLE_WHOLE_HISTORY_NOT_ALLOWED",
                "Применить всю историю можно только для товаров без ранее заданной себестоимости.",
            )
        products = self._products()
        if isinstance(products, dict):
            return products
        current_history_revision = self._cost_history_revision()
        current_revision = self._source_revision(products, current_history_revision)
        if (
            expected_source_revision is not None
            and current_revision != expected_source_revision
        ):
            return self._error(
                "SELLER_COST_TABLE_PREVIEW_STALE",
                "История себестоимости изменилась после предварительного просмотра. Импорт не выполнен; загрузите таблицу заново.",
            )
        if self.fifo_cost_repository is not None:
            if not self._text(store_id):
                return self._error("SELLER_COST_TABLE_STORE_REQUIRED", "Не удалось определить активный магазин. Импорт не выполнен.")
            by_sku = {sku: (offer_id, product_id) for offer_id, sku, product_id in products}
            for row in parsed:
                identity = by_sku.get(self._text(row.get("sku")))
                if identity is None:
                    return self._error("SELLER_COST_TABLE_PREVIEW_STALE", "Каталог изменился после предварительного просмотра. Загрузите таблицу заново.")
                conflict = self._fifo_mode_conflict(
                    store_id=store_id, sku=row.get("sku"),
                    product_id=identity[1], offer_id=identity[0],
                )
                if conflict is not None:
                    return conflict
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
        if source_reference is not None or source_revision is not None:
            if (
                not isinstance(source_reference, str)
                or not self.IMPORT_REFERENCE.fullmatch(source_reference)
                or not isinstance(source_revision, str)
                or not self.IMPORT_REVISION.fullmatch(source_revision)
            ):
                return self._error(
                    "SELLER_COST_TABLE_SOURCE_REFERENCE_INVALID",
                    "Ссылка или ревизия импорта не прошли проверку. Данные не изменены.",
                )
            source += f"|ref={source_reference}|revision={source_revision}"
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
        if expected_history_revision is not None:
            result = recorder(
                switches, expected_revision=expected_history_revision,
            )
        else:
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
            "cost_mode": "LEGACY_DATED",
            "source_reference": source_reference,
            "source_revision": source_revision,
            "history_revision": expected_history_revision,
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
        seen_skus = set()
        for row in rows:
            if not isinstance(row, (tuple, list)) or len(row) < 3:
                return self._error("SELLER_COST_PRODUCT_CATALOG_INVALID", "Каталог товаров повреждён.")
            product_id, offer_id, sku = (self._text(row[0]), self._text(row[1]), self._text(row[2]))
            if not product_id or not sku:
                return self._error("SELLER_COST_PRODUCT_CATALOG_INVALID", "Каталог товаров повреждён.")
            if sku in seen_skus:
                return self._error(
                    "SELLER_COST_PRODUCT_CATALOG_AMBIGUOUS",
                    "В каталоге найден повторяющийся Ozon SKU. Уточните каталог перед импортом.",
                )
            seen_skus.add(sku)
            products.append((offer_id or sku, sku, product_id))
        return sorted(products) if products else self._error("SELLER_COST_PRODUCT_CATALOG_EMPTY", "В активном магазине не найдены товары.")

    def _existing_history_skus(self, products):
        getter = getattr(self.cost_service, "get_seller_cost_identities", None)
        if not callable(getter):
            return set()
        try:
            result = getter()
        except Exception:
            return None
        if not isinstance(result, dict) or result.get("error") is not False:
            return None
        by_product = {product_id: sku for _offer, sku, product_id in products}
        existing = set()
        for row in result.get("records", []):
            if not isinstance(row, dict):
                continue
            sku = self._text(row.get("sku"))
            if sku in {item[1] for item in products}:
                existing.add(sku)
                continue
            product_sku = by_product.get(self._text(row.get("product_id")))
            if product_sku:
                existing.add(product_sku)
        return existing

    def _cost_history_revision(self):
        getter = getattr(self.cost_service, "get_cost_history_snapshot", None)
        if callable(getter):
            try:
                result = getter()
            except Exception:
                return None
            if (
                not isinstance(result, dict) or result.get("error") is not False
                or not isinstance(result.get("revision"), str)
            ):
                return None
            return result["revision"]
        try:
            costs = self.cost_service.get_all_costs()
        except Exception:
            costs = None
        if not isinstance(costs, list):
            return None
        return "legacy-cost-" + hashlib.sha256(
            json.dumps(
                costs, ensure_ascii=False, sort_keys=True, default=str,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:24]

    @staticmethod
    def _source_revision(products, cost_revision):
        if not isinstance(cost_revision, str) or not cost_revision:
            return None
        material = json.dumps(
            {"products": products, "cost_revision": cost_revision},
            ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"),
        ).encode("utf-8")
        return "seller-cost-rev-" + hashlib.sha256(material).hexdigest()[:24]

    def _fifo_mode_conflict(self, *, store_id, sku, product_id, offer_id):
        repository = self.fifo_cost_repository
        if repository is None:
            return None
        try:
            mode = repository.read_cost_mode_status(
                store_id=store_id, product_id=product_id,
                offer_id=offer_id, sku=sku,
            )
        except Exception:
            mode = None
        if not isinstance(mode, dict) or mode.get("error") is not False:
            return self._error(
                "SELLER_COST_TABLE_COST_MODE_UNAVAILABLE",
                "Не удалось подтвердить режим учёта товара. Импорт не выполнен; повторите позже.",
            )
        if mode.get("active") is True:
            return self._error(
                "SELLER_COST_TABLE_FIFO_MODE_CONFLICT",
                f"SKU {sku}: включён FIFO. Таблица датированной себестоимости не изменяет FIFO-историю. Используйте подтверждённый сценарий FIFO; пакетного импорта FIFO-партий нет.",
            )
        if mode.get("active") is not False:
            return self._error(
                "SELLER_COST_TABLE_COST_MODE_UNAVAILABLE",
                "Режим учёта товара не определён. Импорт не выполнен.",
            )
        return None

    @classmethod
    def _spreadsheet_safe(cls, value):
        text = cls._text(value)
        probe = text.lstrip(" \t\r\n")
        if probe and probe[0] in cls.FORMULA_PREFIXES:
            return "'" + text
        return text

    @classmethod
    def _unprotect_identifier(cls, value):
        text = cls._text(value)
        if len(text) > 1 and text[0] == "'" and text[1] in cls.FORMULA_PREFIXES:
            return text[1:]
        return text

    @classmethod
    def _parse_import_source(cls, value):
        text = cls._text(value)
        parts = text.split("|")
        if len(parts) == 3 and parts[1].startswith("ref=") and parts[2].startswith("revision="):
            reference = parts[1][4:]
            revision = parts[2][9:]
            if cls.IMPORT_REFERENCE.fullmatch(reference) and cls.IMPORT_REVISION.fullmatch(revision):
                return parts[0], reference, revision
        return text, None, None

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
    def _content_bytes(content):
        if isinstance(content, bytes):
            return content
        if isinstance(content, str):
            try:
                return content.encode("utf-8")
            except UnicodeEncodeError:
                return None
        return None

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
