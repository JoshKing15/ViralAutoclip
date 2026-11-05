# Learn from reference clips

Open **Reference styles** in the app. Add 1–5 finished clips (ideally 3–5 from
one channel) using individual YouTube video URLs or uploads. Each reference must
be at most 20 minutes. Full podcast episodes and channel URLs are not the
right input: this feature studies the editor's final choices. YouTube reference
imports check metadata before downloading; bot checks and unavailable videos
can still block downloads. Upload a local copy when needed.

Choose a preset name and Analyse references. Analysis runs in the background;
the page polls progress, so refreshes do not lose the running analysis. After a
server restart an interrupted analysis can be retried. Completed measurements,
transcripts and visual results are reused. Only one reference analysis runs at
a time. Run it while ordinary clip jobs are idle on a small GPU.

The app measures duration, aspect ratio and image-change scene cuts with FFmpeg,
transcribes the speech with your configured Whisper model, and asks your
configured text provider to describe reusable opening/context/ending patterns.
No training or external subscription is required when Ollama is the active
provider. Initial Whisper model downloads may still be necessary.

## Optional local visual observations

Install the separately selected vision model in PowerShell:

```powershell
ollama pull qwen2.5vl:3b
```

Enable visual observations before starting the analysis. This uses the configured
Ollama base URL and sends three resized frames per reference to that model. It
may be slow on an RTX 3050 laptop. Calls unload the vision model after each
response to reduce persistent GPU memory use. Model installation is never
performed automatically. Missing model, HTTP errors and malformed responses
appear as failed analysis; retry reuses completed reference results.

Still-frame observations can suggest approximate framing and caption treatment.
They cannot establish zoom animation, exact fonts, music, every camera cut or a
channel's full style. Without vision, layout/caption suggestions default to full
picture fit and clean lower captions; no visual analysis is claimed.

## Review, save and apply

Inspect the measurements, opening and ending text, summary and optional visual
observations. Edit the editorial preferences and suggested length, aspect ratio,
framing and caption template, then **Review and save preset**. Suggested duration
is 70–130% of the median reference length; aspect ratio uses the first reference.
Mixed formats should be analysed as separate presets. Caption choices approximate
existing templates rather than recreate an exact font or logo.

On **New**, choose the saved reference preset. This copies the suggested options;
you can adjust them before starting. Its editorial preferences are saved inside
the job and passed into highlight selection and the second quality review.
Changing a preset later does not alter an existing job. Retry preserves the
job's original settings. Start a new job to use a newer preset.

Scene-change statistics are evidence only. Exports do not automatically insert
cuts, remove pauses or add zooms to mimic the cut rate. The feature is an editable
reference-derived preset, not an automatic style clone or a promise of views.
Audio-only transcription cannot capture gestures, reaction shots or translation
errors, so watch the output before posting.

## Longer references

References up to 20 minutes (1200 seconds) are accepted. Longer transcripts are
read in batches of at most 400 words, then condensed into a per-reference
structure summary before the final preset is generated. All spoken text is
covered by the batches; individual summaries can still miss details. Completed
AI summaries are cached by transcript, provider and model. Progress reports the
current section. Longer references take more time, especially on a laptop.
Three optional frames still sample 10%, 50% and 90% of each video.

Suggested output lengths and editable duration controls now extend to 1200
seconds. A preset derived from a 20-minute reference can therefore suggest a
longer discussion clip. Choosing a short-form Clip format afterward replaces
those suggested lengths. Start a new job to use revised settings.

## Progress and estimates

YouTube reference downloads run as background tasks. The page polls a persisted
status: metadata check, transfer or processing. Where yt-dlp provides size and
speed, it shows current stream percentage, MB, MB/s and estimated seconds left.
Video and audio streams can download separately, so the percentage can reset
when a new stream starts. Stream ETA excludes merging, subsequent streams and AI
analysis. Unknown sizes and stalled transfers display no invented ETA. A last
update timer makes inactivity visible.

Download IDs and pending source selections are kept in this browser so refreshing
the page reconnects to the transfer. A server restart marks an interrupted
transfer failed, with instructions to add the link again. Existing downloads
started with an older app version cannot acquire progress retroactively.

Reference analysis shows elapsed time and its current stage, audio transcription
percentage, section counts and completed visual frames. Overall AI finish time
is unknown; hardware, model loading and transcript size vary too much for a
reliable countdown. Retry starts a fresh elapsed timer and reuses saved work.
