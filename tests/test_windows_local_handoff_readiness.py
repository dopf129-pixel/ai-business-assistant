from pathlib import Path

from telegram_app_layer import telegram_api_bot


ROOT = Path(__file__).resolve().parents[1]


def test_windows_polling_disables_unsupported_signal_handlers():
    assert telegram_api_bot._polling_stop_signals("nt") is None


def test_posix_polling_keeps_graceful_shutdown_signals():
    signals = telegram_api_bot._polling_stop_signals("posix")
    assert signals == (telegram_api_bot.signal.SIGINT, telegram_api_bot.signal.SIGTERM)


def test_windows_bootstrap_uses_python_312_and_private_local_env():
    script = (ROOT / "start_bot.ps1").read_text(encoding="utf-8")

    assert '"-3.12"' in script
    assert ".venv\\Scripts\\python.exe" in script
    assert "Fernet.generate_key" in script
    assert "TELEGRAM_BOT_TOKEN=" in script
    assert "OZON_CREDENTIAL_MASTER_KEY=$MasterKey" in script
    assert "AI_ASSISTANT_STORAGE_ROOT=.runtime-data" in script
    assert '"-m" "telegram_api_bot"' in script
    assert "Write-Host $MasterKey" not in script
    assert "APP_BUILD_REVISION" in script
    assert "APP_BUILD_STARTED_AT_UTC" in script
    assert "rev-parse --verify HEAD" in script
    assert "param([switch]$Background)" in script
    assert "-WindowStyle Hidden" in script
    assert '"-m", "telegram_api_bot"' in script
    assert 'APP_BUILD_MODE = "background"' in script
    assert 'APP_BUILD_MODE = "foreground"' in script


def test_local_status_and_stop_scripts_use_private_venv_cli():
    for name, command in (("status_bot.ps1", "status"), ("stop_bot.ps1", "stop")):
        script = (ROOT / name).read_text(encoding="utf-8")
        assert ".venv\\Scripts\\python.exe" in script
        assert "-m telegram_bot_control" in script
        assert f" {command}" in script
        assert "TELEGRAM_BOT_TOKEN" not in script


def test_local_secret_and_runtime_paths_are_gitignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "\n.env\n" in f"\n{gitignore}"
    assert ".runtime-data/" in gitignore


def test_env_example_contains_only_placeholders():
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "replace_with_your_telegram_bot_token" in example
    assert "generated_locally_by_start_bot_ps1" in example
    assert "AI_ASSISTANT_STORAGE_ROOT=.runtime-data" in example
    assert "OZON_CLIENT_ID=" not in example
    assert "OZON_API_KEY=" not in example


def test_recovery_runbook_documents_safe_first_fast_forward_from_legacy_checkout():
    runbook = (ROOT / "docs" / "daily-use-recovery-runbook.md").read_text(encoding="utf-8")

    assert "### Первый переход со старого checkout" in runbook
    assert "update_bot.ps1` может ещё отсутствовать" in runbook
    assert "git branch --show-current" in runbook
    assert "git status --short" in runbook
    assert "git pull --ff-only origin main" in runbook
    assert "git diff --binary HEAD" in runbook
    assert "git ls-files --others --exclude-standard" in runbook
    assert "не выполняйте pull" in runbook
    assert "не прикладывайте к задаче и не отправляйте в GitHub" in runbook
    assert "-CheckOnly" in runbook and "-NoStart" in runbook
    for prohibited in ("git restore --", "git reset --hard", "git clean -fd"):
        assert f"```powershell\n{prohibited}" not in runbook


def test_canonical_entrypoint_loads_dotenv_before_runtime_import():
    entrypoint = (ROOT / "app" / "telegram_api_bot.py").read_text(encoding="utf-8")
    load_index = entrypoint.index("load_dotenv()")
    import_index = entrypoint.index("from telegram_app_layer.telegram_api_bot")
    assert load_index < import_index
