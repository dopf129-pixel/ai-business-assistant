"""Bounded W36 concurrency and fixed-seed persistence acceptance."""

from concurrent.futures import ThreadPoolExecutor
from random import Random
from threading import Barrier

from services.tenant_context import reset_current_tenant_user_id
from test_planning_workspace_unit_economics import (
    _context,
    _experiment_payload,
    _ready_baseline_phase,
    _seed,
)
from test_unit_economics_experiment_phase_collection_service import (
    PhaseEvidenceCollector,
    _active_phase,
    _service,
)


def test_parallel_baseline_confirmation_creates_exactly_one_observation(tmp_path):
    from services.planning_workspace_repository import PlanningWorkspaceRepository

    repo = PlanningWorkspaceRepository(db_path=tmp_path / "confirm-race.sqlite")
    saved, snapshot, experiment = _seed(repo)
    token = _context()
    try:
        phase = _ready_baseline_phase(repo, saved, snapshot, experiment)
    finally:
        reset_current_tenant_user_id(token)
    start = Barrier(2)

    def confirm(index):
        token = _context()
        try:
            start.wait(timeout=5)
            return repo.confirm_price_experiment_phase(
                experiment["experiment_id"], phase["phase_id"],
                seller_price_cents=10_000,
                effective_from="2026-10-29T12:00:00+03:00",
                owner_confirmed=True, expected_state_revision=4,
                expected_phase_state_revision=1,
                idempotency_key=f"w36-confirm-race-{index}",
                owner_id="owner-1", store_id="store-a",
            )
        finally:
            reset_current_tenant_user_id(token)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(confirm, (1, 2)))

    assert sum(result.get("error") is False for result in results) == 1
    failure = next(result for result in results if result.get("error") is True)
    assert failure["code"] == "PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT"
    token = _context()
    try:
        observations = repo.list_unit_price_observations(
            owner_id="owner-1", store_id="store-a",
        )
        assert len(observations["items"]) == 1
        assert observations["items"][0]["seller_price_cents"] == 10_000
        current = repo.get_price_experiment(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )["experiment"]
        phase_row = repo.list_price_experiment_phases(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )["items"][0]
        assert current["status"] == "BASELINE_ACTIVE"
        assert current["state_revision"] == 5
        assert phase_row["status"] == "ACTIVE"
        assert phase_row["observation_id"] == observations["items"][0]["observation_id"]
    finally:
        reset_current_tenant_user_id(token)


def test_parallel_phase_collection_commits_one_snapshot_and_one_result(tmp_path):
    repo, parent_token, experiment, phase, confirmed = _active_phase(tmp_path)
    try:
        source_barrier = Barrier(2)
        collector = PhaseEvidenceCollector(callback=lambda: source_barrier.wait(timeout=5))
        service = _service(repo, collector)

        def collect(index):
            token = _context()
            try:
                return service.collect_phase(
                    experiment["experiment_id"], phase["phase_id"],
                    expected_state_revision=confirmed["state_revision"],
                    expected_phase_state_revision=confirmed["phase_state_revision"],
                    expected_result_revision=0,
                    idempotency_key=f"w36-collect-race-{index}",
                    owner_id="owner-1", store_id="store-a",
                )
            finally:
                reset_current_tenant_user_id(token)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(collect, (1, 2)))

        assert sum(result.get("error") is False for result in results) == 1
        failed = next(result for result in results if result.get("error") is True)
        assert failed["code"] in {
            "PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT",
            "PLANNING_PRICE_EXPERIMENT_RESULT_CONFLICT",
        }
        collections = repo.list_price_experiment_phase_collections(
            experiment["experiment_id"], phase["phase_id"],
            owner_id="owner-1", store_id="store-a",
        )
        saved_results = repo.list_price_experiment_results(
            experiment["experiment_id"], phase["phase_id"],
            owner_id="owner-1", store_id="store-a",
        )
        assert len(collections["items"]) == 1
        assert len(saved_results["items"]) == 1
        assert collections["items"][0]["collection_revision"] == 1
        assert collections["items"][0]["payload"]["metrics"]["commission"] == "-70.00"
        assert collections["items"][0]["payload"]["metrics"]["cpc_spend"] == "12.50"
        assert saved_results["items"][0]["result_revision"] == 1
    finally:
        reset_current_tenant_user_id(parent_token)


def test_parallel_draft_edit_and_archive_leave_one_consistent_revision(tmp_path):
    from services.planning_workspace_repository import PlanningWorkspaceRepository

    repo = PlanningWorkspaceRepository(db_path=tmp_path / "edit-archive-race.sqlite")
    saved, snapshot, experiment = _seed(repo)
    config = _experiment_payload(saved["document_id"], snapshot["snapshot_id"])
    config.update({
        "plan_schema_version": 1,
        "candidate_price_bounds_cents": {
            "min_price_cents": 9500, "max_price_cents": 10500,
        },
        "maturity_min_days": 7,
        "maturity_min_units": 30,
    })
    config["decision_threshold_rub"] = "0.02"
    start = Barrier(2)

    def edit_or_archive(action):
        token = _context()
        try:
            start.wait(timeout=5)
            if action == "edit":
                return repo.update_price_experiment_draft(
                    experiment["experiment_id"], config,
                    expected_state_revision=1,
                    idempotency_key="w36-race-edit",
                    owner_id="owner-1", store_id="store-a",
                )
            return repo.archive_price_experiment(
                experiment["experiment_id"], expected_state_revision=1,
                idempotency_key="w36-race-archive",
                owner_id="owner-1", store_id="store-a",
            )
        finally:
            reset_current_tenant_user_id(token)

    with ThreadPoolExecutor(max_workers=2) as pool:
        edit_future = pool.submit(edit_or_archive, "edit")
        archive_future = pool.submit(edit_or_archive, "archive")
        edited = edit_future.result()
        archived = archive_future.result()

    assert sum(result.get("error") is False for result in (edited, archived)) == 1
    if edited.get("error") is False:
        assert archived["code"] == "PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT"
        expected_status = "DRAFT"
    else:
        assert edited["code"] in {
            "PLANNING_PRICE_EXPERIMENT_STATE_CONFLICT",
            "PLANNING_PRICE_EXPERIMENT_DRAFT_FROZEN",
        }
        assert archived.get("error") is False
        expected_status = "ARCHIVED"

    token = _context()
    try:
        current = repo.get_price_experiment(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )["experiment"]
        revisions = repo.list_price_experiment_revisions(
            experiment["experiment_id"], owner_id="owner-1", store_id="store-a",
        )["items"]
        assert current["status"] == expected_status
        assert current["state_revision"] == 2
        assert len(revisions) == 2
        assert revisions[0]["state_revision"] == 2
        assert revisions[0]["status"] == expected_status
        assert revisions[1]["state_revision"] == 1
        assert revisions[1]["status"] == "DRAFT"
    finally:
        reset_current_tenant_user_id(token)


def test_fixed_seed_control_event_soak_keeps_bounded_append_only_history(tmp_path):
    from services.planning_workspace_repository import PlanningWorkspaceRepository
    from test_planning_workspace_unit_economics import _confirm_baseline_phase

    repo = PlanningWorkspaceRepository(db_path=tmp_path / "finite-soak.sqlite")
    saved, snapshot, experiment = _seed(repo)
    token = _context()
    try:
        phase = _ready_baseline_phase(repo, saved, snapshot, experiment)
    finally:
        reset_current_tenant_user_id(token)
    token = _context()
    try:
        confirmed = _confirm_baseline_phase(repo, experiment, phase)
        assert confirmed["error"] is False
        expected_state_revision = confirmed["state_revision"]
        # _ready_baseline_phase returns the compact create response rather than
        # a decoded phase row, so use the documented six-category control set.
        current_flags = {
            key: "UNCHANGED" for key in (
                "inventory", "promotion", "advertising", "card", "cost", "tariff",
            )
        }
        rng = Random(20261029)
        categories = tuple(current_flags)
        allowed_values = ("UNCHANGED", "CHANGED", "UNKNOWN")

        for index in range(64):
            category = rng.choice(categories)
            replacement = rng.choice(tuple(
                value for value in allowed_values if value != current_flags[category]
            ))
            current_flags[category] = replacement
            updated = repo.record_price_experiment_control_update(
                experiment["experiment_id"], phase["phase_id"], dict(current_flags),
                expected_state_revision=expected_state_revision,
                idempotency_key=f"w36-fixed-soak-{index:03d}",
                owner_id="owner-1", store_id="store-a",
            )
            assert updated["error"] is False
            assert updated["state_revision"] == expected_state_revision + 1
            expected_state_revision = updated["state_revision"]

        events = []
        offset = 0
        page_count = 0
        while True:
            page = repo.list_price_experiment_events(
                experiment["experiment_id"], limit=10, offset=offset,
                owner_id="owner-1", store_id="store-a",
            )
            assert page.get("error") is False
            events.extend(page["items"])
            page_count += 1
            if not page["has_more"]:
                break
            offset = page["next_offset"]
        assert page_count == 7
        controls = [item for item in events
                    if item["event_kind"] == "CONTROL_UPDATE"]
        assert len(controls) == 64
        assert [item["event_revision"] for item in controls] == list(range(64, 0, -1))
        assert expected_state_revision == confirmed["state_revision"] + 64
        assert all(item["payload"]["source"] == "OWNER_REPORTED" for item in controls)
        serialized = repr(controls)
        for private_value in ("owner-1", "product-1", "offer-1", "sku-1", "raw_response", "api_key"):
            assert private_value not in serialized
    finally:
        reset_current_tenant_user_id(token)
