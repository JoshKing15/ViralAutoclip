# Long podcast mode

For new YouTube sources, the New page now defaults to **Long podcast mode**.
Uncheck it to keep the full-video workflow. Uploads are unchanged.

1. Start checks YouTube metadata only, then creates a background job.
2. The job tries the original-language automatic caption track in JSON3 format.
   It accepts measured per-word offsets, not estimated sentence timing. If a
   usable track is unavailable, it downloads audio only and transcribes it with
   your selected local Whisper model. You can select a language in Advanced
   options; otherwise the original caption language or Whisper detection is used.
3. The entire transcript is scanned in overlapping windows. Ollama requests stay
   sequential and use smaller windows. Successful window responses are saved to
   disk; retries reuse them unless the model, prompt configuration or window
   text changes. Failure of every window is reported as an analysis failure,
   rather than suggesting the episode contained no highlights.
4. After ranking, only the selected video ranges (plus two seconds of padding)
   are requested through yt-dlp/FFmpeg. Each range is checked for audio, video
   and expected duration before being cached. There is no automatic full-video
   fallback when a range fails.
5. Face framing and exports use the downloaded sections. Stored clip times and
   transcripts remain relative to the episode; the player/exporter translate
   those times into each section's clock. Preview, caption edits, re-export and
   trims inside the fetched section are supported. Extending a trim beyond the
   fetched padding is rejected rather than producing a mistimed export.

## Updating an existing Windows checkout

Stop AutoClip with Ctrl+C, then run from the repository in PowerShell:

```powershell
git pull --ff-only
Push-Location frontend
npm.cmd ci --no-audit --no-fund
npm.cmd run build
Pop-Location
& ".\.venv\Scripts\autoclip.exe" serve --host 127.0.0.1 --port 8000
```

Refresh the browser and create a **new job from the YouTube link**, with Long
podcast mode checked. Existing sources retain their original full-video path;
retrying an old job does not convert it into a deferred source. There are no
new Python dependencies and no database migration for this feature.

Start with three clips maximum. Watch the stage messages for caption checks,
audio-only download, transcript analysis and selected-video downloads. These
are stage progress estimates, not a prediction of remaining time.

## Limits and verification

Three hours of local transcription or local LLM analysis can still take a long
time. This change reduces video transfer/processing; it does not make local AI
instant. Downloads depend on YouTube access, yt-dlp, formats and server range
support. Some formats require extra fragments or substantial transfer even
when a section is requested. No bandwidth or speed guarantee is made.

Completed videos only: live/upcoming streams are rejected. Only YouTube links
are covered; Facebook/X imports are not added here. Automatic captions can be
inaccurate, especially during language changes or overlapping speech. Review
subtitle text and the clip's original context before sharing.

Automated tests cover metadata-only ingestion, captions/audio fallback, requested
download ranges, cached retries, preserved episode indices, local-clock preview
and exports, and an actual FFmpeg render. Real YouTube range downloading and
Windows/GPU performance need a live test on the user's PC. Test downloads use
mocks, not fabricated claims of successful YouTube processing.
