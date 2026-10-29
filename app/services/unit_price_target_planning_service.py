import re
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from services.unit_price_advertising_compensation_service import UnitPriceAdvertisingCompensationService
from services.unit_price_tariff_snapshot_adapter import UnitPriceTariffSnapshotAdapter


class UnitPriceTargetPlanningService:
    """Bounded, read-only price planning over the existing forward calculator."""

    MAX_FORWARD_CALCULATIONS = 128
    MAX_TARIFF_FORWARD_CALCULATIONS = 1_024
    MAX_UPPER_BOUND_PROBES = 8
    MAX_LOWER_BOUND_PROBES = 8
    MAX_PRICE_SCALE_PROBES = 6
    MAX_COMPARISON_PRICES = 10
    MAX_PRICE_GRID_CANDIDATES = 200
    MAX_PRICE_GRID_TARIFF_RULES = 20
    MAX_COMPARISON_FORWARD_CALCULATIONS = 1_024
    MIN_PRICE_CENTS = 1
    # Bounds all rounding introduced by per-component HALF_UP and the existing
    # float-based tax service. Ambiguous intervals are evaluated canonically.
    ROUNDING_GAP_BOUND = Decimal("0.25")
    CENT = Decimal("0.01")
    HUNDRED = Decimal("100")
    _TARGET_PATTERN = re.compile(r"\d+(?:[.,]\d{1,2})?\Z")
    _PRICE_PATTERN = re.compile(
        r"(?:\d+(?:[.,]\d{1,2})?|"
        r"\d{1,3}(?:[ \u00a0\u202f]+\d{3})+(?:[.,]\d{1,2})?)\Z"
    )

    def __init__(self, scenario_service):
        self.scenario_service = scenario_service
        self.advertising_compensation_service = UnitPriceAdvertisingCompensationService()
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

    def parse_price_grid(self, text):
        if not isinstance(text, str) or len(text) > 128:
            return {"valid": False, "code": "INVALID_PRICE_GRID"}
        tokens = re.split(r";|\r\n|\r|\n", text.strip())
        if len(tokens) != 3 or any(not token.strip() for token in tokens):
            return {"valid": False, "code": "INVALID_PRICE_GRID"}
        start, end, step = (self._parse_price_token(token) for token in tokens)
        if start is None or end is None or step is None or start >= end or step <= 0:
            return {"valid": False, "code": "INVALID_PRICE_GRID"}
        return {
            "valid": True,
            "start": start,
            "end": end,
            "step": step,
            "normalized": [format(value, ".2f") for value in (start, end, step)],
        }

    def build_price_grid(
        self, text, *, frozen_tariff_snapshot=None, identity=None, inputs=None,
    ):
        parsed = self.parse_price_grid(text)
        if parsed.get("valid") is not True:
            return parsed
        start_cents = int(parsed["start"] * self.HUNDRED)
        end_cents = int(parsed["end"] * self.HUNDRED)
        step_cents = int(parsed["step"] * self.HUNDRED)
        span = end_cents - start_cents
        whole_steps, remainder = divmod(span, step_cents)
        base_count = whole_steps + 1 + (1 if remainder else 0)
        if base_count > self.MAX_PRICE_GRID_CANDIDATES:
            return {
                "valid": False, "code": "PRICE_GRID_LIMIT",
                "required_candidates_at_least": base_count,
                "candidate_limit": self.MAX_PRICE_GRID_CANDIDATES,
            }

        base_cents = {start_cents + index * step_cents for index in range(whole_steps + 1)}
        base_cents.add(end_cents)  # Include the requested end even when step misses it.
        tariff_boundaries = set()
        tariff_rule_count = 0
        tariff_source_status = "NO_FROZEN_SNAPSHOT"
        if frozen_tariff_snapshot is not None:
            tariff_identity = dict(identity or {})
            tariff_identity.setdefault("owner_id", tariff_identity.get("user_id"))
            if (not isinstance(inputs, dict)
                    or UnitPriceTariffSnapshotAdapter.validate(
                        frozen_tariff_snapshot, tariff_identity, inputs,
                    ) is None):
                return {"valid": False, "code": "INVALID_TARIFF_SNAPSHOT"}
            tariff_source_status = str(frozen_tariff_snapshot.get("status") or "UNKNOWN")[:48]
            profiles = frozen_tariff_snapshot.get("profiles") or []
            tariff_rule_count = sum(
                len(profile.get("bands") or [])
                for profile in profiles if isinstance(profile, dict)
            )
            if tariff_rule_count > self.MAX_PRICE_GRID_TARIFF_RULES:
                return {
                    "valid": False, "code": "PRICE_GRID_TARIFF_RULE_LIMIT",
                    "tariff_rule_count": tariff_rule_count,
                    "tariff_rule_limit": self.MAX_PRICE_GRID_TARIFF_RULES,
                }
            for profile in profiles:
                for band in profile.get("bands") or []:
                    lower = band["price_from_cents"]
                    upper = band["price_to_cents"]
                    for boundary in (lower - 1, lower, upper, upper + 1):
                        if start_cents <= boundary <= end_cents:
                            tariff_boundaries.add(boundary)

        inserted_boundaries = tariff_boundaries - base_cents
        candidate_cents = sorted(base_cents | tariff_boundaries)
        if len(candidate_cents) > self.MAX_PRICE_GRID_CANDIDATES:
            return {
                "valid": False, "code": "PRICE_GRID_LIMIT",
                "required_candidates": len(candidate_cents),
                "candidate_limit": self.MAX_PRICE_GRID_CANDIDATES,
                "tariff_rule_count": tariff_rule_count,
            }
        prices = [self._price_from_cents(value) for value in candidate_cents]
        normalized = [format(price, ".2f") for price in prices]
        metadata = {
            "price_basis": "SELLER_PRICE_RUB",
            "start": format(parsed["start"], ".2f"),
            "end": format(parsed["end"], ".2f"),
            "step": format(parsed["step"], ".2f"),
            "base_grid_count": len(base_cents),
            "tariff_rule_count": tariff_rule_count,
            "tariff_rule_limit": self.MAX_PRICE_GRID_TARIFF_RULES,
            "tariff_source_status": tariff_source_status,
            "tariff_boundary_prices": [
                format(self._price_from_cents(value), ".2f")
                for value in sorted(tariff_boundaries)
            ],
            "inserted_tariff_boundary_prices": [
                format(self._price_from_cents(value), ".2f")
                for value in sorted(inserted_boundaries)
            ],
            "candidate_count": len(prices),
            "candidate_limit": self.MAX_PRICE_GRID_CANDIDATES,
            "searched_prices": normalized,
            "global_optimum_claimed": False,
        }
        return {"valid": True, "prices": prices, "normalized": normalized, "metadata": metadata}

    def parse_advertising_rate_list(self, text, expected_count):
        if (not isinstance(text, str) or len(text) > 256
                or type(expected_count) is not int
                or not 2 <= expected_count <= self.MAX_COMPARISON_PRICES):
            return {"valid": False, "code": "INVALID_ADVERTISING_RATE_LIST"}
        tokens = re.split(r";|\r\n|\r|\n", text.strip())
        if len(tokens) != expected_count or any(not token.strip() for token in tokens):
            return {"valid": False, "code": "INVALID_ADVERTISING_RATE_LIST"}
        rates = []
        for token in tokens:
            parsed = self._normalize_target(token.strip())
            if not parsed["valid"]:
                return {"valid": False, "code": "INVALID_ADVERTISING_RATE_LIST"}
            rates.append(parsed["value"])
        return {
            "valid": True,
            "rates": rates,
            "normalized": [format(rate, "f") for rate in rates],
        }

    def parse_advertising_cost_basis(self, text):
        if not isinstance(text, str) or len(text) > 128:
            return {"valid": False, "code": "INVALID_ADVERTISING_COST_BASIS"}
        tokens = re.split(r";|\r\n|\r|\n", text.strip())
        if len(tokens) != 2 or any(not token.strip() for token in tokens):
            return {"valid": False, "code": "INVALID_ADVERTISING_COST_BASIS"}
        amount_text, units_text = tokens[0].strip(), tokens[1].strip()
        if len(amount_text) > 40 or not self._PRICE_PATTERN.fullmatch(amount_text):
            return {"valid": False, "code": "INVALID_ADVERTISING_COST_BASIS"}
        try:
            total_spend = Decimal(re.sub(r"[ \u00a0\u202f]", "", amount_text).replace(",", "."))
        except InvalidOperation:
            return {"valid": False, "code": "INVALID_ADVERTISING_COST_BASIS"}
        if (not total_spend.is_finite() or total_spend < 0
                or total_spend > self.max_price or total_spend.as_tuple().exponent < -2):
            return {"valid": False, "code": "INVALID_ADVERTISING_COST_BASIS"}
        if not re.fullmatch(r"[1-9]\d{0,4}", units_text):
            return {"valid": False, "code": "INVALID_ADVERTISING_COST_BASIS"}
        units = int(units_text)
        if units > 10_000:
            return {"valid": False, "code": "INVALID_ADVERTISING_COST_BASIS"}
        amount_per_unit = (total_spend / Decimal(units)).quantize(
            self.CENT, rounding=ROUND_HALF_UP,
        )
        return {
            "valid": True,
            "basis": {
                "mode": "MANUAL_COST_PER_SUCCESSFUL_UNIT",
                "revenue_basis": "NOT_APPLICABLE",
                "denominator": "SUCCESSFUL_UNITS",
                "total_spend": format(total_spend, ".2f"),
                "successful_units": units,
                "amount_per_unit": format(amount_per_unit, ".2f"),
                "origin": "MANUAL_SCENARIO_ASSUMPTION",
            },
        }

    def solve(
        self,
        inputs,
        target_margin_percent,
        identity=None,
        provenance=None,
        sources=None,
        frozen_tariff_snapshot=None,
        tariff_resolution_required=False,
        exact_price_rate_cents=None,
        max_evaluations=None,
    ):
        target_result = self._normalize_target(target_margin_percent)
        if not target_result["valid"]:
            return self._error_result("INVALID_TARGET", identity)
        if not isinstance(inputs, dict):
            return self._error_result("INVALID_INPUTS", identity)

        target = target_result["value"]
        if type(tariff_resolution_required) is not bool:
            return self._error_result("INVALID_TARIFF_REQUIREMENT", identity)
        if exact_price_rate_cents is not None and (
            type(exact_price_rate_cents) is not int or exact_price_rate_cents < 1
        ):
            return self._error_result("INVALID_EXACT_PRICE_TARIFF", identity)
        tariff_aware = (
            frozen_tariff_snapshot is not None
            or tariff_resolution_required
            or exact_price_rate_cents is not None
        )
        default_evaluation_limit = (
            self.MAX_TARIFF_FORWARD_CALCULATIONS
            if tariff_aware else self.MAX_FORWARD_CALCULATIONS
        )
        if max_evaluations is not None and (
            type(max_evaluations) is not int
            or not 1 <= max_evaluations <= default_evaluation_limit
        ):
            return self._error_result("INVALID_EVALUATION_LIMIT", identity)
        tariff_identity = dict(identity or {})
        tariff_identity.setdefault("owner_id", tariff_identity.get("user_id"))
        if frozen_tariff_snapshot is not None and UnitPriceTariffSnapshotAdapter.validate(
            frozen_tariff_snapshot, tariff_identity, inputs,
        ) is None:
            return self._error_result("INVALID_TARIFF_SNAPSHOT", identity)

        call_state = {
            "count": 0,
            "cache": {},
            "tariff_cache": {},
            "limit": max_evaluations or default_evaluation_limit,
        }
        common = {
            "identity": dict(identity or {}),
            "provenance": dict(provenance or {}),
            "sources": dict(sources or {}),
            "candidate_price_provenance": "planned_seller_price",
        }

        if tariff_aware:
            tariff_search = self._tariff_search_segments(
                frozen_tariff_snapshot, tariff_identity,
            )
            if tariff_search.get("error") is True:
                return self._error_result(tariff_search["code"], identity)
            if tariff_search.get("status") == "SOURCE_UNAVAILABLE":
                break_even = self._unavailable_outcome("SOURCE_UNAVAILABLE")
                target_outcome = self._unavailable_outcome("SOURCE_UNAVAILABLE")
            elif exact_price_rate_cents is not None and frozen_tariff_snapshot is None:
                # A legacy saved plan confirms a rate at its saved price only.
                exact_cents = self._current_price_cents(inputs)
                if exact_cents != exact_price_rate_cents:
                    break_even = self._unavailable_outcome("COMMISSION_UNKNOWN")
                    target_outcome = self._unavailable_outcome("COMMISSION_UNKNOWN")
                else:
                    exact_segment = [{
                        "price_from_cents": exact_cents,
                        "price_to_cents": exact_cents,
                        "commission_rate": inputs.get("commission_rate"),
                        "commission_origin": "legacy_frozen_plan_rate",
                        "commission_status": "LEGACY_EXACT_PRICE_ONLY",
                    }]
                    break_even = self._find_candidate_in_tariff_segments(
                        inputs, Decimal("0"), call_state, common, exact_segment,
                        frozen_tariff_snapshot=None,
                        tariff_identity=tariff_identity,
                        exact_price_rate_cents=exact_price_rate_cents,
                    )
                    target_outcome = (
                        dict(break_even) if target == 0 else
                        self._find_candidate_in_tariff_segments(
                            inputs, target, call_state, common, exact_segment,
                            frozen_tariff_snapshot=None,
                            tariff_identity=tariff_identity,
                            exact_price_rate_cents=exact_price_rate_cents,
                        )
                    )
                    tariff_search["covered_segments"] = exact_segment
                    tariff_search["coverage_complete"] = False
                    tariff_search["scope"] = "EXACT_SAVED_PRICE_ONLY"
                    tariff_search["gaps"] = []
                    if exact_cents > self.MIN_PRICE_CENTS:
                        tariff_search["gaps"].append({
                            "price_from_cents": self.MIN_PRICE_CENTS,
                            "price_to_cents": exact_cents - 1,
                            "reason": "LEGACY_RATE_CONFIRMED_AT_SAVED_PRICE_ONLY",
                        })
                    if exact_cents < self.max_price_cents:
                        tariff_search["gaps"].append({
                            "price_from_cents": exact_cents + 1,
                            "price_to_cents": self.max_price_cents,
                            "reason": "LEGACY_RATE_CONFIRMED_AT_SAVED_PRICE_ONLY",
                        })
            else:
                segments = tariff_search.get("covered_segments") or []
                if not segments:
                    break_even = self._unavailable_outcome("COMMISSION_UNKNOWN")
                    target_outcome = self._unavailable_outcome("COMMISSION_UNKNOWN")
                else:
                    break_even = self._find_candidate_in_tariff_segments(
                        inputs, Decimal("0"), call_state, common, segments,
                        frozen_tariff_snapshot=frozen_tariff_snapshot,
                        tariff_identity=tariff_identity,
                    )
                    target_outcome = (
                        dict(break_even) if target == 0 else
                        self._find_candidate_in_tariff_segments(
                            inputs, target, call_state, common, segments,
                            frozen_tariff_snapshot=frozen_tariff_snapshot,
                            tariff_identity=tariff_identity,
                        )
                    )
            tariff_search = self._public_tariff_search_metadata(tariff_search)
            if break_even.get("status") == "FOUND":
                self._verify_tariff_candidate(
                    break_even, Decimal("0"), inputs, call_state, common,
                    frozen_tariff_snapshot, tariff_identity,
                    exact_price_rate_cents,
                )
            if target == 0:
                target_outcome = dict(break_even)
            elif target_outcome.get("status") == "FOUND":
                self._verify_tariff_candidate(
                    target_outcome, target, inputs, call_state, common,
                    frozen_tariff_snapshot, tariff_identity,
                    exact_price_rate_cents,
                )
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
                "evaluation_limit": call_state["limit"],
                "tariff_search": tariff_search,
                "identity": common["identity"],
                "provenance": self._candidate_provenance(common),
                "source_price_provenance": common["provenance"].get("price"),
                "sources": common["sources"],
                "read_only": True,
                "executed": False,
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
            "evaluation_limit": call_state["limit"],
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
        advertising_mode="SAME_DRR",
        advertising_rates=None,
        advertising_cost_basis=None,
        price_grid_metadata=None,
    ):
        grid_mode = price_grid_metadata is not None
        if isinstance(prices, str):
            if grid_mode:
                return self._error_result("INVALID_PRICE_GRID", identity)
            parsed = self.parse_price_list(prices)
            if parsed["error"]:
                return self._error_result(parsed["code"], identity)
            normalized_prices = parsed["prices"]
        else:
            normalized_prices = self._validate_price_values(
                prices,
                max_prices=(self.MAX_PRICE_GRID_CANDIDATES if grid_mode
                            else self.MAX_COMPARISON_PRICES),
            )
            if normalized_prices is None:
                return self._error_result(
                    "INVALID_PRICE_GRID" if grid_mode else "INVALID_PRICE_LIST", identity,
                )
        target = None
        if target_margin_percent is not None:
            target_result = self._normalize_target(target_margin_percent)
            if not target_result["valid"]:
                return self._error_result("INVALID_TARGET", identity)
            target = target_result["value"]
        if not isinstance(inputs, dict):
            return self._error_result("INVALID_INPUTS", identity)

        normalized_advertising_mode = str(advertising_mode or "").strip().upper()
        normalized_rates = None
        normalized_cost_basis = None
        if normalized_advertising_mode == "SAME_DRR":
            if advertising_rates is not None or advertising_cost_basis is not None:
                return self._error_result("INVALID_ADVERTISING_BASIS", identity)
        elif normalized_advertising_mode == "PER_PRICE_DRR":
            if advertising_cost_basis is not None:
                return self._error_result("INVALID_ADVERTISING_BASIS", identity)
            if isinstance(advertising_rates, str):
                parsed_rates = self.parse_advertising_rate_list(
                    advertising_rates, len(normalized_prices),
                )
                if parsed_rates.get("valid") is not True:
                    return self._error_result("INVALID_ADVERTISING_RATE_LIST", identity)
                normalized_rates = parsed_rates["rates"]
            elif isinstance(advertising_rates, (list, tuple)) and len(advertising_rates) == len(normalized_prices):
                normalized_rates = []
                for value in advertising_rates:
                    parsed_rate = self._normalize_target(value)
                    if not parsed_rate["valid"]:
                        return self._error_result("INVALID_ADVERTISING_RATE_LIST", identity)
                    normalized_rates.append(parsed_rate["value"])
            else:
                return self._error_result("INVALID_ADVERTISING_RATE_LIST", identity)
        elif normalized_advertising_mode == "MANUAL_COST_PER_SUCCESSFUL_UNIT":
            if advertising_rates is not None or not isinstance(advertising_cost_basis, dict):
                return self._error_result("INVALID_ADVERTISING_COST_BASIS", identity)
            parsed_cost = self.parse_advertising_cost_basis(
                str(advertising_cost_basis.get("total_spend", ""))
                + ";" + str(advertising_cost_basis.get("successful_units", "")),
            )
            if parsed_cost.get("valid") is not True:
                return self._error_result("INVALID_ADVERTISING_COST_BASIS", identity)
            normalized_cost_basis = parsed_cost["basis"]
        else:
            return self._error_result("INVALID_ADVERTISING_MODE", identity)

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
        if grid_mode and not self._valid_price_grid_metadata(
            price_grid_metadata,
            normalized_prices,
            frozen_tariff_snapshot=frozen_tariff_snapshot,
            identity=tariff_identity,
            inputs=inputs,
        ):
            return self._error_result("INVALID_PRICE_GRID", identity)

        rows = []
        common = {
            "identity": dict(identity or {}),
            "provenance": dict(provenance or {}),
            "sources": dict(sources or {}),
            "candidate_price_provenance": "manual_seller_assumption",
        }
        evaluation_count = 0
        rate_by_price = (
            {int(price * self.HUNDRED): rate for price, rate in zip(normalized_prices, normalized_rates)}
            if normalized_rates is not None else {}
        )
        advertising_basis = {
            "mode": normalized_advertising_mode,
            "origin": (
                common["provenance"].get("advertising_rate", "unknown")
                if normalized_advertising_mode == "SAME_DRR"
                else "MANUAL_SCENARIO_ASSUMPTION"
            ),
        }
        if normalized_advertising_mode == "SAME_DRR":
            advertising_basis.update({
                "revenue_basis": "SELLER_REVENUE",
                "rate": inputs.get("advertising_rate"),
            })
        elif normalized_advertising_mode == "PER_PRICE_DRR":
            advertising_basis.update({
                "revenue_basis": "SELLER_REVENUE",
                "rates": [format(rate, "f") for rate in normalized_rates],
                "price_order": [format(price, ".2f") for price in normalized_prices],
            })
        else:
            advertising_basis.update(normalized_cost_basis)

        def run_forward(candidate_inputs, candidate_provenance):
            nonlocal evaluation_count
            if evaluation_count >= self.MAX_COMPARISON_FORWARD_CALCULATIONS:
                return {"error": True, "available": False, "code": "SEARCH_BUDGET_EXHAUSTED"}
            evaluation_count += 1
            try:
                return self.scenario_service.calculate(
                    candidate_inputs,
                    identity=common["identity"],
                    provenance=self._candidate_provenance({
                        **common, "provenance": candidate_provenance,
                    }),
                    sources=common["sources"],
                )
            except (ArithmeticError, OverflowError, TypeError, ValueError):
                return None

        def evaluate(price, advertising_rate_override=None):
            cents = int(price * self.HUNDRED)
            candidate_inputs = dict(inputs)
            candidate_inputs["price"] = format(price, ".2f")
            candidate_provenance = dict(common["provenance"])
            if normalized_advertising_mode == "MANUAL_COST_PER_SUCCESSFUL_UNIT":
                candidate_inputs.pop("advertising_rate", None)
                candidate_inputs["advertising_mode"] = "ABSOLUTE_PER_SUCCESSFUL_UNIT"
                candidate_inputs["advertising_cost_per_unit"] = normalized_cost_basis["amount_per_unit"]
                candidate_ad_rate = None
            elif advertising_rate_override is not None:
                candidate_ad_rate = advertising_rate_override
            elif normalized_advertising_mode == "PER_PRICE_DRR":
                candidate_ad_rate = rate_by_price.get(cents)
            else:
                candidate_ad_rate = candidate_inputs.get("advertising_rate")
            if candidate_ad_rate is not None:
                normalized_rate = self._normalize_target(candidate_ad_rate)
                if not normalized_rate["valid"]:
                    return {
                        "status": "INVALID_ADVERTISING_RATE", "available": False,
                        "price": format(price, ".2f"), "profit": None,
                        "margin_percent": None, "tax": None, "goal_reached": None,
                        "commission_rate": candidate_inputs.get("commission_rate"),
                        "commission": None, "commission_status": "UNRESOLVED",
                        "commission_reason": "INVALID_ADVERTISING_RATE",
                        "commission_origin": candidate_provenance.get("commission_rate"),
                        "advertising_rate": None, "advertising_per_unit": None,
                        "advertising_basis": deepcopy(advertising_basis),
                        "missing_inputs": [], "invalid_inputs": ["advertising_rate"],
                        "forward_result": None,
                    }
                candidate_ad_rate = normalized_rate["value"]
                candidate_inputs["advertising_rate"] = format(candidate_ad_rate, "f")
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
                        "advertising_rate": candidate_inputs.get("advertising_rate"),
                        "advertising_per_unit": None,
                        "advertising_basis": deepcopy(advertising_basis),
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
                        "advertising_rate": candidate_inputs.get("advertising_rate"),
                        "advertising_per_unit": None,
                        "advertising_basis": deepcopy(advertising_basis),
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

            forward = run_forward(candidate_inputs, candidate_provenance)
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
                "advertising_rate": candidate_inputs.get("advertising_rate"),
                "advertising_per_unit": calculated.get("advertising") if available else None,
                "advertising_basis": deepcopy(advertising_basis),
                "cross_docking_included": (
                    forward.get("cross_docking_included") if isinstance(forward, dict) else None
                ),
                "cross_docking_status": (
                    forward.get("cross_docking_status") if isinstance(forward, dict) else None
                ),
                "cross_docking_reason": (
                    forward.get("cross_docking_reason") if isinstance(forward, dict) else None
                ),
                "cross_docking_per_unit": (
                    calculated.get("cross_docking") if available else None
                ),
                "missing_inputs": list((forward or {}).get("missing_inputs") or []),
                "invalid_inputs": list((forward or {}).get("invalid_inputs") or []),
                "forward_result": forward if available else None,
            }

        for price in normalized_prices:
            rows.append(evaluate(price))

        baseline_price = self._current_price_cents(inputs)
        baseline = None
        baseline_row = None
        if baseline_price is not None:
            baseline_decimal = self._price_from_cents(baseline_price)
            baseline_row = evaluate(
                baseline_decimal,
                advertising_rate_override=(
                    inputs.get("advertising_rate")
                    if normalized_advertising_mode != "MANUAL_COST_PER_SUCCESSFUL_UNIT"
                    else None
                ),
            )
            baseline = {
                "price": format(baseline_decimal, ".2f"),
                "status": baseline_row.get("status"),
                "available": baseline_row.get("available") is True,
                "profit": baseline_row.get("profit"),
                "margin_percent": baseline_row.get("margin_percent"),
                "commission_rate": baseline_row.get("commission_rate"),
                "commission_status": baseline_row.get("commission_status"),
                "advertising_rate": baseline_row.get("advertising_rate"),
                "advertising_per_unit": baseline_row.get("advertising_per_unit"),
                "evidence_basis": "SCENARIO_ASSUMPTIONS",
            }

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

        if baseline and baseline.get("available") is True and not grid_mode:
            baseline_profit = Decimal(str(baseline["profit"]))
            for row in rows:
                if row.get("available") is not True:
                    row["compensation_thresholds"] = {
                        "status": "CANDIDATE_UNAVAILABLE",
                        "non_worse": None,
                        "strictly_better": None,
                    }
                    continue
                row["profit_delta_vs_baseline"] = format(
                    Decimal(str(row["profit"])) - baseline_profit, ".2f"
                )
                if normalized_advertising_mode == "MANUAL_COST_PER_SUCCESSFUL_UNIT":
                    row["compensation_thresholds"] = {
                        "status": "FIXED_COST_BASIS_NOT_SOLVED",
                        "non_worse": None,
                        "strictly_better": None,
                    }
                    continue
                threshold_inputs = dict(inputs)
                threshold_inputs["price"] = row["price"]
                threshold_inputs["commission_rate"] = row.get("commission_rate")
                threshold_inputs["advertising_rate"] = inputs.get("advertising_rate")
                threshold_provenance = dict(common["provenance"])
                threshold_provenance["price"] = "manual_seller_assumption"
                threshold_provenance["commission_rate"] = {
                    "MANUAL_SELLER_ASSUMPTION": "manual_seller_assumption",
                    "CURRENT_PRICE_POINT": "current_price_point",
                    "CONFIRMED_OFFICIAL_SOURCE": "confirmed_official_source",
                }.get(row.get("commission_origin"), row.get("commission_origin") or "unknown")
                thresholds = self.advertising_compensation_service.solve(
                    threshold_inputs,
                    baseline_profit,
                    lambda candidate, candidate_provenance=threshold_provenance: run_forward(
                        candidate, candidate_provenance,
                    ),
                )
                row["compensation_thresholds"] = thresholds
        else:
            for row in rows:
                row["compensation_thresholds"] = {
                    "status": (
                        "DEFERRED_UNTIL_CANDIDATE_SELECTED"
                        if grid_mode and baseline and baseline.get("available") is True
                        else "BASELINE_UNAVAILABLE"
                    ),
                    "non_worse": None,
                    "strictly_better": None,
                }
        if grid_mode:
            boundary_prices = set(price_grid_metadata["tariff_boundary_prices"])
            for row in rows:
                row["is_tariff_boundary"] = row["price"] in boundary_prices
                # Grid results are kept compact; applying a chosen row performs
                # a fresh canonical forward validation instead of retaining a
                # full repeated source/input payload for up to 200 candidates.
                row.pop("forward_result", None)

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
                **advertising_basis,
            },
            "target_margin_percent": format(target, "f") if target is not None else None,
            "rows": rows,
            "candidate_count": len(rows),
            "evaluation_count": evaluation_count,
            "evaluation_limit": self.MAX_COMPARISON_FORWARD_CALCULATIONS,
            "identity": common["identity"],
            "provenance": self._candidate_provenance(common),
            "source_price_provenance": common["provenance"].get("price"),
            "sources": common["sources"],
            "price_grid": deepcopy(price_grid_metadata) if grid_mode else None,
            "global_optimum_claimed": False if grid_mode else None,
            "read_only": True,
            "executed": False,
        }

    def _tariff_search_segments(self, snapshot, identity):
        if snapshot is None:
            return {
                "covered_segments": [],
                "gaps": [{
                    "price_from_cents": self.MIN_PRICE_CENTS,
                    "price_to_cents": self.max_price_cents,
                    "reason": "NO_FROZEN_TARIFF_SNAPSHOT",
                }],
                "coverage_complete": False,
                "rule_count": 0,
                "scope": "COVERED_FROZEN_TARIFF_SEGMENTS",
            }
        profiles = snapshot.get("profiles") or []
        rule_count = sum(
            len(profile.get("bands") or [])
            for profile in profiles if isinstance(profile, dict)
        )
        if rule_count > self.MAX_PRICE_GRID_TARIFF_RULES:
            return {
                "error": True,
                "code": "TARIFF_RULE_LIMIT_EXCEEDED",
            }
        if snapshot.get("status") == "SOURCE_UNAVAILABLE":
            return {
                "status": "SOURCE_UNAVAILABLE",
                "covered_segments": [],
                "gaps": [{
                    "price_from_cents": self.MIN_PRICE_CENTS,
                    "price_to_cents": self.max_price_cents,
                    "reason": "TARIFF_SOURCE_UNAVAILABLE",
                }],
                "coverage_complete": False,
                "rule_count": rule_count,
                "scope": "COVERED_FROZEN_TARIFF_SEGMENTS",
            }

        cuts = {self.MIN_PRICE_CENTS, self.max_price_cents + 1}
        for profile in profiles:
            for band in profile.get("bands") or []:
                low = max(self.MIN_PRICE_CENTS, band["price_from_cents"])
                high = min(self.max_price_cents, band["price_to_cents"])
                if low <= high:
                    cuts.add(low)
                    cuts.add(high + 1)

        covered = []
        gaps = []
        ordered = sorted(cuts)
        for low, after_high in zip(ordered, ordered[1:]):
            high = after_high - 1
            if low > high:
                continue
            start = UnitPriceTariffSnapshotAdapter.resolve_frozen(snapshot, identity, low)
            end = UnitPriceTariffSnapshotAdapter.resolve_frozen(snapshot, identity, high)
            if start.get("error") is True or end.get("error") is True:
                return {"error": True, "code": "INVALID_TARIFF_SNAPSHOT"}
            start_profile = start.get("selected_profile") or {}
            end_profile = end.get("selected_profile") or {}
            start_key = (
                str(start.get("commission_rate")), start.get("status"),
                start_profile.get("profile_id"), start_profile.get("revision"),
                start_profile.get("state_revision"), start_profile.get("origin"),
            )
            end_key = (
                str(end.get("commission_rate")), end.get("status"),
                end_profile.get("profile_id"), end_profile.get("revision"),
                end_profile.get("state_revision"), end_profile.get("origin"),
            )
            if (start.get("available") is True and end.get("available") is True
                    and start_key == end_key):
                covered.append({
                    "price_from_cents": low,
                    "price_to_cents": high,
                    "commission_rate": str(start.get("commission_rate")),
                    "commission_origin": start_profile.get("origin") or "unknown",
                    "commission_status": start.get("status") or "UNKNOWN",
                })
                continue
            statuses = {start.get("status"), end.get("status")}
            if "SOURCE_UNAVAILABLE" in statuses:
                reason = "TARIFF_SOURCE_UNAVAILABLE"
            elif "CONFLICT" in statuses:
                reason = "TARIFF_PROFILE_CONFLICT"
            elif start_key != end_key and start.get("available") is True and end.get("available") is True:
                reason = "TARIFF_RESOLUTION_CHANGED_WITHIN_SEGMENT"
            elif "EXPIRED" in statuses:
                reason = "TARIFF_PROFILE_EXPIRED"
            elif "UNSUPPORTED_SCHEME" in statuses:
                reason = "TARIFF_SCHEME_UNSUPPORTED"
            else:
                reason = "COMMISSION_UNKNOWN"
            if gaps and gaps[-1]["reason"] == reason and gaps[-1]["price_to_cents"] + 1 == low:
                gaps[-1]["price_to_cents"] = high
            else:
                gaps.append({
                    "price_from_cents": low,
                    "price_to_cents": high,
                    "reason": reason,
                })

        covered_cents = sum(
            segment["price_to_cents"] - segment["price_from_cents"] + 1
            for segment in covered
        )
        return {
            "covered_segments": covered,
            "gaps": gaps,
            "coverage_complete": covered_cents == self.max_price_cents,
            "rule_count": rule_count,
            "scope": "MINIMUM_AMONG_COVERED_TARIFF_SEGMENTS",
        }

    def _public_tariff_search_metadata(self, search):
        def price_range(item):
            return {
                "from": format(self._price_from_cents(item["price_from_cents"]), ".2f"),
                "to": format(self._price_from_cents(item["price_to_cents"]), ".2f"),
            }

        return {
            "mode": "FROZEN_TARIFF_SEGMENTS",
            "scope": search.get("scope") or "MINIMUM_AMONG_COVERED_TARIFF_SEGMENTS",
            "rule_count": search.get("rule_count", 0),
            "rule_limit": self.MAX_PRICE_GRID_TARIFF_RULES,
            "covered_segment_count": len(search.get("covered_segments") or []),
            "covered_ranges": [
                {
                    **price_range(item),
                    "commission_rate": item.get("commission_rate"),
                    "origin": item.get("commission_origin"),
                }
                for item in search.get("covered_segments") or []
            ],
            "gaps": [
                {**price_range(item), "reason": item.get("reason")}
                for item in search.get("gaps") or []
            ],
            "coverage_complete": search.get("coverage_complete") is True,
            "global_minimum_claimed": False,
        }

    def _find_candidate_in_tariff_segments(
        self, inputs, target, call_state, common, segments, *,
        frozen_tariff_snapshot, tariff_identity, exact_price_rate_cents=None,
    ):
        for segment in segments:
            low = segment["price_from_cents"]
            high = segment["price_to_cents"]
            # Verify the idealized bound against canonical outputs at bounded
            # representative points. A custom/unsupported forward service must
            # not inherit this solver's proof silently.
            probe_points = sorted({low, (low + high) // 2, high})
            for cents in probe_points:
                probe, status, _resolution = self._evaluate_tariff_candidate(
                    inputs, cents, call_state, common,
                    frozen_tariff_snapshot=frozen_tariff_snapshot,
                    tariff_identity=tariff_identity,
                    exact_price_rate_cents=exact_price_rate_cents,
                )
                if status == "SEARCH_BUDGET_EXHAUSTED":
                    return self._unavailable_outcome("SEARCH_BUDGET_EXHAUSTED")
                if status != "CALCULATED":
                    return self._unavailable_outcome(status, probe)
                expected_gap = self._ideal_target_gap_upper_bound(
                    inputs, target, segment.get("commission_rate"), cents, cents,
                )
                price = self._price_from_cents(cents)
                try:
                    actual_gap = (
                        Decimal(str(probe["calculated"]["profit"]))
                        - target * price / self.HUNDRED
                    )
                except (KeyError, InvalidOperation, TypeError, ValueError):
                    expected_gap = None
                    actual_gap = None
                if (expected_gap is None or actual_gap is None
                        or abs(actual_gap - expected_gap) > self.ROUNDING_GAP_BOUND):
                    outcome = self._unavailable_outcome("NON_MONOTONIC_SEGMENT")
                    outcome["segment"] = {
                        "price_from_cents": low, "price_to_cents": high,
                    }
                    return outcome
            search = self._search_first_tariff_candidate(
                inputs, target, call_state, common, low, high,
                commission_rate=segment.get("commission_rate"),
                frozen_tariff_snapshot=frozen_tariff_snapshot,
                tariff_identity=tariff_identity,
                exact_price_rate_cents=exact_price_rate_cents,
            )
            if search["status"] == "BUDGET_EXHAUSTED":
                return self._unavailable_outcome("SEARCH_BUDGET_EXHAUSTED")
            if search["status"] == "UNAVAILABLE":
                outcome = self._unavailable_outcome(
                    search.get("reason") or "NON_MONOTONIC_SEGMENT",
                    search.get("forward"),
                )
                outcome["segment"] = {
                    "price_from_cents": low, "price_to_cents": high,
                }
                return outcome
            if search["status"] == "NOT_FOUND":
                continue
            candidate_cents = search["cents"]
            forward = search["forward"]
            resolution = search["resolution"]
            outcome = self._success_outcome(
                self._price_from_cents(candidate_cents), forward, target,
            )
            selected_profile = (resolution or {}).get("selected_profile") or {}
            outcome.update({
                "commission_rate": str((resolution or {}).get("commission_rate")
                                       or segment.get("commission_rate")),
                "commission_origin": (
                    selected_profile.get("origin")
                    or segment.get("commission_origin") or "unknown"
                ),
                "commission_status": (
                    (resolution or {}).get("status")
                    or segment.get("commission_status") or "UNKNOWN"
                ),
                "commission": (forward.get("calculated") or {}).get("commission"),
                "segment": {
                    "price_from_cents": low,
                    "price_to_cents": high,
                },
            })
            return outcome
        return self._unavailable_outcome("NOT_FOUND_IN_COVERED_SEGMENTS")

    def _search_first_tariff_candidate(
        self, inputs, target, call_state, common, low, high, *, commission_rate,
        frozen_tariff_snapshot, tariff_identity, exact_price_rate_cents=None,
    ):
        """Find the first reached cent using a conservative rounded-profit bound.

        The continuous profit gap is the minimum of at most three affine lines
        for supported tax modes. Its maximum over any interval is attained at
        an endpoint or a line intersection. If that maximum is below the
        canonical forward calculation's rounding-error bound, the interval is
        provably infeasible and can be skipped. Remaining intervals are split
        left-first and verified at individual cents; budget exhaustion fails
        closed instead of claiming a non-minimal price.
        """
        upper_gap = self._ideal_target_gap_upper_bound(
            inputs, target, commission_rate, low, high,
        )
        if upper_gap is None:
            return {"status": "UNAVAILABLE", "reason": "ROUNDING_BOUND_UNAVAILABLE"}
        if upper_gap < -self.ROUNDING_GAP_BOUND:
            return {"status": "NOT_FOUND"}
        if low == high:
            forward, status, resolution = self._evaluate_tariff_candidate(
                inputs, low, call_state, common,
                frozen_tariff_snapshot=frozen_tariff_snapshot,
                tariff_identity=tariff_identity,
                exact_price_rate_cents=exact_price_rate_cents,
            )
            if status == "SEARCH_BUDGET_EXHAUSTED":
                return {"status": "BUDGET_EXHAUSTED"}
            if status != "CALCULATED":
                return {"status": "UNAVAILABLE", "reason": status, "forward": forward}
            if self._reached(forward, self._price_from_cents(low), target):
                return {
                    "status": "FOUND", "cents": low,
                    "forward": forward, "resolution": resolution,
                }
            return {"status": "NOT_FOUND"}

        middle = (low + high) // 2
        left = self._search_first_tariff_candidate(
            inputs, target, call_state, common, low, middle,
            commission_rate=commission_rate,
            frozen_tariff_snapshot=frozen_tariff_snapshot,
            tariff_identity=tariff_identity,
            exact_price_rate_cents=exact_price_rate_cents,
        )
        if left["status"] != "NOT_FOUND":
            return left
        return self._search_first_tariff_candidate(
            inputs, target, call_state, common, middle + 1, high,
            commission_rate=commission_rate,
            frozen_tariff_snapshot=frozen_tariff_snapshot,
            tariff_identity=tariff_identity,
            exact_price_rate_cents=exact_price_rate_cents,
        )

    def _ideal_target_gap_upper_bound(
        self, inputs, target, commission_rate, low_cents, high_cents,
    ):
        """Return a conservative maximum continuous gap in [low, high]."""
        def decimal(name, default=None):
            raw = inputs.get(name, default)
            if raw is None or raw == "" or isinstance(raw, bool):
                return None
            try:
                result = Decimal(str(raw).strip().replace(",", "."))
            except (InvalidOperation, TypeError, ValueError):
                return None
            return result if result.is_finite() else None

        if commission_rate is None:
            commission = decimal("commission_rate")
        else:
            try:
                commission = Decimal(str(commission_rate))
            except (InvalidOperation, TypeError, ValueError):
                commission = None
        advertising = decimal("advertising_rate")
        points = decimal("discount_points_rate")
        cost = decimal("cost")
        logistics = decimal("logistics_per_unit")
        last_mile = decimal("last_mile_per_unit")
        acquiring = decimal("acquiring_per_unit")
        cross_docking = decimal("cross_docking_per_unit", "0")
        if cross_docking is None and inputs.get("cross_docking_per_unit") in (None, ""):
            cross_docking = Decimal("0")
        if any(value is None for value in (
            commission, advertising, points, cost, logistics, last_mile,
            acquiring, cross_docking,
        )):
            return None
        if any(value < 0 or value > self.HUNDRED for value in (
            commission, advertising, points,
        )):
            return None
        fees = (logistics + last_mile + acquiring).quantize(
            self.CENT, rounding=ROUND_HALF_UP,
        )
        base_slope = (
            Decimal("1") - commission / self.HUNDRED
            - advertising / self.HUNDRED
        )
        base_intercept = -(fees + cost + cross_docking)
        target_rate = target / self.HUNDRED
        lines = [(
            base_slope - target_rate,
            base_intercept,
        )]
        tax_mode = str(inputs.get("tax_mode") or "").strip().upper()
        if tax_mode == "USN_INCOME":
            tax_rate = decimal("tax_rate")
            if tax_rate is None or not Decimal("0") <= tax_rate <= self.HUNDRED:
                return None
            lines = [(
                base_slope - target_rate
                - (Decimal("1") - points / self.HUNDRED)
                * tax_rate / self.HUNDRED,
                base_intercept,
            )]
        elif tax_mode == "USN_INCOME_MINUS_EXPENSES":
            tax_rate = decimal("tax_rate")
            minimum_tax_rate = decimal("minimum_tax_rate")
            if any(value is None or not Decimal("0") <= value <= self.HUNDRED
                   for value in (tax_rate, minimum_tax_rate)):
                return None
            regular_base_slope = base_slope - points / self.HUNDRED
            regular_rate = tax_rate / self.HUNDRED
            minimum_rate = minimum_tax_rate / self.HUNDRED
            lines = [
                (base_slope - target_rate, base_intercept),
                (
                    base_slope - target_rate - regular_base_slope * regular_rate,
                    base_intercept * (Decimal("1") - regular_rate),
                ),
                (
                    base_slope - target_rate
                    - (Decimal("1") - points / self.HUNDRED) * minimum_rate,
                    base_intercept,
                ),
            ]
        elif tax_mode != "NONE":
            return None

        low = Decimal(low_cents) / self.HUNDRED
        high = Decimal(high_cents) / self.HUNDRED
        candidates = {low, high}
        for index, (slope, intercept) in enumerate(lines):
            for other_slope, other_intercept in lines[index + 1:]:
                denominator = slope - other_slope
                if denominator == 0:
                    continue
                crossing = (other_intercept - intercept) / denominator
                if low < crossing < high:
                    candidates.add(crossing)
        return max(
            min(slope * price + intercept for slope, intercept in lines)
            for price in candidates
        )

    def _evaluate_tariff_candidate(
        self, inputs, cents, call_state, common, *, frozen_tariff_snapshot,
        tariff_identity, exact_price_rate_cents=None, bypass_cache=False,
    ):
        cache = call_state.setdefault("tariff_cache", {})
        if not bypass_cache and cents in cache:
            return cache[cents]
        price = self._price_from_cents(cents)
        if frozen_tariff_snapshot is not None:
            resolution = UnitPriceTariffSnapshotAdapter.resolve_frozen(
                frozen_tariff_snapshot, tariff_identity, cents,
            )
            if resolution.get("error") is True:
                return None, "INVALID_TARIFF_SNAPSHOT", resolution
            if resolution.get("available") is not True:
                status = ("SOURCE_UNAVAILABLE"
                         if resolution.get("status") == "SOURCE_UNAVAILABLE"
                         else "COMMISSION_UNKNOWN")
                return None, status, resolution
            selected_profile = resolution.get("selected_profile") or {}
            commission_origin = selected_profile.get("origin") or "unknown"
            commission_status = resolution.get("status") or "UNKNOWN"
            rate = resolution.get("commission_rate")
        else:
            if (exact_price_rate_cents is None or cents != exact_price_rate_cents
                    or self._current_price_cents(inputs) != exact_price_rate_cents):
                return None, "COMMISSION_UNKNOWN", None
            rate = inputs.get("commission_rate")
            commission_origin = "legacy_frozen_plan_rate"
            commission_status = "LEGACY_EXACT_PRICE_ONLY"
            resolution = {
                "available": True,
                "commission_rate": rate,
                "status": commission_status,
                "selected_profile": {"origin": commission_origin},
            }
        if call_state["count"] >= call_state.get(
            "limit", self.MAX_FORWARD_CALCULATIONS,
        ):
            return None, "SEARCH_BUDGET_EXHAUSTED", resolution
        candidate_inputs = dict(inputs)
        candidate_inputs["price"] = format(price, ".2f")
        candidate_inputs["commission_rate"] = rate
        candidate_provenance = dict(common["provenance"])
        candidate_provenance["price"] = common["candidate_price_provenance"]
        candidate_provenance["commission_rate"] = {
            "MANUAL_SELLER_ASSUMPTION": "manual_seller_assumption",
            "CURRENT_PRICE_POINT": "current_price_point",
            "CONFIRMED_OFFICIAL_SOURCE": "confirmed_official_source",
        }.get(commission_origin, commission_origin)
        call_state["count"] += 1
        try:
            forward = self.scenario_service.calculate(
                candidate_inputs,
                identity=common["identity"],
                provenance=candidate_provenance,
                sources=common["sources"],
            )
        except (ArithmeticError, OverflowError, TypeError, ValueError):
            forward = None
        status = self._forward_status(forward)
        item = (forward, status, resolution)
        if not bypass_cache:
            cache[cents] = item
        return item

    def _verify_tariff_candidate(
        self, outcome, target, inputs, call_state, common,
        frozen_tariff_snapshot, tariff_identity, exact_price_rate_cents,
    ):
        cents = int(Decimal(outcome["price"]) * self.HUNDRED)
        forward, status, resolution = self._evaluate_tariff_candidate(
            inputs, cents, call_state, common,
            frozen_tariff_snapshot=frozen_tariff_snapshot,
            tariff_identity=tariff_identity,
            exact_price_rate_cents=exact_price_rate_cents,
            bypass_cache=True,
        )
        if status != "CALCULATED" or not self._reached(
            forward, self._price_from_cents(cents), target,
        ):
            outcome.update(self._unavailable_outcome(
                "SEARCH_BUDGET_EXHAUSTED"
                if status == "SEARCH_BUDGET_EXHAUSTED" else "FINAL_CHECK_FAILED",
                forward,
            ))
            return
        segment = outcome.get("segment") or {}
        previous_cents = cents - 1
        previous_status = "OUTSIDE_COVERED_SEGMENT"
        previous_goal_reached = None
        if previous_cents >= segment.get("price_from_cents", cents):
            previous, previous_status, _ = self._evaluate_tariff_candidate(
                inputs, previous_cents, call_state, common,
                frozen_tariff_snapshot=frozen_tariff_snapshot,
                tariff_identity=tariff_identity,
                exact_price_rate_cents=exact_price_rate_cents,
                bypass_cache=True,
            )
            if previous_status != "CALCULATED":
                outcome.update(self._unavailable_outcome(
                    "SEARCH_BUDGET_EXHAUSTED"
                    if previous_status == "SEARCH_BUDGET_EXHAUSTED" else "FINAL_CHECK_FAILED",
                    previous,
                ))
                return
            previous_goal_reached = self._reached(
                previous, self._price_from_cents(previous_cents), target,
            )
            if previous_goal_reached:
                outcome.update(self._unavailable_outcome("FINAL_CHECK_FAILED", previous))
                return
        verified = self._success_outcome(self._price_from_cents(cents), forward, target)
        outcome.update(verified)
        outcome.update({
            "commission_rate": resolution.get("commission_rate"),
            "commission_origin": (
                (resolution.get("selected_profile") or {}).get("origin")
                or outcome.get("commission_origin")
            ),
            "commission_status": resolution.get("status") or outcome.get("commission_status"),
            "commission": (forward.get("calculated") or {}).get("commission"),
            "segment": segment,
            "previous_cent_check": previous_status,
            "previous_cent_goal_reached": previous_goal_reached,
        })

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
        if call_state["count"] >= call_state.get(
            "limit", self.MAX_FORWARD_CALCULATIONS,
        ):
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

    def _validate_price_values(self, prices, max_prices=None):
        limit = self.MAX_COMPARISON_PRICES if max_prices is None else max_prices
        if not isinstance(prices, (list, tuple)) or not 2 <= len(prices) <= limit:
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

    def _valid_price_grid_metadata(
        self, metadata, normalized_prices, *, frozen_tariff_snapshot=None,
        identity=None, inputs=None,
    ):
        required = {
            "price_basis", "start", "end", "step", "base_grid_count",
            "tariff_rule_count", "tariff_rule_limit", "tariff_source_status",
            "tariff_boundary_prices", "inserted_tariff_boundary_prices",
            "candidate_count", "candidate_limit", "searched_prices",
            "global_optimum_claimed",
        }
        if not isinstance(metadata, dict) or set(metadata) != required:
            return False
        if (metadata.get("price_basis") != "SELLER_PRICE_RUB"
                or metadata.get("global_optimum_claimed") is not False
                or metadata.get("candidate_limit") != self.MAX_PRICE_GRID_CANDIDATES
                or metadata.get("tariff_rule_limit") != self.MAX_PRICE_GRID_TARIFF_RULES
                or metadata.get("candidate_count") != len(normalized_prices)
                or metadata.get("searched_prices") != [
                    format(value, ".2f") for value in normalized_prices
                ]):
            return False
        start = self._parse_price_token(metadata.get("start", ""))
        end = self._parse_price_token(metadata.get("end", ""))
        step = self._parse_price_token(metadata.get("step", ""))
        if (start is None or end is None or step is None or start >= end or step <= 0
                or normalized_prices[0] != start or normalized_prices[-1] != end
                or normalized_prices != sorted(normalized_prices)):
            return False
        base_count = metadata.get("base_grid_count")
        rule_count = metadata.get("tariff_rule_count")
        if (type(base_count) is not int or not 1 <= base_count <= len(normalized_prices)
                or type(rule_count) is not int
                or not 0 <= rule_count <= self.MAX_PRICE_GRID_TARIFF_RULES
                or not isinstance(metadata.get("tariff_source_status"), str)
                or len(metadata["tariff_source_status"]) > 48):
            return False
        boundary_prices = metadata.get("tariff_boundary_prices")
        inserted_prices = metadata.get("inserted_tariff_boundary_prices")
        if (not isinstance(boundary_prices, list) or len(boundary_prices) > 80
                or not isinstance(inserted_prices, list) or len(inserted_prices) > 80):
            return False
        normalized_boundary = []
        for collection in (boundary_prices, inserted_prices):
            values = []
            for value in collection:
                price = self._parse_price_token(value) if isinstance(value, str) else None
                if (price is None or format(price, ".2f") not in metadata["searched_prices"]
                        or price < start or price > end):
                    return False
                values.append(format(price, ".2f"))
            if len(values) != len(set(values)):
                return False
            normalized_boundary.append(set(values))
        if not normalized_boundary[1].issubset(normalized_boundary[0]):
            return False
        rebuilt = self.build_price_grid(
            ";".join((metadata["start"], metadata["end"], metadata["step"])),
            frozen_tariff_snapshot=frozen_tariff_snapshot,
            identity=identity,
            inputs=inputs,
        )
        return (
            rebuilt.get("valid") is True
            and rebuilt.get("normalized") == metadata["searched_prices"]
            and rebuilt.get("metadata") == metadata
            and [format(value, ".2f") for value in normalized_prices]
            == rebuilt.get("normalized")
        )

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
