$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$VenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$EnvFile = Join-Path $PSScriptRoot ".env"
$Requirements = Join-Path $PSScriptRoot "requirements.txt"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE: $FilePath $($Arguments -join ' ')"
    }
}

if (-not (Test-Path $VenvPython)) {
    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if (-not $PyLauncher) {
        throw "Python launcher 'py' was not found. Install Python 3.12, then run .\start_bot.ps1 again."
    }

    Invoke-Checked "py" "-3.12" "-c" "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)"
    Invoke-Checked "py" "-3.12" "-m" "venv" ".venv"
    Invoke-Checked $VenvPython "-m" "pip" "install" "--upgrade" "pip"
    Invoke-Checked $VenvPython "-m" "pip" "install" "-r" $Requirements
}
else {
    & $VenvPython -c "import telegram, cryptography, dotenv" *> $null
    if ($LASTEXITCODE -ne 0) {
        Invoke-Checked $VenvPython "-m" "pip" "install" "-r" $Requirements
    }
}

if (-not (Test-Path $EnvFile)) {
    $MasterKey = & $VenvPython -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode('ascii'))"
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($MasterKey)) {
        throw "Failed to generate OZON_CREDENTIAL_MASTER_KEY."
    }

    @"
# Local-only secrets. This file is gitignored. Never send it to anyone.
TELEGRAM_BOT_TOKEN=
OZON_CREDENTIAL_MASTER_KEY=$MasterKey
AI_ASSISTANT_STORAGE_ROOT=.runtime-data
"@ | Set-Content -Path $EnvFile -Encoding UTF8

    Write-Host "Created local .env with a private Ozon credential master key."
    Write-Host "Open .env, set TELEGRAM_BOT_TOKEN to your own bot token, save it, then run .\start_bot.ps1 again."
    exit 2
}

$env:PYTHONPATH = Join-Path $PSScriptRoot "app"
Invoke-Checked $VenvPython "-m" "telegram_api_bot"
