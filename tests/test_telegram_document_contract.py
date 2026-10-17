from telegram_app_layer.telegram_document_contract import prepare_telegram_document


def test_legacy_cost_document_has_an_explicit_safe_contract():
    result = prepare_telegram_document({
        "document_kind": "seller_cost_import_template",
        "filename": "sebestoymost.csv",
        "mime_type": "text/csv",
        "file_content": "\ufeffАртикул;Ozon SKU\n",
    })

    assert result["payload"].startswith(b"\xef\xbb\xbf")
    assert result["caption"] == "Заполните себестоимость и отправьте этот CSV-файл обратно боту."


def test_analytics_document_is_explicitly_marked_as_not_a_cost_import():
    result = prepare_telegram_document({
        "document_kind": "analytics_export",
        "filename": "period-profit.csv",
        "mime_type": "text/csv",
        "file_content": b"metric;value\n",
    })

    assert result["payload"] == b"metric;value\n"
    assert "нельзя загружать как таблицу себестоимости" in result["caption"]


def test_document_contract_rejects_untrusted_or_mismatched_metadata():
    base = {
        "document_kind": "analytics_export",
        "filename": "report.json",
        "mime_type": "application/json",
        "file_content": b"{}",
    }
    assert prepare_telegram_document({**base, "filename": "../report.json"}) is None
    assert prepare_telegram_document({**base, "filename": "C-report.json"}) is not None
    assert prepare_telegram_document({**base, "filename": "bad name.json"}) is None
    assert prepare_telegram_document({**base, "mime_type": "text/csv"}) is None
    assert prepare_telegram_document({**base, "document_kind": "unknown"}) is None
    assert prepare_telegram_document({**base, "file_content": object()}) is None
