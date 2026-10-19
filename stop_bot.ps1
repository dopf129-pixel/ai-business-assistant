$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$VenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    throw "Virtual environment not found. Run .\start_bot.ps1 once to set up the local environment."
}

$env:PYTHONPATH = Join-Path $PSScriptRoot "app"
& $VenvPython -m telegram_bot_control stop
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
