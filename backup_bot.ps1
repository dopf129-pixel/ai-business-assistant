$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$VenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    throw "Virtual environment not found. Run .\start_bot.ps1 once to set up the local environment."
}

$env:PYTHONPATH = Join-Path $PSScriptRoot "app"
& $VenvPython -m bot_backup backup --project-root $PSScriptRoot
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
