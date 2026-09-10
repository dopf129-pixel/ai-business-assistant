from pathlib import Path


def _compose_text() -> str:
    return Path("docker-compose.production.yml").read_text(encoding="utf-8")


def test_compose_uses_repository_dockerfile_and_persistent_volume():
    text = _compose_text()

    assert "dockerfile: Dockerfile" in text
    assert "AI_ASSISTANT_STORAGE_ROOT: /var/lib/ai-business-assistant" in text
    assert "ai_business_assistant_data:/var/lib/ai-business-assistant" in text
    assert "ai_business_assistant_data:" in text


def test_compose_requires_runtime_secrets_at_deploy_time_without_values():
    text = _compose_text()

    assert "TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN is required}" in text
    assert (
        "OZON_CREDENTIAL_MASTER_KEY: "
        "${OZON_CREDENTIAL_MASTER_KEY:?OZON_CREDENTIAL_MASTER_KEY is required}"
    ) in text
    assert "TELEGRAM_BOT_TOKEN=" not in text
    assert "OZON_CREDENTIAL_MASTER_KEY=" not in text


def test_compose_declares_restart_and_graceful_stop_window():
    text = _compose_text()

    assert "restart: unless-stopped" in text
    assert "stop_grace_period: 30s" in text


def test_compose_does_not_publish_network_ports_or_override_healthcheck():
    text = _compose_text()

    assert "ports:" not in text
    assert "healthcheck:" not in text
    assert "command:" not in text
