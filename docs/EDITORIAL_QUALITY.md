# Choosing complete podcast clips

New jobs in the web UI default to Complete podcast story: 45–120 seconds,
vertical video, full picture fit and clean lower captions. News discussion uses
60–180 seconds and landscape video. Quick highlights suggests 20–60 seconds.
These are generic editorial presets, not verified reproductions of a particular
channel. All suggested lengths and layouts can be adjusted in options.

The story prompt asks for a complete story, question and answer, disagreement or
punchline. Transcript time markers help the model choose actual durations.
Editorial quality check reviews the final trimmed excerpt a second time, scores
hook, context, payoff and specificity, and requires matching quotes near the
opening and ending. Out-of-window indices are rejected instead of clamped.
Candidates can fail, so the requested clip count is a maximum, not a quota.
Review and failed-job screens show the assessment and rejected candidates.

The assessment is AI judgement, not a prediction of views or a fact check.
Transcript errors, mistranslations, missing visual context and weak source
material can still produce poor results. Listen to the finished excerpt and
correct captions before posting. If a meaningful answer needs longer, increase
the maximum duration rather than demanding an incomplete short clip.

The optional second review adds local AI calls. Ollama quality mode requests an
8192-token context and limits response generation to 1200 tokens; it can use more
RAM/VRAM and take longer on a laptop GPU. Completed reviews are cached per
provider, model and excerpt. Errors fail visibly and retry reuses completed
reviews. Turning off the checkbox skips this extra pass.

Start a NEW job to use the presets. Retrying an old job preserves its original
settings. Updating the code requires rebuilding the frontend and restarting the
server. For an exact visual reference match, provide a representative short
video from each reference and one poor app export; channel URLs alone may not
be accessible for inspection.
