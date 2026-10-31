"""Persist a phase maturity evaluation over the newest frozen collection only."""

from datetime import datetime, timezone

from services.unit_economics_experiment_phase_maturity_service import (
    UnitEconomicsExperimentPhaseMaturityService,
)


class UnitEconomicsExperimentPhaseReadinessService:
    """Evaluate stored evidence with CAS; it never contacts Ozon or recalculates profit."""

    MAX_PHASES = 10
    MAX_EVENTS = 100
    EVENT_PAGE_SIZE = 10

    def __init__(self, repository, clock=None):
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def evaluate_latest(
        self, experiment_id, phase_id, *, expected_state_revision,
        expected_phase_state_revision, expected_result_revision,
        idempotency_key, owner_id, store_id,
    ):
        if (not isinstance(owner_id, str) or not owner_id.strip()
                or not isinstance(store_id, str) or not store_id.strip()
                or type(expected_state_revision) is not int or expected_state_revision < 1
                or type(expected_phase_state_revision) is not int
                or expected_phase_state_revision < 1
                or type(expected_result_revision) is not int or expected_result_revision < 0):
            return self._error("EXPERIMENT_PHASE_READINESS_INPUT_INVALID")
        experiment_result = self.repository.get_price_experiment(
            experiment_id, owner_id=owner_id, store_id=store_id,
        )
        if experiment_result.get("error"):
            return experiment_result
        experiment = experiment_result.get("experiment")
        phases_result = self.repository.list_price_experiment_phases(
            experiment_id, limit=self.MAX_PHASES, owner_id=owner_id, store_id=store_id,
        )
        if phases_result.get("error"):
            return phases_result
        phase = next((item for item in phases_result.get("items", [])
                      if item.get("phase_id") == phase_id), None)
        if phase is None:
            return self._error("EXPERIMENT_PHASE_NOT_FOUND")
        if phase.get("status") not in {"ACTIVE", "PAUSED", "FINISHED"}:
            return self._error("EXPERIMENT_PHASE_NOT_EVALUABLE")
        if (phase.get("observation_id") is None or phase.get("confirmation") is None
                or experiment.get("status") in {"CANCELLED", "COMPLETED", "ARCHIVED"}):
            return self._error("EXPERIMENT_PHASE_NOT_EVALUABLE")

        collections = self.repository.list_price_experiment_phase_collections(
            experiment_id, phase_id, limit=1, owner_id=owner_id, store_id=store_id,
        )
        if collections.get("error"):
            return collections
        if not collections.get("items"):
            return self._error("EXPERIMENT_PHASE_COLLECTION_NOT_FOUND")
        collection_item = collections["items"][0]
        event_items = []
        event_offset = 0
        while True:
            events = self.repository.list_price_experiment_events(
                experiment_id, phase_id=phase_id,
                limit=min(self.EVENT_PAGE_SIZE, self.MAX_EVENTS - len(event_items)),
                offset=event_offset, owner_id=owner_id, store_id=store_id,
            )
            if events.get("error"):
                return events
            event_items.extend(events.get("items", []))
            if events.get("has_more") is not True:
                break
            if len(event_items) >= self.MAX_EVENTS:
                return self._error("EXPERIMENT_PHASE_EVENT_HISTORY_INCOMPLETE")
            event_offset = events.get("next_offset")
        now = self.clock()
        evaluated = UnitEconomicsExperimentPhaseMaturityService.evaluate(
            experiment, phase, collection_item["payload"],
            collection_item["collection_id"], event_items, now,
        )
        if evaluated.get("error"):
            return evaluated
        saved = self.repository.append_price_experiment_result(
            experiment_id, phase_id, evaluated["payload"],
            expected_state_revision=expected_state_revision,
            expected_phase_state_revision=expected_phase_state_revision,
            expected_result_revision=expected_result_revision,
            idempotency_key=idempotency_key, owner_id=owner_id, store_id=store_id,
        )
        if saved.get("error"):
            return saved
        return {
            **saved, "status": evaluated["status"],
            "outcome": evaluated["outcome"],
            "collection_revision": collection_item["collection_revision"],
            "read_only": True, "source_io": False,
        }

    @staticmethod
    def _error(code):
        return {"error": True, "code": code, "read_only": True, "source_io": False}
