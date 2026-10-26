# Короткая памятка по ежедневной эксплуатации

Команды запускаются из PowerShell в корне проекта. Перед остановкой, резервным копированием или обновлением проверьте, что открыта нужная папка проекта. Команды ниже независимы: копируйте каждый блок отдельно.

## Проверить состояние

```powershell
.\status_bot.ps1
```

`RUNNING` означает, что polling готов. Проверка конфигурации локальная и не подтверждает доступ к Ozon. Ошибки источника и неполные финансовые данные смотрите в диагностике конкретного отчёта.

Безопасно проверить локальные настройки запуска можно отдельно:

```powershell
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path (Get-Location) 'app'
    & .\.venv\Scripts\python.exe -m runtime_healthcheck
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}
```

Эта проверка не делает сетевые запросы, не читает продавецкую базу и не меняет данные.

## Остановить и создать backup

```powershell
.\stop_bot.ps1
```

```powershell
.\backup_bot.ps1
```

Проверить архив по пути, который напечатала команда backup:

```powershell
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path (Get-Location) 'app'
    & .\.venv\Scripts\python.exe -m bot_backup verify ".\<путь-к-архиву>.zip"
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}
```

Backup не содержит `.env`, токен Telegram, ключ шифрования `OZON_CREDENTIAL_MASTER_KEY`, открытые API-ключи Ozon, логи и Git checkout. SQLite-копия включает Client ID Ozon и зашифрованные записи API-ключей. Для восстановления доступа к Ozon понадобится исходный `OZON_CREDENTIAL_MASTER_KEY`; храните его отдельно от backup. Считайте архив конфиденциальными данными.

## Проверить восстановление без записи

Выберите новый путь, которого ещё нет, вне текущей папки проекта и хранилища:

```powershell
.\restore_bot.ps1 -ArchivePath ".\.local-backups\<архив>.zip" -TargetDirectory ([System.IO.Path]::GetFullPath((Join-Path (Get-Location) '..\restore-drill'))) -CheckOnly
```

Сама проверка ничего не распаковывает. Для создания отдельной копии данных повторите команду без `-CheckOnly`. Она не переключает checkout, не меняет `.env` и не запускает бота. Рабочие данные восстановленной копии следует проверять только в отдельном checkout с отдельным `AI_ASSISTANT_STORAGE_ROOT`.

## Обновить

### Первый переход со старого checkout

В старой копии `update_bot.ps1` может ещё отсутствовать. До получения этой версии не запускайте `-CheckOnly` или `-NoStart`: старый checkout не умеет их обработать. Сначала проверьте ветку:

```powershell
git branch --show-current
```

Затем проверьте незакоммиченные и untracked файлы:

```powershell
git status --short
```

Если ветка — `main`, список изменений пуст и бот остановлен штатным для этой версии способом, получите fast-forward обновление, которое добавит актуальный updater:

```powershell
git pull --ff-only origin main
```

После успешного обновления продолжайте с `.\update_bot.ps1 -CheckOnly` ниже. Этот шаг не запускает бота.

Если ветка отличается от `main` или `git status --short` показывает файлы, не выполняйте pull и не пытайтесь освободить checkout командами очистки. Сначала сохраните tracked diff и список untracked файлов в соседнюю папку вне проекта:

```powershell
$preserveRoot = Join-Path (Split-Path -Parent (Get-Location)) ("Ai ассистент-local-backup-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $preserveRoot
$patchPath = Join-Path $preserveRoot 'tracked.patch'
git diff --binary HEAD "--output=$patchPath"
$untrackedPath = Join-Path $preserveRoot 'untracked-list.txt'
git ls-files --others --exclude-standard | Set-Content -LiteralPath $untrackedPath -Encoding utf8
```

В patch могут быть приватные данные: храните его локально, не прикладывайте к задаче и не отправляйте в GitHub. Просмотрите список untracked и вручную скопируйте только нужные файлы в соседнюю папку, сохраняя относительные пути. Не переносите `.env`, runtime storage, JSON/SQLite данные или логи в Git. Остановитесь и разберите сохранённые изменения отдельно; не удаляйте и не перезаписывайте их автоматически.

Если fast-forward уже был прерван из-за локального конфликта, Git оставляет текущий checkout без слияния. Проверьте `git status --short`, сохраните необходимые локальные файлы вне конфликтующих путей и продолжайте только после их разбора. Не повторяйте pull до разрешения конфликта.

### Обычное обновление через штатный updater

Сначала запустите проверку без изменений:

```powershell
.\update_bot.ps1 -CheckOnly
```

Если проверка разрешает обновление, выполните его штатным updater:

```powershell
.\update_bot.ps1
```

Чтобы обновить код и оставить процесс остановленным:

```powershell
.\update_bot.ps1 -NoStart
```

Updater не удаляет локальные изменения, не делает stash/reset/clean и не завершает Python принудительно. Если он сообщает об остановленном боте и незавершённом обновлении, сначала сохраните указанный путь проверенного backup и выполните read-only preflight:

```powershell
.\update_bot.ps1 -CheckOnly
```

Не запускайте `git reset --hard`, `git clean` или автоматическое восстановление базы. При локальном конфликте сначала получите обзор:

```powershell
git status --short
```

```powershell
git diff --stat
```

Сохраните локальные файлы и backup, затем разрешайте конфликт в отдельной рабочей копии или обратитесь за помощью с выводом этих двух команд. Не отправляйте `.env`, SQLite/JSON базы и сырые отчёты.

## Если Ozon credentials не расшифровываются

Не создавайте новый master key и не удаляйте текущую папку `.runtime-data`. Найдите исходный `OZON_CREDENTIAL_MASTER_KEY` в своём защищённом месте и восстановите его в локальный `.env`. Если исходный ключ утрачен, ciphertext нельзя расшифровать; потребуется заново подключить Ozon после сохранения backup и проверки исходной базы. Сам ключ не присылайте и не вставляйте в PowerShell-команду.

## Если нужен безопасный диагностический материал

В боте откройте диагностику проблемного расчёта и сформируйте `📦 Сохранить диагностику`. Экспорт ограничен allowlist и скрывает сырые ответы API, суммы, названия товаров и исходные идентификаторы. Перед отправкой откройте JSON и проверьте, что в нём нет дополнительных пользовательских полей.

Отдельно можно приложить текст `status_bot.ps1`, если он показывает только revision, mode, lifecycle state, safe reason code и совпадение папки проекта. Не присылайте `.env`, API-ключи, токены, базу, backup и исходные отчёты.

## Ограничения проверки

Локальные synthetic проверки подтверждают ограниченные сценарии и восстановление на тестовых каталогах. Они не доказывают работу реального Telegram polling, доступность Ozon, полноту финансовых источников или успешность длительного production-периода. Для фактического наблюдения используйте отдельный журнал 24–72 часа после собственного запуска и отмечайте только безопасные статусы/время.
