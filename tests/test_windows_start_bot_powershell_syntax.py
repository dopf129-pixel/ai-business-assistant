from pathlib import Path


def test_windows_launcher_delimits_lastexitcode_before_colon():
    script = Path("start_bot.ps1").read_text(encoding="utf-8")

    assert "${LASTEXITCODE}:" in script
    assert "$LASTEXITCODE:" not in script
