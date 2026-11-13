"""Deterministic, read-only requirements for a late FIFO transition.

The result is a review queue, not a proof of readiness.  It never changes a
case state, synthesizes source coverage, or enables FIFO application.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from services.fifo_cost_transition_contracts import (
    EvidenceCompleteness,
    PeriodProvenance,
    ScopeIdentity,
    TransitionCase,
    TransitionState,
)
from services.fifo_cost_transition_opening_proposal_service import (
    FifoCostTransitionOpeningProposal,
)
from services.fifo_cost_cutoff_bridge_service import FifoCutoffBridgeResult
from services.fifo_cost_transition_supply_reconciliation_service import (
    FifoCostTransitionSupplyReconciliation,
)


@dataclass(frozen=True, slots=True)
class FifoReadinessEvidenceRef:
    """Safe, compact reference to evidence already saved for this case."""

    source_type: str
    fingerprint: str | None
    captured_at: str | None
    source_as_of: str | None
    period_from: str | None
    period_to: str | None
    period_provenance: str | None
    saved_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FifoMissingRequirement:
    code: str
    status: str
    required_document_or_action: str
    required_fields: tuple[str, ...]
    required_period: tuple[str, str] | None
    already_saved: tuple[FifoReadinessEvidenceRef, ...]
    known_values: Mapping[str, object]
    explanation: str
    blocks_apply: bool

    def __post_init__(self):
        if self.status not in {"MISSING", "NEEDS_CONFIRMATION", "CONFLICT"}:
            raise ValueError("FIFO_READINESS_INPUT_INVALID")
        if type(self.blocks_apply) is not bool:
            raise ValueError("FIFO_READINESS_INPUT_INVALID")
        object.__setattr__(self, "required_fields", tuple(self.required_fields))
        object.__setattr__(self, "already_saved", tuple(self.already_saved))
        object.__setattr__(self, "known_values", _freeze_mapping(self.known_values))


@dataclass(frozen=True, slots=True)
class FifoCostTransitionReadiness:
    status: str
    scope: ScopeIdentity
    case_id: str
    case_revision: int
    cutoff_date: str | None
    case_state_before: str
    case_state_after: str
    requirements: tuple[FifoMissingRequirement, ...]
    source_data_through: str | None
    candidate_data_through: str | None
    complete_through: str | None
    ready_to_apply: bool
    preview_only: bool
    is_atomic_snapshot: bool


class FifoCostTransitionReadinessService:
    """Build a stable owner-action queue from the saved proposal and evidence."""

    MAX_REQUIREMENTS = 32
    MAX_EVIDENCE_REFS = 500

    _CONFLICT_CODES = frozenset({
        "ACCEPTANCE_BINDING_CONFLICT",
        "ACCEPTANCE_RECONCILIATION_CONFLICT",
        "OWNER_API_DECLARATION_MISMATCH",
        "OWNER_ACCEPTANCE_DECLARATION_MISMATCH",
        "SUPPLY_DECLARATION_CONFLICT",
        "SUPPLY_OBSERVATION_CONFLICT",
        "STOCK_REPORT_SCOPE_CONFLICT",
        "DECLARATIONS_EXCEED_OWNER_TOTAL",
    })

    def assess(
        self,
        *,
        case: TransitionCase,
        proposal: FifoCostTransitionOpeningProposal,
        supply_reconciliation: FifoCostTransitionSupplyReconciliation | None,
        cutoff_bridge: FifoCutoffBridgeResult | None = None,
    ) -> FifoCostTransitionReadiness:
        if (
            not isinstance(case, TransitionCase)
            or not isinstance(proposal, FifoCostTransitionOpeningProposal)
            or proposal.scope != case.metadata.scope
            or proposal.case_id != case.case_id
            or proposal.case_revision != case.case_revision
            or (
                supply_reconciliation is not None
                and (
                    not isinstance(supply_reconciliation, FifoCostTransitionSupplyReconciliation)
                    or supply_reconciliation.scope != case.metadata.scope
                    or supply_reconciliation.case_id != case.case_id
                )
            )
            or (
                cutoff_bridge is not None
                and (
                    not isinstance(cutoff_bridge, FifoCutoffBridgeResult)
                    or cutoff_bridge.scope != case.metadata.scope
                    or cutoff_bridge.case_id != case.case_id
                    or cutoff_bridge.case_revision != case.case_revision
                    or cutoff_bridge.cutoff_date != proposal.confirmed_cutoff_date
                )
            )
        ):
            raise ValueError("FIFO_READINESS_INPUT_INVALID")

        requirements: dict[str, FifoMissingRequirement] = {}

        def add(requirement: FifoMissingRequirement) -> None:
            existing = requirements.get(requirement.code)
            if existing is None:
                requirements[requirement.code] = requirement
            elif requirement.status == "CONFLICT" and existing.status != "CONFLICT":
                requirements[requirement.code] = requirement

        declarations = (
            supply_reconciliation.declarations if supply_reconciliation is not None else ()
        )
        owner_total = case.declared_shipped_units
        if supply_reconciliation is not None:
            owner_total = supply_reconciliation.owner_declared_total
            if owner_total is None:
                owner_total = case.declared_shipped_units
        listed_total = (
            supply_reconciliation.known_declared_total
            if supply_reconciliation is not None else 0
        )
        unassigned = (
            supply_reconciliation.owner_undistributed_units
            if supply_reconciliation is not None else owner_total
        )
        unknown_declarations = (
            supply_reconciliation.declarations_with_unknown_quantity
            if supply_reconciliation is not None else 0
        )
        manifest_incomplete = (
            supply_reconciliation is None
            or owner_total is None
            or not declarations
            or unassigned not in (None, 0)
            or unknown_declarations > 0
        )
        if manifest_incomplete:
            saved = tuple(
                FifoReadinessEvidenceRef(
                    source_type="SUPPLY_DECLARATION",
                    fingerprint=item.observed_source_fingerprint,
                    captured_at=item.observed_at,
                    source_as_of=item.observed_source_as_of,
                    period_from=item.dispatch_date,
                    period_to=item.dispatch_date,
                    period_provenance="OWNER_INPUT",
                    saved_fields=tuple(name for name, value in (
                        ("declared_quantity", item.declared_quantity),
                        ("dispatch_date", item.dispatch_date),
                        ("observed_status", item.observed_status.value if item.observed_status else None),
                        ("accepted_quantity", item.accepted_quantity),
                    ) if value is not None),
                )
                for item in declarations[:self.MAX_EVIDENCE_REFS]
            )
            add(FifoMissingRequirement(
                code="SUPPLY_MANIFEST_INCOMPLETE",
                status="CONFLICT" if (
                    supply_reconciliation is not None
                    and self._has_conflict(supply_reconciliation)
                ) else "MISSING",
                required_document_or_action=(
                    "Список всех поставок этого SKU: отдельная строка на каждую поставку"
                ),
                required_fields=(
                    "идентификатор поставки или заявки", "количество", "дата отгрузки",
                    "статус/акт приёмки, если доступны",
                ),
                required_period=None,
                already_saved=saved,
                known_values=MappingProxyType({
                    "owner_declared_total": owner_total,
                    "listed_declared_total": listed_total,
                    "unassigned_units": unassigned,
                    "unknown_quantity_declarations": unknown_declarations,
                }),
                explanation=(
                    "Общее количество не распределено по конкретным поставкам. "
                    "Арифметический остаток не считается отдельной поставкой или приёмкой."
                ),
                blocks_apply=True,
            ))

        stock_refs = tuple(
            self._report_ref("STOCK_MANAGEMENT", snapshot)
            for snapshot in proposal.stock_snapshots
        )
        stock_gaps = []
        stock_conflict = False
        for snapshot in proposal.stock_snapshots:
            reserved = snapshot.stock_buckets.get("reserved")
            overlap_confirmed = snapshot.fbs_return_is_subset_of_available is True
            if reserved is None or not overlap_confirmed:
                stock_gaps.append(MappingProxyType({
                    "fingerprint": snapshot.report_fingerprint,
                    "reserved": reserved,
                    "fbs_return_available_units": snapshot.fbs_return_available_units,
                    "fbs_return_is_subset_of_available": snapshot.fbs_return_is_subset_of_available,
                    "period": (snapshot.period_from, snapshot.period_to),
                }))
            if snapshot.fbs_return_is_subset_of_available is False:
                stock_conflict = True
        if not proposal.stock_snapshots or stock_gaps:
            add(FifoMissingRequirement(
                code="STOCK_RESERVED_OR_OVERLAP_UNKNOWN",
                status="CONFLICT" if stock_conflict else "MISSING",
                required_document_or_action=(
                    "Отчёт «Управление остатками» с отдельным числом reserved и подтверждённым "
                    "соотношением FBS-возвратов к доступному остатку"
                ),
                required_fields=(
                    "reserved", "available", "FBS-return quantity", "FBS-return overlap/subset rule",
                ),
                required_period=(proposal.confirmed_cutoff_date, proposal.confirmed_cutoff_date)
                if proposal.confirmed_cutoff_date else None,
                already_saved=stock_refs,
                known_values=MappingProxyType({"unresolved_snapshots": tuple(stock_gaps)}),
                explanation=(
                    "Unknown/reserved or overlap must stay unknown until an independent field or "
                    "owner-confirmed relationship is saved; do not subtract or add it by inference."
                ),
                blocks_apply=True,
            ))

        turnover_refs = tuple(
            self._report_ref("TURNOVER", view) for view in proposal.turnover_controls
        )
        if not proposal.turnover_controls:
            add(FifoMissingRequirement(
                code="TURNOVER_REPORT_REQUIRED",
                status="MISSING",
                required_document_or_action="Оборотная ведомость Ozon по SKU",
                required_fields=("период", "opening", "receipts", "redemption/outflow", "closing"),
                required_period=(case.dispatch_date, proposal.confirmed_cutoff_date)
                if case.dispatch_date and proposal.confirmed_cutoff_date else None,
                already_saved=(),
                known_values=MappingProxyType({}),
                explanation="Для контрольного моста нет сохранённой оборотной ведомости.",
                blocks_apply=True,
            ))
        candidate_turnover = tuple(
            ref for ref in turnover_refs
            if ref.period_provenance == PeriodProvenance.FILENAME_CANDIDATE.value
        )
        if candidate_turnover:
            candidate_period = proposal.turnover_candidate_gap
            if candidate_period is None:
                candidate_ref = candidate_turnover[-1]
                if candidate_ref.period_from and candidate_ref.period_to:
                    candidate_period = (candidate_ref.period_from, candidate_ref.period_to)
            add(FifoMissingRequirement(
                code="TURNOVER_PERIOD_CONFIRMATION_REQUIRED",
                status="NEEDS_CONFIRMATION",
                required_document_or_action=(
                    "Подтвердить период файла оборотной ведомости или загрузить отчёт "
                    "с подтверждённым периодом"
                ),
                required_fields=("period_from", "period_to", "period_provenance"),
                required_period=candidate_period,
                already_saved=candidate_turnover,
                known_values=MappingProxyType({
                    "candidate_missing_period": proposal.turnover_candidate_gap,
                    "owner_confirmed_coverage_gap": None,
                }),
                explanation=(
                    "Даты из имени файла являются только кандидатом. Интервал не объявляется "
                    "фактически отсутствующим, пока владелец не подтвердит период."
                ),
                blocks_apply=True,
            ))
        if proposal.turnover_coverage_gap is not None:
            add(FifoMissingRequirement(
                code="TURNOVER_COVERAGE_GAP",
                status="MISSING",
                required_document_or_action=(
                    "Оборотная ведомость Ozon за отсутствующий период с подтверждёнными датами"
                ),
                required_fields=("period_from", "period_to", "SKU rows", "quantity movements"),
                required_period=proposal.turnover_coverage_gap,
                already_saved=tuple(
                    ref for ref in turnover_refs
                    if ref.period_provenance == PeriodProvenance.OWNER_CONFIRMED.value
                ),
                known_values=MappingProxyType({
                    "saved_confirmed_data_through": proposal.turnover_coverage_gap[0],
                    "requested_cutoff": proposal.turnover_coverage_gap[1],
                }),
                explanation=(
                    "Сохранённый подтверждённый отчёт заканчивается раньше cutoff. "
                    "complete_through не переносится на конец периода автоматически."
                ),
                blocks_apply=True,
            ))

        if supply_reconciliation is not None and self._has_act_conflict(supply_reconciliation):
            add(FifoMissingRequirement(
                code="ACCEPTANCE_ACT_CONFLICT",
                status="CONFLICT",
                required_document_or_action=(
                    "Разобрать противоречие идентичности/версии акта с точной привязкой к поставке"
                ),
                required_fields=(
                    "supply reference", "act reference/version", "SKU identity",
                    "declared/accepted quantity", "source timestamps",
                ),
                required_period=None,
                already_saved=tuple(
                    FifoReadinessEvidenceRef(
                        source_type="SUPPLY_ACCEPTANCE_CONFLICT",
                        fingerprint=item.source_fingerprint,
                        captured_at=item.captured_at,
                        source_as_of=item.source_as_of,
                        period_from=next((
                            declaration.dispatch_date for declaration in declarations
                            if declaration.declaration_id == item.declaration_id
                        ), None),
                        period_to=next((
                            declaration.dispatch_date for declaration in declarations
                            if declaration.declaration_id == item.declaration_id
                        ), None),
                        period_provenance="API_AS_OF",
                        saved_fields=(
                            "acceptance_status", "issue_codes", "act_reference_present",
                        ),
                    )
                    for item in supply_reconciliation.acceptance_conflicts
                ),
                known_values=MappingProxyType({
                    "conflict_codes": tuple(sorted(
                        code for code in supply_reconciliation.issue_codes
                        if code in {
                            "ACCEPTANCE_BINDING_CONFLICT",
                            "ACCEPTANCE_RECONCILIATION_CONFLICT",
                        }
                    )),
                    "saved_conflicting_acceptance_count": len(
                        supply_reconciliation.acceptance_conflicts,
                    ),
                }),
                explanation=(
                    "Акт нельзя связывать с поставкой по одному совпадению SKU/количества; "
                    "сохранённый конфликт требует проверки владельца."
                ),
                blocks_apply=True,
            ))

        if supply_reconciliation is not None and self._has_conflict(supply_reconciliation):
            add(FifoMissingRequirement(
                code="SUPPLY_EVIDENCE_CONFLICT",
                status="CONFLICT",
                required_document_or_action=(
                    "Сверить конфликтующие количества/идентификаторы поставок с первичными документами"
                ),
                required_fields=("точная ссылка", "SKU", "revision", "quantity", "source timestamp"),
                required_period=None,
                already_saved=tuple(
                    FifoReadinessEvidenceRef(
                        source_type="SUPPLY_DECLARATION_OR_OBSERVATION",
                        fingerprint=item.observed_source_fingerprint,
                        captured_at=item.observed_at,
                        source_as_of=item.observed_source_as_of,
                        period_from=item.dispatch_date,
                        period_to=item.dispatch_date,
                        period_provenance="API_AS_OF" if item.observed_source_as_of else "OWNER_INPUT",
                        saved_fields=("declared_quantity", "observed_status", "accepted_quantity"),
                    )
                    for item in declarations if item.observed_at is not None
                ),
                known_values=MappingProxyType({
                    "conflict_codes": tuple(sorted(
                        code for code in supply_reconciliation.issue_codes
                        if code in self._CONFLICT_CODES
                    )),
                }),
                explanation="Конфликт evidence остаётся открытым и закрывает применение.",
                blocks_apply=True,
            ))

        if proposal.confirmed_cutoff_date is None:
            add(FifoMissingRequirement(
                code="OWNER_CUTOFF_CONFIRMATION_REQUIRED",
                status="NEEDS_CONFIRMATION",
                required_document_or_action="Подтвердить дату среза начального остатка",
                required_fields=("owner_confirmed_cutoff_date",),
                required_period=None,
                already_saved=(),
                known_values=MappingProxyType({"filename_date_is_cutoff": False}),
                explanation="Дата из имени файла не используется как подтверждённый cutoff.",
                blocks_apply=True,
            ))

        if not self._has_sale_bridge(cutoff_bridge):
            add(FifoMissingRequirement(
                code="SALE_CUTOFF_BRIDGE_REQUIRED",
                status="MISSING",
                required_document_or_action=(
                    "Документированный bridge движений продаж/возвратов/выбытий до cutoff "
                    "с доказательством физической даты"
                ),
                required_fields=(
                    "точный posting/operation identity", "SKU", "физическая дата события",
                    "quantity", "source provenance и coverage proof",
                ),
                required_period=(case.dispatch_date, proposal.confirmed_cutoff_date)
                if case.dispatch_date and proposal.confirmed_cutoff_date else None,
                already_saved=(
                    FifoReadinessEvidenceRef(
                        source_type="CUTOFF_BRIDGE",
                        fingerprint=cutoff_bridge.source_set_fingerprint,
                        captured_at=None,
                        source_as_of=None,
                        period_from=case.dispatch_date,
                        period_to=cutoff_bridge.complete_through,
                        period_provenance="OWNER_CONFIRMED_AND_SOURCE_COVERED",
                        saved_fields=(
                            "cutoff", "stock_scope", "pre_cutoff_outflows",
                            "post_cutoff_physical_events", "finance_identity_mappings",
                        ),
                    ),
                ) if cutoff_bridge is not None else (),
                known_values=MappingProxyType({
                    "sales_bridge_verified": bool(
                        cutoff_bridge is not None
                        and cutoff_bridge.ready_for_fifo_event
                        and not cutoff_bridge.unresolved_issues
                    ),
                    "unresolved_issues": (
                        cutoff_bridge.unresolved_issues if cutoff_bridge is not None else ()
                    ),
                }),
                explanation=(
                    "Суммарные количества и даты финансовых начислений сами по себе "
                    "не доказывают физический FIFO-порядок продаж. Нужны точные "
                    "posting/SKU/date/quantity и полное покрытие подтверждённым документом."
                ),
                blocks_apply=True,
            ))

        source_lag = self._source_lag(supply_reconciliation)
        if source_lag is not None:
            add(source_lag)

        requirements_tuple = tuple(
            requirements[key] for key in sorted(requirements)
        )
        if len(requirements_tuple) > self.MAX_REQUIREMENTS:
            raise ValueError("FIFO_READINESS_INPUT_INVALID")
        conflicts = any(item.status == "CONFLICT" for item in requirements_tuple)
        return FifoCostTransitionReadiness(
            status="CONFLICT" if conflicts else "AWAITING_EVIDENCE",
            scope=case.metadata.scope,
            case_id=case.case_id,
            case_revision=case.case_revision,
            cutoff_date=proposal.confirmed_cutoff_date,
            case_state_before=case.state.value,
            case_state_after=case.state.value,
            requirements=requirements_tuple,
            source_data_through=self._latest_confirmed_end(proposal),
            candidate_data_through=self._latest_candidate_end(proposal),
            complete_through=None,
            ready_to_apply=False,
            preview_only=True,
            is_atomic_snapshot=False,
        )

    @staticmethod
    def _report_ref(source_type, view):
        return FifoReadinessEvidenceRef(
            source_type=source_type,
            fingerprint=view.report_fingerprint,
            captured_at=view.captured_at,
            source_as_of=None,
            period_from=view.period_from,
            period_to=view.period_to,
            period_provenance=view.period_provenance.value,
            saved_fields=tuple(sorted(view.stock_buckets)) + tuple(name for name, value in (
                ("fbs_return_available_units", view.fbs_return_available_units),
                ("fbs_return_is_subset_of_available", view.fbs_return_is_subset_of_available),
            ) if source_type == "STOCK_MANAGEMENT" and value is not None)
            if source_type == "STOCK_MANAGEMENT"
            else tuple(name for name, value in (
                ("opening_total", view.opening_total),
                ("receipts_total", view.receipts_total),
                ("expenses_total", view.expenses_total),
                ("closing_total", view.closing_total),
                ("redeemed_units", view.redeemed_units),
                ("withdrawal_units", view.withdrawal_units),
                ("buyer_delivery", view.closing_buyer_delivery_units),
                ("buyer_return_transit", view.closing_buyer_return_transit_units),
            ) if value is not None),
        )

    @staticmethod
    def _has_conflict(reconciliation):
        return any(code in FifoCostTransitionReadinessService._CONFLICT_CODES
                   for code in reconciliation.issue_codes)

    @classmethod
    def _has_act_conflict(cls, reconciliation):
        return bool(
            {"ACCEPTANCE_BINDING_CONFLICT", "ACCEPTANCE_RECONCILIATION_CONFLICT"}
            & set(reconciliation.issue_codes)
        ) or any(
            item.acceptance_status in {"CONFLICT", "INVALID"}
            or item.acceptance_declared_quantity_difference not in (None, 0)
            for item in reconciliation.declarations
        )

    @classmethod
    def _source_lag(cls, reconciliation):
        if reconciliation is None:
            return None
        declaration_refs = tuple(
            FifoReadinessEvidenceRef(
                source_type="OZON_SUPPLY_API",
                fingerprint=item.observed_source_fingerprint,
                captured_at=item.observed_at,
                source_as_of=item.observed_source_as_of,
                period_from=item.dispatch_date,
                period_to=item.dispatch_date,
                period_provenance="API_AS_OF" if item.observed_source_as_of else None,
                saved_fields=tuple(name for name, value in (
                    ("status", item.observed_status),
                    ("source_as_of", item.observed_source_as_of),
                    ("presence", item.observed_presence),
                    ("accepted_quantity", item.accepted_quantity),
                ) if value is not None),
            )
            for item in reconciliation.declarations
            if item.observed_at is not None or item.observed_presence is not None
        )
        stale_observations = tuple(
            item for item in reconciliation.declarations
            if item.observation_freshness != "CURRENT"
        )
        as_of_not_atomic = reconciliation.source_as_of_coherence != "SAME"
        if not stale_observations and not as_of_not_atomic:
            return None
        return FifoMissingRequirement(
            code="SUPPLY_SOURCE_LAG_OR_AS_OF_GAP",
            status="NEEDS_CONFIRMATION",
            required_document_or_action=(
                "Обновить полный список поставок и данные актов; сохранить source_as_of, "
                "полноту страниц и время получения"
            ),
            required_fields=(
                "captured_at", "source_as_of", "pagination_complete", "scope_complete",
                "status", "acceptance quantity and act binding",
            ),
            required_period=None,
            already_saved=declaration_refs,
            known_values=MappingProxyType({
                "source_as_of_coherence": reconciliation.source_as_of_coherence,
                "declarations_not_current": tuple(item.declaration_id for item in stale_observations),
            }),
            explanation=(
                "Снимки источников не подтверждают общий актуальный watermark. "
                "Без зафиксированного SLA это предупреждение о покрытии/as-of, а не "
                "утверждение, что данные устарели на заданное число часов."
            ),
            blocks_apply=True,
        )

    @staticmethod
    def _has_sale_bridge(cutoff_bridge):
        return bool(
            isinstance(cutoff_bridge, FifoCutoffBridgeResult)
            and cutoff_bridge.status == "READY"
            and cutoff_bridge.ready_for_fifo_event is True
            and cutoff_bridge.preview_only is True
            and cutoff_bridge.complete_through is not None
            and not cutoff_bridge.unresolved_issues
        )

    @staticmethod
    def _latest_confirmed_end(proposal):
        values = [
            view.period_to for view in proposal.turnover_controls
            if view.period_to and view.period_provenance is PeriodProvenance.OWNER_CONFIRMED
            and view.completeness is EvidenceCompleteness.COMPLETE
        ]
        return max(values) if values else None

    @staticmethod
    def _latest_candidate_end(proposal):
        values = [
            view.period_to for view in proposal.turnover_controls
            if view.period_to and view.period_provenance is PeriodProvenance.FILENAME_CANDIDATE
        ]
        return max(values) if values else None


def _freeze_mapping(value):
    if not isinstance(value, Mapping):
        raise ValueError("FIFO_READINESS_INPUT_INVALID")
    return MappingProxyType({
        key: _freeze_value(item) for key, item in value.items()
    })


def _freeze_value(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze_value(item) for item in value)
    return value
