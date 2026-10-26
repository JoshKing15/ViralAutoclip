param([string]$Model = 'llama3.1:8b')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location (Split-Path $PSScriptRoot -Parent)

function Run-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed (exit $LASTEXITCODE). Fix the error above and rerun setup." }
}

# Report hardware before downloading dependencies or models.
$ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
$gpuNames = (Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -join ', '
Write-Host "RAM: $ramGB GB | Graphics: $gpuNames"
if ($ramGB -lt 16) {
    Write-Warning 'The default 8B model can be slow or run out of memory on this PC. A 3B model is lighter but makes weaker highlight choices.'
}

$missing = @()
foreach ($tool in @('py', 'node', 'npm.cmd', 'ffmpeg', 'ffprobe', 'ollama')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { $missing += $tool }
}
if ($missing.Count -gt 0) {
    throw "Missing: $($missing -join ', '). Follow docs/LOCAL_WINDOWS.md, reopen PowerShell, and rerun."
}
Run-Checked 'py' @('-3.11', '-c', 'import sys; print(sys.version)')
Run-Checked 'node' @('-e', 'if(Number(process.versions.node.split(".")[0])<20)process.exit(1)')
$filters = (& ffmpeg -hide_banner -filters 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $filters -notmatch '\bass\b') { throw 'FFmpeg needs the ass subtitle filter. Install the full Gyan.FFmpeg build.' }

try { $null = Invoke-RestMethod 'http://localhost:11434/api/tags' -TimeoutSec 5 }
catch { throw 'Open the Ollama application first, then rerun this script.' }

if (-not (Test-Path '.venv/Scripts/python.exe')) { Run-Checked 'py' @('-3.11', '-m', 'venv', '.venv') }
$python = Join-Path (Get-Location) '.venv/Scripts/python.exe'
Run-Checked $python @('-c', 'import sys; assert sys.version_info[:2] == (3,11), "Use a Python 3.11 virtual environment"')
Run-Checked $python @('-m', 'pip', 'install', '-e', '.')
Push-Location frontend
try {
    Run-Checked 'npm.cmd' @('ci', '--no-audit', '--no-fund')
    Run-Checked 'npm.cmd' @('run', 'build')
} finally { Pop-Location }
Run-Checked 'ollama' @('pull', $Model)

# Use the application's loader/saver so unrelated settings and secrets survive.
$configure = @'
import sys
from autoclip import config
s = config.load()
s.active_provider = 'ollama'
s.provider('ollama').model = sys.argv[1]
s.provider('ollama').base_url = 'http://localhost:11434'
s.whisper.model = 'base'
s.whisper.diarization = False
s.clips.max_clips = 3
config.save(s)
print('Local Ollama configured; Whisper base; up to 3 clips. No paid provider selected.')
'@
Run-Checked $python @('-c', $configure, $Model)
Run-Checked '.venv/Scripts/autoclip.exe' @('doctor')
Write-Host 'Setup complete. Run: powershell -ExecutionPolicy Bypass -File .\scripts\Start-Local.ps1'
