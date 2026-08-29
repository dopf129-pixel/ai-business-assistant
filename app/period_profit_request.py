from datetime import date, datetime, timedelta


SUPPORTED_PRESETS = {"TODAY": 1, "7D": 7, "28D": 28, "56D": 56, "90D": 90}


def build_period_profit_request(period_code=None, date_from=None, date_to=None, today=None):
    if date_from or date_to:
        start = _date(date_from)
        end = _date(date_to)
        if start is None or end is None or start > end:
            return _blocked("PERIOD_PROFIT_REQUEST_PERIOD_INVALID")
        return {"error": False, "status": "PERIOD_PROFIT_REQUEST_READY", "mode": "CUSTOM", "date_from": start.isoformat(), "date_to": end.isoformat(), "period_code": None}

    code = str(period_code or "7D").upper()
    if code not in SUPPORTED_PRESETS:
        return _blocked("PERIOD_PROFIT_REQUEST_PRESET_INVALID")
    end = _date(today) or date.today()
    days = SUPPORTED_PRESETS[code]
    start = end - timedelta(days=days - 1)
    return {"error": False, "status": "PERIOD_PROFIT_REQUEST_READY", "mode": "PRESET", "period_code": code, "date_from": start.isoformat(), "date_to": end.isoformat()}


def build_previous_period_profit_request(request):
    source = dict(request or {})
    if source.get("status") != "PERIOD_PROFIT_REQUEST_READY":
        return _blocked("PERIOD_PROFIT_REQUEST_REQUIRED")
    start = _date(source.get("date_from"))
    end = _date(source.get("date_to"))
    if start is None or end is None or start > end:
        return _blocked("PERIOD_PROFIT_REQUEST_PERIOD_INVALID")
    days = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=days - 1)
    return {"error": False, "status": "PERIOD_PROFIT_REQUEST_READY", "mode": "PREVIOUS_COMPARABLE", "period_code": source.get("period_code"), "date_from": previous_start.isoformat(), "date_to": previous_end.isoformat()}


def _date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _blocked(code):
    return {"error": True, "code": code, "status": "PERIOD_PROFIT_REQUEST_UNAVAILABLE"}
