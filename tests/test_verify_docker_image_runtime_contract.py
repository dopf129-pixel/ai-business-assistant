from pathlib import Path


WORKFLOW = Path('.github/workflows/verify.yml')


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding='utf-8')


def test_verify_builds_production_docker_image_from_repository_root():
    text = _workflow_text()

    assert '- name: Build production Docker image' in text
    assert 'docker build --pull=false --tag "$IMAGE" .' in text
    assert 'ai-business-assistant:verify-${GITHUB_SHA}' in text
    assert 'docker image inspect "$IMAGE"' in text


def test_verify_smokes_runtime_healthcheck_inside_built_image():
    text = _workflow_text()

    assert '- name: Smoke production Docker runtime' in text
    assert '-m runtime_healthcheck' in text
    assert 'TELEGRAM_BOT_TOKEN=verification-token' in text
    assert 'OZON_CREDENTIAL_MASTER_KEY="$MASTER_KEY"' in text
    assert 'AI_ASSISTANT_STORAGE_ROOT=/tmp' in text


def test_verify_generates_ephemeral_fernet_key_without_repository_secret():
    text = _workflow_text()

    assert 'Fernet.generate_key()' in text
    assert 'MASTER_KEY="$(docker run --rm --entrypoint python' in text
    assert 'secrets.OZON_CREDENTIAL_MASTER_KEY' not in text


def test_verify_imports_canonical_container_runtime_modules():
    text = _workflow_text()

    assert 'import telegram_api_bot, runtime_healthcheck' in text
    assert 'container imports ok' in text
