# Personal Windows setup: local AI, no paid API or hosting

This uses your Windows PC to run AutoClip, Whisper transcription and Ollama
highlight selection. No OpenAI key, ChatGPT Plus integration, server or domain is
needed. Software and model downloads require internet and several GB of data.
Local uploads can be processed without cloud AI after models are downloaded.
Your PC stays on while processing. This setup has not been run on Windows yet.

## 1. Install the prerequisites

In PowerShell, run the commands below one at a time. Skip software already
installed. These are free packages; installers may request Windows permission.

```powershell
winget install --exact --id Git.Git
winget install --exact --id Python.Python.3.11
winget install --exact --id OpenJS.NodeJS.LTS
winget install --exact --id Gyan.FFmpeg
```

Install Ollama from https://ollama.com/download/windows and open it.
Close and reopen PowerShell so newly installed programs are on PATH.
Use the full FFmpeg package above: captions require its `ass` filter.

## 2. Get this branch and run setup

For a new download:

```powershell
cd $env:USERPROFILE
git clone --branch local-windows-setup https://github.com/JoshKing15/ViralAutoclip.git
cd ViralAutoclip
powershell -ExecutionPolicy Bypass -File .\scripts\Setup-Local.ps1
```

For an existing checkout, first commit or stash your own changes, then fetch
and switch to `local-windows-setup` rather than cloning into the same directory.

The script reports RAM/graphics, checks tools, creates a Python 3.11 environment,
builds the UI, downloads `llama3.1:8b`, selects Ollama and runs the app doctor.
It stops on errors and can be rerun. It preserves unrelated configuration but
selects Whisper `base`, disables optional diarization and sets a maximum of
three clips. These defaults reduce the initial processing load.

16 GB RAM is a suggested starting point, not a hardware guarantee. CPU-only
works more slowly. If the 8B model cannot run, try the lighter model below;
expect weaker highlight choices and check each result yourself:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Setup-Local.ps1 -Model qwen2.5:3b
```

## 3. Start and test

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Start-Local.ps1
```

Open http://localhost:8000 . Upload a 1-3 minute spoken video first, generate a
clip, and check the start/end, audio, crop and subtitles. Whisper downloads its
model on first use, so that first test also needs internet. Keep the terminal
open; Ctrl+C stops the app. Later starts need only Ollama and Start-Local.ps1.

The initial launcher binds only to this PC. Phone access is not enabled because
upstream has no login; do not forward port 8000 on your router or expose it
through a public tunnel. A protected phone-access setup can be added separately.

YouTube is supported but downloads may hit platform checks; upload is the
fallback. Facebook and X imports still need implementation. Highlight selection
uses speech transcripts; it cannot reliably find silent visual action or promise
viral clips. No sample or demo results are substituted for real processing.

If setup fails, send the final error text plus the RAM/graphics line. Do not
send browser cookies, passwords or API keys. Data normally lives in
`$env:USERPROFILE\.autoclip` (or your existing `AUTOCLIP_HOME`), not the repository.
