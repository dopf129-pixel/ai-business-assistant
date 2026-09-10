"""Local, side-effect-free healthcheck for the Telegram production runtime."""

import os
from pathlib import Path

from cryptography.fernet import Fernet


_STORAGE_ROOT_ENV = "AI_ASSISTANT_STORAGE_ROOT"
_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
_OZON_MASTER_KEY_ENV = "OZON_CREDENTIAL_MASTER_KEY"


def check_runtime_environment(environment=None):
    """Return health status without network calls or seller-runtime initialization."""
    env = environment if environment is not None else os.environ
    token = str(env.get(_TOKEN_ENV, "") or "").strip()
    storage_root = str(env.get(_STORAGE_ROOT_ENV, "") or "").strip()
    ozon_master_key = str(env.get(_OZON_MASTER_KEY_ENV, "") or "").strip()

    if not token:
        return False, "telegram token is not configured"

    if storage_root:
        root = Path(storage_root)
        if not root.exists():
            return False, "storage root does not exist"
        if not root.is_dir():
            return False, "storage root is not a directory"
        if not os.access(root, os.W_OK | os.X_OK):
            return False, "storage root is not writable"

        if not ozon_master_key:
            return False, "Ozon credential master key is not configured"
        try:
            Fernet(ozon_master_key.encode("utf-8"))
        except Exception:
            return False, "Ozon credential master key is invalid"

    return True, "ok"


def main():
    healthy, message = check_runtime_environment()
    print(message)
    raise SystemExit(0 if healthy else 1)


if __name__ == "__main__":
    main()
