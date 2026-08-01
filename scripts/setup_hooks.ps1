# Install git pre-push hook for AI log submission (Windows PowerShell).
# Run once after cloning: powershell -ExecutionPolicy Bypass -File scripts\setup_hooks.ps1

$ErrorActionPreference = 'Stop'

$HookFile = '.git/hooks/pre-push'
$HookPath = [System.IO.Path]::GetFullPath($HookFile)
$HookDir = [System.IO.Path]::GetDirectoryName($HookPath)

# Git on Windows runs hooks via Git Bash, so the hook body must be bash.
# $HookBody = @'
# #!/usr/bin/env bash
# # Pre-push: sweep recent Antigravity / Gemini prompts, then submit AI logs.
# bash scripts/_pyrun.sh scripts/log_antigravity.py --auto || true
# bash scripts/_pyrun.sh scripts/submit_log.py || true
# exit 0
# '@
$HookBody = "#!/usr/bin/env bash`n# Pre-push: sweep recent Antigravity / Gemini prompts, then submit AI logs.`nbash scripts/_pyrun.sh scripts/log_antigravity.py --auto || true`nbash scripts/_pyrun.sh scripts/submit_log.py || true`nexit 0`n"
# Ensure the hook directory exists. The pre-push file is normally absent after
# cloning because Git hooks are local files and are not tracked by the repo.
if (-not (Test-Path -LiteralPath $HookDir)) {
    New-Item -ItemType Directory -Force -Path $HookDir | Out-Null
}

$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($HookPath, $HookBody, $Utf8NoBom)
Write-Host "[ai-log] Git pre-push hook installed."

if (-not (Test-Path .ai-log)) { New-Item -ItemType Directory -Path .ai-log | Out-Null }
if (-not (Test-Path .ai-log/.gitkeep)) { New-Item -ItemType File -Path .ai-log/.gitkeep | Out-Null }

Write-Host "[ai-log] Setup complete. Configure AI_LOG_SERVER in your .env file."
