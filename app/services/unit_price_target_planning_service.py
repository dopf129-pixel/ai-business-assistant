import re
from decimal import Decimal, InvalidOperation


class UnitPriceTargetPlanningService:
    """Bounded, read-only price planning over the existing forward calculator."""

    MAX_FORWARD_CALCULATIONS = 128
    MIN_PRICE_CENTS = 1
    CENT = Decimal("0.01")
    HUNDRED = Decimal("100")
    _TARGET_PATTERN = re.compile(r"\d+(?:[.,]\d{1,2})?\Z")
    _PRICE_PATTERN = re.compile(
        r"(?:\d+(?:[.,]\d{1,2})?|"
        r"\d{1,3}(?:[ \u00a0\u202f]+\d{3})+(?:[.,]\d{1,2})?)\Z"
    )

    def __init__(self, scenario_service):
        self.scenario_service = scenario_service
        self.max_price = self._max_supported_price(scenario_service)
        self.max_price_cents = int(self.max_price * self.HUNDRED)

    def parse_target_margin(self, text):
        if not isinstance(text, str):
            return self._invalid_target()
        value = text.strip()
        if len(value) > 16 or not self._TARGET_PATTERN.fullmatch(value):
            return self._invalid_target()
        try:
            target = Decimal(value.replace(",", "."))
        except InvalidOperation:
            return self._invalid_target()
        if not target.is_finite() or target < 0 or target > self.HUNDRED:
            return self._invalid_target()
        return {
            "error": False,
            "valid": True,
            "value": target,
            "normalized": format(target, "f"),
        }

    def parse_price_list(self, text):
        if not isinstance(text, str) or len(text) > 256:
            return self._invalid_price_list()
        tokens = re.split(r";|\r\n|\r|\n", text.strip())
        if not 2 <= len(tokens) <= 5 or any(not token.strip() for token in tokens):
            return self._invalid_price_list()

        prices = []
        cents_seen = set()
        for token in tokens:
            price = self._parse_price_token(token)
            if price is None:
                return self._invalid_price_list()
            cents = int(price * self.HUNDRED)
            if cents in cents_seen:
                return self._invalid_price_list(code="DUPLICATE_PRICE")
            cents_seen.add(cents)
            prices.append(price)
        return {
            "error": False,
            "valid": True,
            "prices": prices,
            "normalized": [format(price, ".2f") for price in prices],
        }

    def solve(
        self,
        inputs,
        target_margin_percent,
        identity=None,
        provenance=None,
        sources=None,
    ):
        target_result = self._normalize_target(target_margin_percent)
        if not target_result["valid"]:
            return self._error_result("INVALID_TARGET", identity)
        if not isinstance(inputs, dict):
            return self._error_result("INVALID_INPUTS", identity)

        target = target_result["value"]
        call_state = {"count": 0, "cache": {}}
        common = {
            "identity": dict(identity or {}),
            "provenance": dict(provenance or {}),
            "sources": dict(sources or {}),
        }

        break_even = self._find_candidate(
            inputs, Decimal("0"), call_state, common
        )
        if target == 0:
            target_outcome = dict(break_even)
        else:
            target_outcome = self._find_candidate(
                inputs, target, call_state, common
            )

        validated = {}
        for outcome in (break_even, target_outcome):
            if outcome.get("status") != "FOUND":
                continue
            price = outcome["price"]
            if price in validated:
                outcome["forward_result"] = validated[price]
                continue
            cents = int(Decimal(price) * self.HUNDRED)
            forward, forward_status = self._evaluate(
                inputs, cents, call_state, common, bypass_cache=True
            )
            if forward_status != "CALCULATED" or not self._reached(
                forward, Decimal(price),
                target if outcome is target_outcome else Decimal("0"),
            ):
                outcome.update(self._unavailable_outcome(
                    "FINAL_CHECK_FAILED", forward
                ))
                continue
            outcome.update(self._success_outcome(
                Decimal(price), forward,
                target if outcome is target_outcome else Decimal("0"),
            ))
            validated[price] = forward

        # A 0% target is the same predicate as break-even; publish the same
        # final direct result and avoid spending a second validation call.
        if target == 0 and break_even.get("status") == "FOUND":
            target_outcome = dict(break_even)

        return {
            "error": False,
            "kind": "UNIT_PRICE_TARGET_PLAN",
            "status": "COMPLETED",
            "available": (
                break_even.get("status") == "FOUND"
                or target_outcome.get("status") == "FOUND"
            ),
            "target_margin_percent": format(target, "f"),
            "break_even": break_even,
            "target": target_outcome,
            "evaluation_count": call_state["count"],
            "evaluation_limit": self.MAX_FORWARD_CALCULATIONS,
            "identity": common["identity"],
            "provenance": common["provenance"],
            "sources": common["sources"],
            "read_only": True,
            "executed": False,
        }

    def compare_prices(
        self,
        inputs,
        prices,
        target_margin_percent=None,
        identity=None,
        provenance=None,
        sources=None,
    ):
        if isinstance(prices, str):
            parsed = self.parse_price_list(prices)
            if parsed["error"]:
                return self._error_result(parsed["code"], identity)
            normalized_prices = parsed["prices"]
        else:
            normalized_prices = self._validate_price_values(prices)
            if normalized_prices is None:
                return self._error_result("INVALID_PRICE_LIST", identity)

        target = None
        if target_margin_percent is not None:
            target_result = self._normalize_target(target_margin_percent)
            if not target_result["valid"]:
                return self._error_result("INVALID_TARGET", identity)
            target = target_result["value"]
        if not isinstance(inputs, dict):
            return self._error_result("INVALID_INPUTS", identity)

        rows = []
        common = {
            "identity": dict(identity or {}),
            "provenance": dict(provenance or {}),
            "sources": dict(sources or {}),
        }
        for price in normalized_prices:
            candidate_inputs = dict(inputs)
            candidate_inputs["price"] = format(price, ".2f")
            try:
                forward = self.scenario_service.calculate(
                    candidate_inputs,
                    identity=common["identity"],
                    provenance=common["provenance"],
                    sources=common["sources"],
                )
            except (ArithmeticError, OverflowError, TypeError, ValueError):
                forward = None
            available = self._forward_status(forward) == "CALCULATED"
            calculated = (forward or {}).get("calculated") or {}
            goal_reached = (
                self._reached(forward, price, target)
                if available and target is not None
                else None
            )
            rows.append({
                "status": "CALCULATED" if available else self._forward_status(forward),
                "available": available,
                "price": format(price, ".2f"),
                "profit": calculated.get("profit") if available else None,
                "margin_percent": calculated.get("margin_percent") if available else None,
                "tax": calculated.get("tax") if available else None,
                "goal_reached": goal_reached,
                "missing_inputs": list((forward or {}).get("missing_inputs") or []),
                "invalid_inputs": list((forward or {}).get("invalid_inputs") or []),
                "forward_result": forward if available else None,
            })

        return {
            "error": False,
            "kind": "UNIT_PRICE_OPTIONS_COMPARISON",
            "status": "COMPLETED",
            "available": any(row["available"] for row in rows),
            "target_margin_percent": format(target, "f") if target is not None else None,
            "rows": rows,
            "evaluation_count": len(rows),
            "evaluation_limit": len(normalized_prices),
            "identity": common["identity"],
            "provenance": common["provenance"],
            "sources": common["sources"],
            "read_only": True,
            "executed": False,
        }

    def _find_candidate(self, inputs, target, call_state, common):
        low = self.MIN_PRICE_CENTS
        low_result, low_status = self._evaluate(inputs, low, call_state, common)
        if low_status != "CALCULATED":
            return self._unavailable_outcome(low_status, low_result)
        low_price = self._price_from_cents(low)
        if self._reached(low_result, low_price, target):
            return self._success_outcome(low_price, low_result, target)

        high = self.max_price_cents
        high_result, high_status = self._evaluate(inputs, high, call_state, common)
        if high_status != "CALCULATED":
            return self._unavailable_outcome(high_status, high_result)
        high_price = self._price_from_cents(high)
        if not self._reached(high_result, high_price, target):
            return self._unavailable_outcome("NOT_FOUND_IN_TESTED_RANGE")

        while high - low > 1:
            middle = (low + high) // 2
            middle_result, middle_status = self._evaluate(
                inputs, middle, call_state, common
            )
            if middle_status != "CALCULATED":
                return self._unavailable_outcome(middle_status, middle_result)
            if self._reached(
                middle_result, self._price_from_cents(middle), target
            ):
                high = middle
                high_result = middle_result
            else:
                low = middle

        return self._success_outcome(
            self._price_from_cents(high), high_result, target
        )

    def _evaluate(self, inputs, cents, call_state, common, bypass_cache=False):
        if not bypass_cache and cents in call_state["cache"]:
            return call_state["cache"][cents]
        if call_state["count"] >= self.MAX_FORWARD_CALCULATIONS:
            return None, "SEARCH_BUDGET_EXHAUSTED"
        call_state["count"] += 1
        candidate_inputs = dict(inputs)
        candidate_inputs["price"] = format(self._price_from_cents(cents), ".2f")
        try:
            result = self.scenario_service.calculate(
                candidate_inputs,
                identity=common["identity"],
                provenance=common["provenance"],
                sources=common["sources"],
            )
        except (ArithmeticError, OverflowError, TypeError, ValueError):
            result = None
        status = self._forward_status(result)
        pair = (result, status)
        if not bypass_cache:
            call_state["cache"][cents] = pair
        return pair

    @staticmethod
    def _forward_status(result):
        if isinstance(result, dict) and result.get("available") is True:
            return "CALCULATED"
        if isinstance(result, dict) and result.get("missing_inputs"):
            return "MISSING_INPUTS"
        if isinstance(result, dict) and result.get("invalid_inputs"):
            return "INVALID_INPUTS"
        return "UNSUPPORTED_FORWARD_CALCULATION"

    @staticmethod
    def _reached(result, price, target):
        if not isinstance(result, dict) or result.get("available") is not True:
            return False
        try:
            profit = Decimal(str(result["calculated"]["profit"]))
            return (
                profit.is_finite()
                and profit * Decimal("100") >= target * price
            )
        except (KeyError, InvalidOperation, TypeError, ValueError):
            return False

    @staticmethod
    def _success_outcome(price, forward, target):
        calculated = forward["calculated"]
        return {
            "status": "FOUND",
            "available": True,
            "price": format(price, ".2f"),
            "profit": calculated.get("profit"),
            "margin_percent": calculated.get("margin_percent"),
            "tax": calculated.get("tax"),
            "goal_reached": UnitPriceTargetPlanningService._reached(
                forward, price, target
            ),
            "forward_result": forward,
        }

    @staticmethod
    def _unavailable_outcome(status, forward=None):
        return {
            "status": status,
            "available": False,
            "price": None,
            "profit": None,
            "margin_percent": None,
            "tax": None,
            "goal_reached": None,
            "missing_inputs": list((forward or {}).get("missing_inputs") or []),
            "invalid_inputs": list((forward or {}).get("invalid_inputs") or []),
            "forward_result": None,
        }

    def _normalize_target(self, value):
        if isinstance(value, bool):
            return {"valid": False, "value": None}
        if isinstance(value, Decimal):
            target = value
        elif isinstance(value, (str, int, float)):
            text = str(value).strip()
            if len(text) > 16 or not self._TARGET_PATTERN.fullmatch(text):
                return {"valid": False, "value": None}
            try:
                target = Decimal(text.replace(",", "."))
            except InvalidOperation:
                return {"valid": False, "value": None}
        else:
            return {"valid": False, "value": None}
        exponent = target.as_tuple().exponent if target.is_finite() else -3
        if (
            not target.is_finite()
            or target < 0
            or target > self.HUNDRED
            or exponent < -2
        ):
            return {"valid": False, "value": None}
        return {"valid": True, "value": target}

    def _validate_price_values(self, prices):
        if not isinstance(prices, (list, tuple)) or not 2 <= len(prices) <= 5:
            return None
        normalized = []
        seen = set()
        for value in prices:
            if isinstance(value, bool):
                return None
            try:
                price = value if isinstance(value, Decimal) else Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError):
                return None
            if not self._is_valid_price(price):
                return None
            cents = int(price * self.HUNDRED)
            if cents in seen:
                return None
            seen.add(cents)
            normalized.append(self._price_from_cents(cents))
        return normalized

    def _parse_price_token(self, token):
        value = token.strip()
        if not value or len(value) > 40 or not self._PRICE_PATTERN.fullmatch(value):
            return None
        compact = re.sub(r"[ \u00a0\u202f]", "", value).replace(",", ".")
        try:
            price = Decimal(compact)
        except InvalidOperation:
            return None
        return price if self._is_valid_price(price) else None

    def _is_valid_price(self, price):
        if not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
            return False
        if price.as_tuple().exponent < -2 or price > self.max_price:
            return False
        return price == price.quantize(self.CENT)

    @staticmethod
    def _price_from_cents(cents):
        return Decimal(cents) / Decimal("100")

    def _max_supported_price(self, scenario_service):
        digits = int(scenario_service.MAX_INPUT_DIGITS)
        adjusted_exponent = int(scenario_service.MAX_INPUT_ADJUSTED_EXPONENT)
        max_integer_digits = min(digits - 2, adjusted_exponent + 1)
        return (Decimal(10) ** max_integer_digits) - self.CENT

    @staticmethod
    def _invalid_target():
        return {
            "error": True,
            "valid": False,
            "code": "INVALID_TARGET",
            "message": "Введите процент от 0 до 100, не более двух знаков после запятой.",
        }

    @staticmethod
    def _invalid_price_list(code="INVALID_PRICE_LIST"):
        return {
            "error": True,
            "valid": False,
            "code": code,
            "message": "Введите от 2 до 5 разных положительных цен через точку с запятой или с новой строки.",
        }

    @staticmethod
    def _error_result(code, identity=None):
        return {
            "error": True,
            "code": code,
            "kind": "UNIT_PRICE_TARGET_PLAN",
            "available": False,
            "identity": dict(identity or {}),
            "read_only": True,
            "executed": False,
        }
