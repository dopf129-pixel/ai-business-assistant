import re
from decimal import Decimal, InvalidOperation

from services.unit_price_tariff_snapshot_adapter import UnitPriceTariffSnapshotAdapter


class UnitPriceTargetPlanningService:
    """Bounded, read-only price planning over the existing forward calculator."""

    MAX_FORWARD_CALCULATIONS = 128
    MAX_UPPER_BOUND_PROBES = 8
    MAX_LOWER_BOUND_PROBES = 8
    MAX_PRICE_SCALE_PROBES = 6
    MAX_COMPARISON_PRICES = 10
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
        if not 2 <= len(tokens) <= self.MAX_COMPARISON_PRICES or any(not token.strip() for token in tokens):
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
            "candidate_price_provenance": "planned_seller_price",
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
            "provenance": self._candidate_provenance(common),
            "source_price_provenance": common["provenance"].get("price"),
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
        frozen_tariff_snapshot=None,
        tariff_resolution_required=False,
        exact_price_rate_cents=None,
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

        if type(tariff_resolution_required) is not bool:
            return self._error_result("INVALID_TARIFF_REQUIREMENT", identity)
        tariff_identity = dict(identity or {})
        tariff_identity.setdefault("owner_id", tariff_identity.get("user_id"))
        tariff_aware = frozen_tariff_snapshot is not None or tariff_resolution_required
        if frozen_tariff_snapshot is not None:
            if UnitPriceTariffSnapshotAdapter.validate(
                frozen_tariff_snapshot, tariff_identity, inputs,
            ) is None:
                return self._error_result("INVALID_TARIFF_SNAPSHOT", identity)
        if exact_price_rate_cents is not None and (
            type(exact_price_rate_cents) is not int or exact_price_rate_cents < 1
        ):
            return self._error_result("INVALID_EXACT_PRICE_TARIFF", identity)

        rows = []
        common = {
            "identity": dict(identity or {}),
            "provenance": dict(provenance or {}),
            "sources": dict(sources or {}),
            "candidate_price_provenance": "manual_seller_assumption",
        }
        evaluation_count = 0

        def evaluate(price):
            nonlocal evaluation_count
            cents = int(price * self.HUNDRED)
            candidate_inputs = dict(inputs)
            candidate_inputs["price"] = format(price, ".2f")
            candidate_provenance = dict(common["provenance"])
            tariff_status = "ASSUMPTION_INPUT"
            tariff_reason = None
            tariff_origin = candidate_provenance.get("commission_rate", "unknown")
            resolved_rate = candidate_inputs.get("commission_rate")
            if frozen_tariff_snapshot is not None:
                resolution = UnitPriceTariffSnapshotAdapter.resolve_frozen(
                    frozen_tariff_snapshot, tariff_identity, cents,
                )
                if resolution.get("error") is True:
                    return {
                        "status": "SOURCE_UNAVAILABLE", "available": False,
                        "price": format(price, ".2f"), "profit": None,
                        "margin_percent": None, "tax": None, "goal_reached": None,
                        "commission_rate": None, "commission": None,
                        "commission_status": "SOURCE_UNAVAILABLE",
                        "commission_reason": resolution.get("code"),
                        "commission_origin": None,
                        "missing_inputs": [], "invalid_inputs": [],
                        "forward_result": None,
                    }
                if resolution.get("available") is not True:
                    status = resolution.get("status")
                    unavailable_status = (
                        "SOURCE_UNAVAILABLE" if status == "SOURCE_UNAVAILABLE"
                        else "COMMISSION_UNKNOWN"
                    )
                    return {
                        "status": unavailable_status, "available": False,
                        "price": format(price, ".2f"), "profit": None,
                        "margin_percent": None, "tax": None, "goal_reached": None,
                        "commission_rate": None, "commission": None,
                        "commission_status": status or "UNKNOWN",
                        "commission_reason": resolution.get("reason"),
                        "commission_origin": None,
                        "missing_inputs": ["commission_rate"],
                        "invalid_inputs": [], "forward_result": None,
                    }
                resolved_rate = resolution.get("commission_rate")
                tariff_status = resolution.get("status") or "CONFIRMED"
                profile = resolution.get("selected_profile") or {}
                tariff_origin = profile.get("origin") or "unknown"
                candidate_inputs["commission_rate"] = resolved_rate
                candidate_provenance["commission_rate"] = {
                    "MANUAL_SELLER_ASSUMPTION": "manual_seller_assumption",
                    "CURRENT_PRICE_POINT": "current_price_point",
                    "CONFIRMED_OFFICIAL_SOURCE": "confirmed_official_source",
                }.get(tariff_origin, "unknown")
            elif tariff_aware:
                original_cents = self._current_price_cents(inputs)
                if (exact_price_rate_cents is None or cents != exact_price_rate_cents
                        or original_cents != exact_price_rate_cents):
                    return {
                        "status": "COMMISSION_UNKNOWN", "available": False,
                        "price": format(price, ".2f"), "profit": None,
                        "margin_percent": None, "tax": None, "goal_reached": None,
                        "commission_rate": None, "commission": None,
                        "commission_status": "UNKNOWN",
                        "commission_reason": "NO_FROZEN_TARIFF_FOR_CANDIDATE_PRICE",
                        "commission_origin": None,
                        "missing_inputs": ["commission_rate"],
                        "invalid_inputs": [], "forward_result": None,
                    }
                tariff_status = "LEGACY_EXACT_PRICE_ONLY"
                tariff_origin = "legacy_frozen_plan_rate"
                candidate_provenance["commission_rate"] = tariff_origin

            try:
                forward = self.scenario_service.calculate(
                    candidate_inputs,
                    identity=common["identity"],
                    provenance=self._candidate_provenance({
                        **common, "provenance": candidate_provenance,
                    }),
                    sources=common["sources"],
                )
            except (ArithmeticError, OverflowError, TypeError, ValueError):
                forward = None
            evaluation_count += 1
            status = self._forward_status(forward)
            available = status == "CALCULATED"
            calculated = (forward or {}).get("calculated") or {}
            return {
                "status": "CALCULATED" if available else status,
                "available": available,
                "price": format(price, ".2f"),
                "profit": calculated.get("profit") if available else None,
                "margin_percent": calculated.get("margin_percent") if available else None,
                "tax": calculated.get("tax") if available else None,
                "goal_reached": (
                    self._reached(forward, price, target)
                    if available and target is not None else None
                ),
                "commission_rate": resolved_rate,
                "commission": calculated.get("commission") if available else None,
                "commission_status": tariff_status,
                "commission_reason": tariff_reason,
                "commission_origin": tariff_origin,
                "missing_inputs": list((forward or {}).get("missing_inputs") or []),
                "invalid_inputs": list((forward or {}).get("invalid_inputs") or []),
                "forward_result": forward if available else None,
            }

        for price in normalized_prices:
            rows.append(evaluate(price))

        best_profit = max(
            (Decimal(str(row["profit"])) for row in rows if row.get("available") is True),
            default=None,
        )
        for row in rows:
            row["is_best"] = (
                row.get("available") is True
                and Decimal(str(row["profit"])) == best_profit
            )
            row["evidence_basis"] = "SCENARIO_ASSUMPTIONS"
            row["profit_delta_vs_baseline"] = None

        baseline_price = self._current_price_cents(inputs)
        baseline = None
        if baseline_price is not None:
            baseline_decimal = self._price_from_cents(baseline_price)
            baseline_row = next(
                (row for row in rows if int(Decimal(row["price"]) * self.HUNDRED) == baseline_price),
                None,
            )
            if baseline_row is None:
                baseline_row = evaluate(baseline_decimal)
            baseline = {
                "price": format(baseline_decimal, ".2f"),
                "status": baseline_row.get("status"),
                "available": baseline_row.get("available") is True,
                "profit": baseline_row.get("profit"),
                "margin_percent": baseline_row.get("margin_percent"),
                "commission_rate": baseline_row.get("commission_rate"),
                "commission_status": baseline_row.get("commission_status"),
                "evidence_basis": baseline_row.get("evidence_basis", "SCENARIO_ASSUMPTIONS"),
            }
            if baseline.get("available") is True:
                baseline_profit = Decimal(str(baseline["profit"]))
                for row in rows:
                    if row.get("available") is True:
                        row["profit_delta_vs_baseline"] = format(
                            Decimal(str(row["profit"])) - baseline_profit, ".2f"
                        )

        return {
            "error": False,
            "kind": "UNIT_PRICE_OPTIONS_COMPARISON",
            "status": "COMPLETED",
            "available": any(row["available"] for row in rows),
            "baseline": baseline,
            "best_profit": format(best_profit, ".2f") if best_profit is not None else None,
            "best_prices": [row["price"] for row in rows if row.get("is_best") is True],
            "evidence_basis": "SCENARIO_ASSUMPTIONS",
            "advertising_basis": {
                "mode": "SAME_DRR",
                "revenue_basis": "SELLER_REVENUE",
                "rate": inputs.get("advertising_rate"),
            },
            "target_margin_percent": format(target, "f") if target is not None else None,
            "rows": rows,
            "candidate_count": len(rows),
            "evaluation_count": evaluation_count,
            "evaluation_limit": self.MAX_COMPARISON_PRICES + 1,
            "identity": common["identity"],
            "provenance": self._candidate_provenance(common),
            "source_price_provenance": common["provenance"].get("price"),
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
        high_reached = self._reached(high_result, high_price, target)
        feasible_upper = self._find_feasible_upper_bound(
            inputs,
            low,
            high,
            target,
            call_state,
            common,
            known_feasible=(high, high_result) if high_reached else None,
        )
        if feasible_upper is None:
            return self._unavailable_outcome("NOT_FOUND_IN_TESTED_RANGE")
        high, high_result = feasible_upper

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

    def _find_feasible_upper_bound(
        self, inputs, low, high, target, call_state, common, known_feasible=None
    ):
        """Find the smallest verified upper bracket among bounded probes."""
        candidates = [
            high - offset
            for offset in range(1, self.MAX_UPPER_BOUND_PROBES + 1)
            if low < high - offset
        ]
        current_cents = self._current_price_cents(inputs)
        if current_cents is not None and low < current_cents < high:
            candidates.append(current_cents)
        candidates.extend(
            low + offset
            for offset in range(1, self.MAX_LOWER_BOUND_PROBES + 1)
            if low + offset < high
        )
        candidates.extend(
            10**power
            for power in range(1, self.MAX_PRICE_SCALE_PROBES + 1)
            if low < 10**power < high
        )

        best = known_feasible
        upper_limit = best[0] if best is not None else high
        for cents in sorted(set(candidates)):
            if cents >= upper_limit:
                continue
            result, status = self._evaluate(inputs, cents, call_state, common)
            if status != "CALCULATED":
                if best is not None:
                    continue
                return None
            if self._reached(result, self._price_from_cents(cents), target):
                return cents, result
        return best

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
                provenance=self._candidate_provenance(common),
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
    def _candidate_provenance(common):
        provenance = dict(common["provenance"])
        provenance["price"] = common["candidate_price_provenance"]
        return provenance

    def _current_price_cents(self, inputs):
        raw_price = inputs.get("price")
        if raw_price is None or isinstance(raw_price, bool):
            return None
        try:
            if isinstance(raw_price, Decimal):
                price = raw_price
            elif isinstance(raw_price, (str, int, float)):
                text = str(raw_price).strip().replace("\u00a0", "").replace(" ", "")
                if len(text) > 64 or ("," in text and "." in text):
                    return None
                price = Decimal(text.replace(",", "."))
            else:
                return None
        except (InvalidOperation, TypeError, ValueError):
            return None
        if price.is_finite() and price.as_tuple().exponent < -2:
            sign, digits, exponent = price.as_tuple()
            digits = list(digits)
            while exponent < -2 and len(digits) > 1 and digits[-1] == 0:
                digits.pop()
                exponent += 1
            price = Decimal((sign, tuple(digits), exponent))
        if not self._is_valid_price(price):
            return None
        return int(price * self.HUNDRED)

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
        if not isinstance(prices, (list, tuple)) or not 2 <= len(prices) <= self.MAX_COMPARISON_PRICES:
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
            "message": "Введите от 2 до 10 разных положительных цен через точку с запятой или с новой строки.",
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
