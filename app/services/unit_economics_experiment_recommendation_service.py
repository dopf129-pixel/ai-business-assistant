"""Explain persisted experiment comparisons and rank only measured candidates."""

import json
from decimal import Decimal

from services.planning_unit_economics_experiment_adapter import (
    PlanningUnitEconomicsExperimentAdapter,
)


class UnitEconomicsExperimentRecommendationService:
    """Build safe, deterministic recommendations from stored result snapshots."""

    MAX_CANDIDATES = 10
    _EVALUATED_OUTCOMES = frozenset({
        "NO_CLEAR_DIFFERENCE", "CANDIDATE_BETTER_IN_MODEL", "BASELINE_BETTER_IN_MODEL",
    })
    _REASON_CODES = frozenset({
        "STRICT_RETAINED_COHORT_DISPOSITION_UNAVAILABLE",
        "PHASE_WINDOWS_OVERLAP_OR_REVERSED", "SOURCE_AS_OF_INVALID",
        "SOURCE_AS_OF_MATURITY_DIFFERS", "TIMEZONE_OR_WINDOW_INVALID",
        "WINDOW_DATA_INVALID", "WINDOW_DURATION_OR_WEEKDAY_COVERAGE_DIFFERS",
        "COST_OR_EXPENSE_SNAPSHOT_CHANGED", "PHASE_CONTROL_FLAGS_DIFFER",
        "PHASE_CONTROL_FLAGS_CHANGED_OR_UNKNOWN", "PHASE_NOT_MATURE_AND_READY",
        "PHASE_CONTROL_CONDITIONS_NOT_CONFIRMED", "SOLD_UNIT_DENOMINATOR_UNCONFIRMED",
        "FROZEN_PLAN_UNAVAILABLE", "FROZEN_COST_OR_TAX_INPUTS_UNAVAILABLE",
        "PHASE_FINANCIAL_OR_UNIT_DATA_INCOMPLETE", "RETURNED_UNIT_DISPOSITION_UNKNOWN",
        "BASELINE_AND_CANDIDATE_PRICE_ARE_EQUAL",
    })
    _MESSAGES = {
        "CONTINUE_COLLECTING": (
            "CONTINUE_COLLECTING",
            "Данных пока недостаточно для зрелого сравнения.",
            "Дождитесь завершения окна и повторите сбор фактов.",
        ),
        "FIX_DATA_OR_CONDITIONS": (
            "FIX_DATA_OR_CONDITIONS",
            "Сначала нужно исправить данные или стабилизировать условия.",
            "Устраните указанные причины, затем соберите новый снимок.",
        ),
        "INCOMPARABLE": (
            "INCOMPARABLE",
            "Эти фазы нельзя надёжно сравнить по текущим данным.",
            "Исправьте несовместимые условия или завершите сопоставимые фазы.",
        ),
        "NO_CLEAR_DIFFERENCE": (
            "NO_CLEAR_DIFFERENCE",
            "Расчётная разница не достигла заранее установленного порога.",
            "Не считайте цены различающимися по прибыли; решение остаётся за владельцем.",
        ),
        "CANDIDATE_BETTER_IN_MODEL": (
            "CANDIDATE_BETTER_IN_MODEL",
            "У проверенной цены кандидата выше расчётная прибыль на единицу.",
            "Сравните кандидата с другими оценёнными вариантами и решите вручную.",
        ),
        "BASELINE_BETTER_IN_MODEL": (
            "BASELINE_BETTER_IN_MODEL",
            "У базовой цены выше расчётная прибыль на единицу.",
            "Сохраните это как результат модели; автоматического изменения цены нет.",
        ),
    }

    @classmethod
    def explain_result(cls, payload, *, evaluated_candidates=None):
        normalized = PlanningUnitEconomicsExperimentAdapter.normalize_result(payload)
        if normalized is None:
            return cls._error("EXPERIMENT_RECOMMENDATION_RESULT_INVALID")
        outcome = normalized["outcome"]
        title, explanation, next_step = cls._MESSAGES[outcome]
        reasons = sorted({
            (item["reason_code"] if item["reason_code"] in cls._REASON_CODES
             else "UNRECOGNIZED_QUALITY_REASON") for item in normalized["quality_gates"]
            if item["status"] in {"FAIL", "UNKNOWN", "WARNING"}
        })[:16]
        comparison = normalized.get("comparison")
        if comparison is not None:
            if outcome == "NO_CLEAR_DIFFERENCE":
                explanation += (
                    f" Дельта: {normalized['delta_profit_per_unit_rub']} ₽/шт.; "
                    f"порог: {comparison['decision_threshold_rub']} ₽/шт."
                )
            elif outcome in {"CANDIDATE_BETTER_IN_MODEL", "BASELINE_BETTER_IN_MODEL"}:
                explanation += (
                    f" База: {normalized['baseline_profit_per_unit_rub']} ₽/шт.; "
                    f"кандидат: {normalized['candidate_profit_per_unit_rub']} ₽/шт.; "
                    f"дельта: {normalized['delta_profit_per_unit_rub']} ₽/шт."
                )
        ranking = cls.rank_evaluated_candidates(evaluated_candidates or [])
        if ranking.get("status") == "RANKED":
            next_step += (
                f" Максимум среди {ranking['evaluated_candidate_count']} совместимых "
                "оценённых кандидатов показан отдельно; это не доказательство причинности."
            )
        return {
            "schema_version": 1, "outcome": outcome,
            "recommendation_code": title, "explanation": explanation,
            "next_step": next_step, "reason_codes": reasons,
            "limitations": list(normalized["limitations"]),
            "baseline_profit_per_unit_rub": normalized["baseline_profit_per_unit_rub"],
            "candidate_profit_per_unit_rub": normalized["candidate_profit_per_unit_rub"],
            "delta_profit_per_unit_rub": normalized["delta_profit_per_unit_rub"],
            "candidate_ranking": ranking,
            "decision_options": cls._decision_options(outcome),
            "read_only": True, "changes_ozon_price": False,
        }

    @classmethod
    def rank_evaluated_candidates(cls, candidates):
        if not isinstance(candidates, list) or len(candidates) > cls.MAX_CANDIDATES:
            return {"status": "UNAVAILABLE", "reason_code": "CANDIDATE_SET_INVALID"}
        valid = []
        seen = set()
        for item in candidates:
            if (not isinstance(item, dict) or set(item) != {
                    "phase_id", "result_revision", "latest_result_revision", "payload",
            } or not isinstance(item.get("phase_id"), str)
                    or len(item["phase_id"]) != 32
                    or any(ch not in "0123456789abcdef" for ch in item["phase_id"])
                    or type(item.get("result_revision")) is not int
                    or not 1 <= item["result_revision"] <= 20
                    or type(item.get("latest_result_revision")) is not int
                    or not 1 <= item["latest_result_revision"] <= 20):
                return {"status": "UNAVAILABLE", "reason_code": "CANDIDATE_SET_INVALID"}
            if item["result_revision"] != item["latest_result_revision"]:
                continue
            if item["phase_id"] in seen:
                return {"status": "UNAVAILABLE", "reason_code": "CANDIDATE_SET_INVALID"}
            seen.add(item["phase_id"])
            result = PlanningUnitEconomicsExperimentAdapter.normalize_result(item["payload"])
            if result is None or result["outcome"] not in cls._EVALUATED_OUTCOMES:
                continue
            comparison = result.get("comparison")
            if comparison is None or result["candidate_profit_per_unit_rub"] is None:
                continue
            phase = comparison["candidate"]
            valid.append({
                "phase_id": item["phase_id"], "result_revision": item["result_revision"],
                "profit": Decimal(result["candidate_profit_per_unit_rub"]),
                "price_cents": phase["seller_price_cents"],
                "signature": cls._comparison_signature(result),
            })
        if not valid:
            return {
                "status": "NO_EVALUATED_CANDIDATES", "reason_code": "NO_COMPARABLE_CANDIDATES",
                "evaluated_candidate_count": 0, "excluded_candidate_count": len(candidates),
                "scope": "EVALUATED_COMPARABLE_CANDIDATES_ONLY",
            }
        signatures = {item["signature"] for item in valid}
        if len(signatures) != 1:
            return {
                "status": "INCOMPARABLE_CANDIDATE_BASES",
                "reason_code": "CANDIDATE_BASELINES_DIFFER",
                "evaluated_candidate_count": len(valid),
                "excluded_candidate_count": len(candidates) - len(valid),
                "scope": "EVALUATED_COMPARABLE_CANDIDATES_ONLY",
            }
        maximum = max(item["profit"] for item in valid)
        ranked = sorted(valid, key=lambda item: (-item["profit"], item["phase_id"]))
        return {
            "status": "RANKED", "reason_code": "MAXIMUM_OF_EVALUATED_CANDIDATES",
            "evaluated_candidate_count": len(valid),
            "excluded_candidate_count": len(candidates) - len(valid),
            "best_phase_ids": sorted(item["phase_id"] for item in valid if item["profit"] == maximum),
            "maximum_profit_per_unit_rub": format(maximum, ".2f"),
            "candidates": [{
                "phase_id": item["phase_id"], "result_revision": item["result_revision"],
                "seller_price_cents": item["price_cents"],
                "profit_per_unit_rub": format(item["profit"], ".2f"),
            } for item in ranked],
            "scope": "EVALUATED_COMPARABLE_CANDIDATES_ONLY",
        }

    @staticmethod
    def _comparison_signature(result):
        comparison = result["comparison"]
        baseline = comparison["baseline"]
        return json.dumps({
            "baseline_collection_hash": comparison["baseline_collection_hash"],
            "baseline_readiness_revision": comparison["baseline_readiness_revision"],
            "baseline_phase_state_revision": comparison["baseline_phase_state_revision"],
            "baseline": baseline,
            "profit_basis": comparison["profit_basis"],
            "threshold": comparison["decision_threshold_rub"],
            "shared_snapshot_refs": sorted(set(result["snapshot_refs"])
                                            - {comparison["candidate_collection_hash"]}),
        }, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _decision_options(outcome):
        if outcome in {"CONTINUE_COLLECTING", "FIX_DATA_OR_CONDITIONS", "INCOMPARABLE"}:
            return ["CONTINUE_TEST", "STOP_WITHOUT_PRICE_CHANGE"]
        return [
            "KEEP_BASELINE_PRICE", "SELECT_EVALUATED_CANDIDATE",
            "CONTINUE_TEST", "STOP_WITHOUT_PRICE_CHANGE",
        ]

    @staticmethod
    def _error(code):
        return {"error": True, "code": code}
