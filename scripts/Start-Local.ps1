$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path '.venv/Scripts/autoclip.exe')) { throw 'Run scripts/Setup-Local.ps1 first.' }
try { $null = Invoke-RestMethod 'http://localhost:11434/api/tags' -TimeoutSec 5 }
catch { throw 'Open the Ollama app, then run this launcher again.' }
Write-Host 'Open http://localhost:8000 . Keep this window open; press Ctrl+C to stop.'
& .venv/Scripts/autoclip.exe serve --host 127.0.0.1 --port 8000
if ($LASTEXITCODE -ne 0) { throw "AutoClip exited with code $LASTEXITCODE." }
