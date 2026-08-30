from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"
REQUIREMENTS = ROOT / "requirements-dev.txt"


def test_v269_dev_dependencies_are_explicit_and_bounded():
    text = REQUIREMENTS.read_text(encoding="utf-8")
    assert "pytest>=8,<9" in text
    assert "requests>=2.31,<3" in text
    assert "python-dotenv>=1,<2" in text


def test_v270_workflow_runs_on_pull_request_and_main():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request:" in text
    assert "push:" in text
    assert "- main" in text


def test_v271_workflow_compiles_application_before_tests():
    text = WORKFLOW.read_text(encoding="utf-8")
    compile_index = text.index("python -m compileall -q app")
    pytest_index = text.index("python -m pytest -q")
    assert compile_index < pytest_index


def test_v272_workflow_uses_app_pythonpath():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "PYTHONPATH: app" in text


def test_v273_workflow_records_exact_commit_sha():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "commit_sha=%s" in text
    assert '"$GITHUB_SHA"' in text
    assert "verification-artifacts/revision.txt" in text


def test_v274_workflow_emits_junit_report():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "--junitxml=verification-artifacts/pytest-junit.xml" in text


def test_v275_ci_does_not_receive_ozon_credentials():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'OZON_CLIENT_ID: ""' in text
    assert 'OZON_API_KEY: ""' in text
    assert "secrets.OZON" not in text


def test_v276_workflow_has_minimal_permissions_and_timeout():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "permissions:\n  contents: read" in text
    assert "timeout-minutes: 20" in text


def test_v277_workflow_cancels_superseded_runs():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "cancel-in-progress: true" in text


def test_v278_verification_artifact_is_uploaded_even_after_failure():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "if: always()" in text
    assert "actions/upload-artifact@v4" in text
    assert "verification-${{ github.sha }}" in text
