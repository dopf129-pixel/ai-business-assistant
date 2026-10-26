param(
    [switch]$CheckOnly,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if ($CheckOnly -and $NoStart) {
    throw "Параметры -CheckOnly и -NoStart нельзя использовать вместе."
}

if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    throw "Virtual environment not found. Run .\start_bot.ps1 once to set up the local environment."
}

$PreviousPythonPath = $env:PYTHONPATH
$PreviousPowerShellExecutable = $env:APP_POWER_SHELL_EXECUTABLE
try {
    $env:PYTHONPATH = Join-Path $ProjectRoot "app"
    $env:APP_POWER_SHELL_EXECUTABLE = (Get-Process -Id $PID).Path
    if ($CheckOnly) {
        & $VenvPython -m bot_update check --check-only --project-root $ProjectRoot
    }
    elseif ($NoStart) {
        & $VenvPython -m bot_update update --no-start --project-root $ProjectRoot
    }
    else {
        & $VenvPython -m bot_update update --project-root $ProjectRoot
    }
    $CommandExitCode = $LASTEXITCODE
}
finally {
    $env:PYTHONPATH = $PreviousPythonPath
    $env:APP_POWER_SHELL_EXECUTABLE = $PreviousPowerShellExecutable
}

exit $CommandExitCode
