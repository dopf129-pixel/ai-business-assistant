"""Safe, explicit contract for generated Telegram documents."""

import re


_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,126}$")

DOCUMENT_KINDS = {
    "seller_cost_import_template": {
        "mime_types": {"text/csv": ".csv"},
        "caption": "Заполните себестоимость и отправьте этот CSV-файл обратно боту.",
    },
    "analytics_export": {
        "mime_types": {
            "text/csv": ".csv",
            "application/json": ".json",
        },
        "caption": "Экспорт аналитики для просмотра. Этот файл нельзя загружать как таблицу себестоимости.",
    },
    "support_diagnostic": {
        "mime_types": {"application/json": ".json"},
        "caption": "Обезличенная диагностика для поддержки.",
    },
}


def prepare_telegram_document(result):
    """Validate a generated file and return the transport-safe fields."""
    if not isinstance(result, dict):
        return None
    kind = result.get("document_kind")
    spec = DOCUMENT_KINDS.get(kind)
    filename = result.get("filename")
    mime_type = result.get("mime_type")
    content = result.get("file_content")
    if (
        spec is None
        or not isinstance(filename, str)
        or not _FILENAME_RE.fullmatch(filename)
        or not isinstance(mime_type, str)
        or spec["mime_types"].get(mime_type) != _extension(filename)
    ):
        return None
    if isinstance(content, str):
        payload = content.encode("utf-8")
    elif isinstance(content, (bytes, bytearray, memoryview)):
        payload = bytes(content)
    else:
        return None
    return {
        "kind": kind,
        "filename": filename,
        "mime_type": mime_type,
        "payload": payload,
        "caption": spec["caption"],
    }


def _extension(filename):
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot >= 0 else ""
