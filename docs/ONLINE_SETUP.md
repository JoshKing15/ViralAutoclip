# ViralAutoclip online: private single-owner deployment

This setup runs the existing React UI, Python worker, FFmpeg, and transcription
on a Linux server. Your phone only needs a browser. Caddy provides HTTPS and
password protection for every route. It is a personal workspace: anyone given
the password can see every video and change settings. It is not a multi-user SaaS.

## Before provisioning

You need a Linux server with Docker Engine and the Compose plugin, and a domain
or subdomain whose DNS points to the server. As an initial sizing estimate, use
4 CPU cores, 8 GB RAM and 50 GB disk for short source videos, then measure memory,
disk use and processing speed on your footage. This is not a benchmark or a
minimum guarantee; CPU transcription and rendering can be slow. GPU is optional.
Hosting, storage, bandwidth and an external AI provider can incur charges.

Allow inbound TCP 80 and 443 and restrict SSH access. Do not open port 8000.
The server needs outbound internet for image builds, models, video downloads,
certificate issuance and your selected AI provider.

## Install

```bash
git clone https://github.com/JoshKing15/ViralAutoclip.git
cd ViralAutoclip/docker/cloud
cp .env.example .env
docker run --rm -it caddy:2-alpine caddy hash-password
```

The last command prompts for your chosen password without placing it in shell
history. Put the resulting hash in `.env`, keeping its single quotes. Set
`CLIP_DOMAIN` and `CLIP_USERNAME`. Never commit `.env`, passwords or API keys.

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 proxy app
```

Open `https://YOUR_HOSTNAME`. The browser asks for your username and password.
DNS must resolve correctly and ports 80/443 must be reachable for certificates.
The backend health check stays internal; external health requests also require
the password. Plain HTTP redirects to HTTPS.

## Configure and verify

1. In the protected app, configure a supported AI provider in Settings → Keys.
   The cloud Compose file does not include Ollama; use an external provider for
   this first deployment. Only configure keys through your HTTPS app.
2. Upload a small talking-head video and generate a clip. First processing can
   take longer while models download. Check audio, subtitle timing, crop and
   download from both desktop and phone.
3. Test a public YouTube video you may process. Cloud IPs can encounter bot
   checks. A server cannot read the browser cookies on your phone or PC using
   the existing “cookies from browser” setting. Use upload if the link fails.
4. In a private browser window, verify the UI, `/api/health`, `/docs` and a
   generated media URL require authentication. Verify no service publishes
   port 8000 in `docker compose ps`.

The current upstream import flow supports YouTube and uploads. Facebook and X
imports are not implemented or verified by this deployment change. Highlight
selection uses speech transcripts; it is not a guarantee of visual highlights
or viral performance. This deployment has not been tested on a live server.

## Storage, updates and limits

App data, settings and clips persist in `app-data`; models persist in
`model-cache`; certificates persist in the Caddy volumes. Back up app-data
before updates (stop the app for a consistent database backup) and protect the
backup because settings can contain API credentials. Do not use
`docker compose down -v` unless you intend to delete the stored data.

The proxy limits an individual request body to 2 GB. It does not limit total
disk consumption, source duration or CPU use. Start with small videos, monitor
disk space, and remove unneeded sources and exports. Do not share the login
publicly. A public multi-user launch needs user isolation, quotas, stronger job
controls and a separate review of the upstream app's local-file capabilities.

After a reviewed update, run `git pull --ff-only` at the repository root and
`docker compose up -d --build` from `docker/cloud`. These commands do not erase
the named data volumes. To stop without deleting data: `docker compose down`.
