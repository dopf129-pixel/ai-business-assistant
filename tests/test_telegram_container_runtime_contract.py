from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
DOCKERIGNORE = ROOT / ".dockerignore"


def test_dockerfile_uses_canonical_telegram_entrypoint():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "PYTHONPATH=/app/app" in dockerfile
    assert 'CMD ["python", "-m", "telegram_api_bot"]' in dockerfile
    assert "COPY app ./app" in dockerfile


def test_dockerfile_installs_production_requirements_only():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "COPY requirements.txt ./requirements.txt" in dockerfile
    assert "pip install --no-cache-dir -r requirements.txt" in dockerfile
    assert "requirements-dev.txt" not in dockerfile


def test_dockerfile_declares_persistent_runtime_storage():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "AI_ASSISTANT_STORAGE_ROOT=/var/lib/ai-business-assistant" in dockerfile
    assert 'VOLUME ["/var/lib/ai-business-assistant"]' in dockerfile


def test_dockerignore_excludes_local_secrets_and_seller_state():
    dockerignore = DOCKERIGNORE.read_text(encoding="utf-8").splitlines()

    assert ".env" in dockerignore
    assert ".env.*" in dockerignore
    assert "data/" in dockerignore
    assert "*.db" in dockerignore
    assert "*.sqlite" in dockerignore
    assert "*.sqlite3" in dockerignore


def test_container_contract_does_not_bake_telegram_token():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "TELEGRAM_BOT_TOKEN=" not in dockerfile
