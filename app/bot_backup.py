"""Local backup CLI. It never contacts Telegram or Ozon."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

from services.bot_backup_service import BotBackupService


def _parser():
    parser = argparse.ArgumentParser(
        description="Создание и проверка локальной резервной копии данных бота"
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    backup = subcommands.add_parser("backup", help="Создать проверенную копию")
    backup.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    verify = subcommands.add_parser("verify", help="Проверить архив без распаковки")
    verify.add_argument("archive")
    verify.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    restore = subcommands.add_parser("restore", help="Восстановить архив в новую папку")
    restore.add_argument("archive")
    restore.add_argument("--target-directory", required=True)
    restore.add_argument("--dry-run", action="store_true")
    restore.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    return parser


def main(argv=None):
    arguments = _parser().parse_args(argv)
    project_root = Path(arguments.project_root).resolve()
    load_dotenv(dotenv_path=project_root / ".env", override=False)
    service = BotBackupService(
        project_root=project_root,
        storage_root=os.getenv("AI_ASSISTANT_STORAGE_ROOT") or None,
        lifecycle_token=os.getenv("TELEGRAM_BOT_TOKEN"),
    )
    if arguments.command == "backup":
        result = service.backup()
    elif arguments.command == "verify":
        result = service.verify_archive(arguments.archive)
    else:
        result = service.restore_archive(
            arguments.archive,
            arguments.target_directory,
            dry_run=arguments.dry_run,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("error") is False else 1


if __name__ == "__main__":
    raise SystemExit(main())
