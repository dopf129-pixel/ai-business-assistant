from pathlib import Path


WORKFLOW = Path(
    ".github/workflows/verify.yml"
)


def test_v547_verify_workflow_keeps_main_push_contract():
    text = WORKFLOW.read_text(
        encoding="utf-8"
    )

    assert "push:" in text
    assert "- main" in text


def test_v547_verify_workflow_runs_on_branch_pushes_for_exact_sha():
    text = WORKFLOW.read_text(
        encoding="utf-8"
    )

    assert '- "**"' in text
    assert "Checkout exact revision" in text
    assert 'commit_sha=%s' in text
    assert '--commit-sha "$GITHUB_SHA"' in text
