# Topic, framing, posting drafts and progress

These additions work with the existing local Ollama setup. No paid API or
hosting is required. Nothing posts to YouTube or Facebook automatically.

## Update Windows

Stop the app with Ctrl+C, then run in the existing checkout:

```powershell
git pull --ff-only
Push-Location frontend
npm.cmd ci --no-audit --no-fund
npm.cmd run build
Pop-Location
& ".\.venv\Scripts\autoclip.exe" serve --host 127.0.0.1 --port 8000
```

Refresh the browser. No new Python dependency or database migration is needed.

## Select relevant moments

On **New**, enter a short description under **Topics to look for**. Example:
`Relationships, money, dating expectations`. Leave blank for general highlights.
This instruction is passed to the selected model for every transcript window.
Topic relevance is model-assisted, not a deterministic filter. The model may
return no matches; review context before using any selection.

New-job defaults are three clips, 30–60 seconds, without optional diarization.
Advanced options allow changing them. Topic and framing choices are saved with
the job; changing a topic requires a new job. Analysis checkpoints include the
topic so results aren't reused across different selection instructions.

## Choose framing

Choose framing in Advanced options, or change each clip in Review:

| Choice | Behaviour |
| --- | --- |
| Auto | Existing speaker/face tracking and wide-frame fallback. |
| Centre | Fixed centre crop. |
| Full picture | Entire picture over a blurred copy of the source. |
| Two panels | Left source half above right source half, cropped to fill each panel. |

Two panels is a manual layout for side-by-side guests, not identity-aware
speaker selection. It can crop faces if guests are not positioned in those
halves; watch the preview and change modes if needed. Auto tracking still
depends on the footage and available models. WhisperX speaker labels remain
optional and require their own installation.

Preview and exports share the saved framing plan. Changing a ratio rebuilds the
plan for that shape. Browser captions approximate the final ASS captions. Full
picture and two-panel previews draw the same playing video on a canvas, so
there is only one audio/playback clock. Updating framing doesn't overwrite old
export files until you click Export. Check the newest export after changes.

## Prepare a posting package

In Review, click **Generate posting package**. The app uses the clip transcript
(including saved text edits), source title and chosen topic to request a draft
from the job's AI provider. For the local setup, this is Ollama on your PC.

The draft includes a YouTube title/description, Facebook caption, hashtags,
commentary talking points and a source credit built from the registered source.
Edit fields, click **Save draft**, or **Copy package**. Generation is on demand
to avoid slowing down every clip render. Saved drafts survive restarts. Trimming
or saving new caption text invalidates the old draft so it can be regenerated.
AI output needs factual and editorial review; source credit isn't permission
to reuse footage, and a generated commentary outline is not recorded commentary.

## Understand progress

The progress page shows elapsed wall time for the current attempt, completed
transcript sections such as `Analysed section 7/40`, reused checkpoint indicators,
and downloaded MB where yt-dlp reports transfer bytes. The last activity message
is saved for page refreshes. Unknown transfer totals aren't fabricated. FFmpeg
section fetching may not report bytes through yt-dlp; in that case the selected
video number remains visible. Percentages remain estimates, not time remaining.

Automated tests cover request settings, topic prompts/checkpoints, saved drafts,
framing persistence, refreshed progress, and actual FFmpeg renders of explicit
layouts. Windows playback, real podcast selection quality and local model draft
quality still need review on the user's machine.
