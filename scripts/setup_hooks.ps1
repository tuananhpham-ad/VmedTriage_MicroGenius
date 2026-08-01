# Install git pre-push hook for AI log submission (Windows PowerShell).
# Run once after cloning: powershell -ExecutionPolicy Bypass -File scripts\setup_hooks.ps1
#

$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
$RepoRoot = Resolve-Path (Join-Path $ScriptDir '..')

$HookPath = Join-Path $RepoRoot '.git/hooks/pre-push'
$HookDir = Split-Path $HookPath -Parent

$HookBody = "#!/usr/bin/env bash`n# Pre-push: sweep recent Antigravity / Gemini prompts, then submit AI logs.`ncd `"`$(git rev-parse --show-toplevel)`" || exit 0`nbash scripts/_pyrun.sh scripts/log_antigravity.py --auto || true`nbash scripts/_pyrun.sh scripts/submit_log.py || true`nexit 0`n"

# Ensure the hook directory exists. The pre-push file is normally absent after
# cloning because Git hooks are local files and are not tracked by the repo.
if (-not (Test-Path -LiteralPath $HookDir)) {
    New-Item -ItemType Directory -Force -Path $HookDir | Out-Null
}

$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($HookPath, $HookBody, $Utf8NoBom)

Write-Host "[ai-log] Git pre-push hook installed."

$AiLogDir = Join-Path $RepoRoot '.ai-log'
$GitKeep = Join-Path $AiLogDir '.gitkeep'

if (-not (Test-Path -LiteralPath $AiLogDir)) {
    New-Item -ItemType Directory -Path $AiLogDir | Out-Null
}

if (-not (Test-Path -LiteralPath $GitKeep)) {
    New-Item -ItemType File -Path $GitKeep | Out-Null
}

Write-Host "[ai-log] Setup complete. Configure AI_LOG_SERVER in your .env file."