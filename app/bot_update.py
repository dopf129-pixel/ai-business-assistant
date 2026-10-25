"""Local command line for bot update preflight and explicit update execution."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

from services.bot_update_preflight_service import BotUpdatePreflightService
from services.bot_update_runtime_service import BotUpdateRuntimeService


_BLOCKER_TEXT = {
    "BOT_UPDATE_GIT_UNAVAILABLE": "Git недоступен или команда не выполнена.",
    "BOT_UPDATE_GIT_COMMAND_FAILED": "Не удалось прочитать локальное состояние Git.",
    "BOT_UPDATE_GIT_RELATION_INVALID": "Не удалось определить расхождение веток.",
    "BOT_UPDATE_WRONG_REPOSITORY_ROOT": "Скрипт запущен не из корня проверяемого репозитория.",
    "BOT_UPDATE_WRONG_BRANCH": "Текущая ветка должна быть main.",
    "BOT_UPDATE_WRONG_UPSTREAM": "Для main должна быть настроена origin/main.",
    "BOT_UPDATE_REMOTE_NOT_ALLOWED": "origin не соответствует официальному репозиторию проекта.",
    "BOT_UPDATE_LOCAL_COMMITS_AHEAD": "В main есть локальные коммиты; fast-forward обновление остановлено.",
    "BOT_UPDATE_LOCAL_DATA_OVERLAP": "Входящие изменения затрагивают локальные users/tasks данные.",
    "BOT_UPDATE_INCOMING_PROTECTED_DATA_CHANGE": "В целевой версии изменяются защищённые users/tasks данные.",
    "BOT_UPDATE_LOCAL_CHANGES_UNSAFE": "Есть незакоммиченные изменения кода или другого состояния.",
    "BOT_UPDATE_UNTRACKED_OVERWRITE_CONFLICT": "Целевая версия затронет неотслеживаемый файл.",
    "BOT_UPDATE_PROCESS_STATE_UNKNOWN": "Состояние экземпляра бота не удалось безопасно подтвердить.",
    "BOT_UPDATE_PROCESS_CHECKOUT_UNKNOWN": "Экземпляр бота не содержит подтверждения папки запуска; остановите его вручную.",
    "BOT_UPDATE_PROCESS_OTHER_CHECKOUT": "Этот токен занят экземпляром из другой папки проекта; updater его не остановит.",
    "BOT_UPDATE_WINDOWS_ONLY": "Автоматическое обновление поддерживается только через PowerShell в Windows.",
    "TELEGRAM_BOT_TOKEN_MISSING": "В .env не настроен TELEGRAM_BOT_TOKEN.",
    "BOT_UPDATE_POWERSHELL_UNAVAILABLE": "Не удалось найти PowerShell для безопасного запуска бота.",
    "BOT_UPDATE_ALREADY_RUNNING": "Другая команда обновления уже выполняется.",
    "BOT_UPDATE_LOCK_UNAVAILABLE": "Не удалось получить блокировку обновления для этой папки.",
    "BOT_UPDATE_REPOSITORY_IDENTITY_UNAVAILABLE": "Не удалось проверить локальную папку проекта.",
    "BOT_UPDATE_REPOSITORY_IDENTITY_REJECTED": "Текущая папка, ветка или origin не подходят для безопасного обновления.",
    "BOT_UPDATE_REVISION_INVALID": "Git не вернул корректные SHA текущей и целевой версий.",
    "BOT_UPDATE_PROCESS_CHECKOUT_UNVERIFIED": "Нельзя подтвердить, что работающий бот запущен из этой папки; updater его не остановит.",
    "BOT_UPDATE_FETCH_FAILED": "Не удалось получить обновления из origin/main.",
    "BOT_UPDATE_PREFLIGHT_BLOCKED": "Проверка после загрузки изменений остановила обновление.",
    "BOT_UPDATE_POST_STOP_PREFLIGHT_FAILED": "После штатной остановки повторная проверка проекта не прошла.",
    "BOT_UPDATE_REVISION_CHANGED_AFTER_STOP": "Версия проекта или целевая версия изменилась после остановки; fast-forward не выполнялся.",
    "BOT_UPDATE_STOP_FAILED": "Не удалось штатно остановить экземпляр бота из этой папки.",
    "BOT_UPDATE_BACKUP_FAILED": "Не удалось создать проверенную резервную копию; файлы не обновлены.",
    "BOT_UPDATE_BACKUP_PATH_MISSING": "Резервная копия не вернула подтверждённый путь; код не обновлён.",
    "BOT_UPDATE_BACKUP_VERIFY_FAILED": "Проверенная резервная копия не прошла повторную проверку; код не обновлён.",
    "BOT_UPDATE_PRE_MERGE_CHECK_FAILED": "Состояние проекта изменилось после создания копии; fast-forward не выполнялся.",
    "BOT_UPDATE_FAST_FORWARD_FAILED": "Git не смог безопасно применить обновление fast-forward.",
    "BOT_UPDATE_REVISION_MISMATCH_AFTER_MERGE": "После обновления Git не оказался на проверенной целевой версии.",
    "BOT_UPDATE_DEPENDENCIES_FAILED": "Не удалось установить или проверить Python-зависимости.",
    "BOT_UPDATE_COMPILE_FAILED": "Локальная проверка Python-кода завершилась ошибкой.",
    "BOT_UPDATE_RUNTIME_CHECK_FAILED": "Локальная проверка настроек запуска бота завершилась ошибкой.",
    "BOT_UPDATE_START_FAILED": "Обновление установлено, но фоновый запуск не состоялся.",
    "BOT_UPDATE_READINESS_NOT_CONFIRMED": "Процесс запуска запрошен, но готовность Telegram polling не подтверждена.",
}


def _parser():
    parser = argparse.ArgumentParser(
        description="Read-only preflight локального обновления Telegram-бота"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Проверить локальный план без изменений")
    check.add_argument("--check-only", action="store_true", required=True)
    check.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    update = commands.add_parser("update", help="Выполнить проверенное локальное обновление")
    update.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    update.add_argument("--no-start", action="store_true")
    return parser


def _format_result(result):
    lines = ["Проверка обновления (только чтение)"]
    current = result.get("current_revision")
    target = result.get("target_revision")
    lines.append("Текущая версия: " + (current or "недоступна"))
    lines.append("Ветка: " + (result.get("current_branch") or "не определена"))
    lines.append("Ожидаемая версия: " + (target or "origin/main недоступен"))
    process_state = result.get("process_state")
    if process_state:
        lines.append("Состояние своего бота: " + process_state)
    if result.get("already_current") is True:
        lines.append("Обновлений по локальной origin/main нет.")
    else:
        lines.append("Коммитов позади origin/main: " + str(result.get("behind_count", "—")))
    lines.append(
        "Изменились runtime-зависимости: "
        + ("да" if result.get("dependencies_needed") else "нет")
    )
    lines.append(
        "Перед обновлением потребуется проверенная резервная копия: "
        + ("да" if result.get("backup_required_before_update") else "нет")
    )
    lines.append(
        "Локальные origin refs могут устареть. Эта проверка не выполняла fetch."
    )
    lines.append(
        "План проверки: network=0, filesystem writes=0, Git mutations=0, lifecycle changes=0."
    )
    blockers = result.get("blockers") or []
    if blockers:
        lines.append("Обновление заблокировано:")
        for blocker in blockers:
            code = blocker.get("code", "BOT_UPDATE_PREFLIGHT_FAILED")
            lines.append("• " + _BLOCKER_TEXT.get(code, code))
            for path in blocker.get("paths", []):
                lines.append("  " + str(path))
            if blocker.get("path"):
                lines.append("  " + str(blocker["path"]))
    elif result.get("required_action"):
        lines.append("Перед обновлением нужно штатно остановить только этот экземпляр бота.")
    lines.append(
        "Результат: "
        + ("проверки пройдены; обновления не выполнялись." if not result.get("error")
           else "обновление сейчас выполнять нельзя.")
    )
    return "\n".join(lines)


def main(argv=None):
    arguments = _parser().parse_args(argv)
    project_root = Path(arguments.project_root).resolve(strict=False)
    load_dotenv(dotenv_path=project_root / ".env", override=False)
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if arguments.command == "check":
        service = BotUpdatePreflightService(
            project_root,
            lifecycle_token=token,
        )
        result = service.inspect()
        print(_format_result(result))
    else:
        service = BotUpdateRuntimeService(
            project_root,
            lifecycle_token=token,
        )
        result = service.update(no_start=arguments.no_start)
        print(_format_update_result(result))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("error") is False else 2


def _format_update_result(result):
    lines = ["Обновление Telegram-бота"]
    code = result.get("code")
    status = result.get("status")
    if result.get("error") is False:
        if status == "BOT_UPDATE_ALREADY_CURRENT":
            lines.append("Установлена актуальная версия; бот не останавливался и не перезапускался.")
        elif status == "BOT_UPDATE_COMPLETE_NO_START":
            lines.append("Код обновлён и проверен; бот оставлен остановленным по параметру -NoStart.")
        else:
            lines.append("Код обновлён; Telegram polling подтверждён как готовый.")
    else:
        lines.append(_BLOCKER_TEXT.get(code, "Обновление остановлено: " + str(code or "неизвестная ошибка")))
        for blocker in result.get("blockers", []):
            blocker_code = blocker.get("code", "BOT_UPDATE_PREFLIGHT_FAILED")
            lines.append("• " + _BLOCKER_TEXT.get(blocker_code, blocker_code))
            for path in blocker.get("paths", []):
                lines.append("  " + str(path))
            if blocker.get("path"):
                lines.append("  " + str(blocker["path"]))
        if result.get("bot_stopped") is True:
            lines.append("Бот подтверждённо остановлен; обновление не завершено.")
            if result.get("recovery_action"):
                lines.append(str(result["recovery_action"]))
            if result.get("recovery_command"):
                lines.append("Команда безопасной проверки: " + str(result["recovery_command"]))
        elif result.get("backup_path"):
            lines.append("Проверенная копия: " + str(result["backup_path"]))
    if result.get("current_revision"):
        lines.append("Установленная ревизия: " + str(result["current_revision"]))
    if result.get("target_revision"):
        lines.append("Целевая ревизия: " + str(result["target_revision"]))
    if result.get("backup_path"):
        lines.append("Проверенная копия: " + str(result["backup_path"]))
    if result.get("readiness_confirmed") is True:
        lines.append("Готовность: RUNNING на целевой ревизии в этой папке.")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
