import { useEffect, useState } from 'react'
import { api, type PostingDraft } from '../api'

export function PostingEditor({ clipId }: { clipId: string }) {
  const [draft, setDraft] = useState<PostingDraft | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  useEffect(() => {
    let active = true
    api.getPosting(clipId).then((value) => { if (active) setDraft(value) }).catch(() => undefined)
    return () => { active = false }
  }, [clipId])
  const generate = async () => {
    setBusy(true); setMessage('Generating with your selected AI provider…')
    try { setDraft(await api.generatePosting(clipId)); setMessage('Draft generated. Review and edit before using.') }
    catch (error) { setMessage(String(error)) }
    finally { setBusy(false) }
  }
  const save = async () => {
    if (!draft) return
    setBusy(true)
    try { setDraft(await api.savePosting(clipId, draft)); setMessage('Draft saved.') }
    catch (error) { setMessage(String(error)) }
    finally { setBusy(false) }
  }
  const copy = async () => {
    if (!draft) return
    try {
      await navigator.clipboard.writeText([
        draft.youtube_title, draft.description, draft.facebook_caption,
        draft.hashtags.join(' '), 'Commentary talking points:', ...draft.commentary_points,
        draft.source_credit,
      ].join('\n\n'))
      setMessage('Posting package copied.')
    } catch { setMessage('Clipboard unavailable. You can select and copy the text below.') }
  }
  const textFields = ['youtube_title', 'description', 'facebook_caption', 'source_credit'] as const
  const labels = { youtube_title: 'YouTube title', description: 'YouTube description', facebook_caption: 'Facebook caption', source_credit: 'Source credit' }
  return <section className="space-y-3 border-t border-ink-800 pt-6">
    <p className="eyebrow">Posting package · draft</p>
    <p className="text-xs text-ink-400">Generate text and commentary ideas from this clip. Nothing is posted automatically.</p>
    <button className="btn btn-ghost" disabled={busy} onClick={generate}>
      {busy ? 'Working…' : draft ? 'Regenerate draft' : 'Generate posting package'}
    </button>
    {message && <p role="status" className="text-xs text-ink-300">{message}</p>}
    {draft && <>
      {textFields.map((key) => <label className="block" key={key}>
        <span className="eyebrow">{labels[key]}</span>
        <textarea className="field mt-1 text-sm" rows={key === 'youtube_title' ? 2 : 3}
          maxLength={key === 'youtube_title' ? 100 : key === 'description' ? 5000 : key === 'facebook_caption' ? 3000 : 2000}
          value={draft[key]} onChange={(e) => setDraft({ ...draft, [key]: e.target.value })} />
      </label>)}
      <label className="block"><span className="eyebrow">Hashtags (one per line)</span>
        <textarea className="field mt-1 text-sm" rows={3} value={draft.hashtags.join('\n')}
          onChange={(e) => setDraft({ ...draft, hashtags: e.target.value.split('\n') })} />
      </label>
      <label className="block"><span className="eyebrow">Your commentary talking points (one per line)</span>
        <textarea className="field mt-1 text-sm" rows={5} value={draft.commentary_points.join('\n')}
          onChange={(e) => setDraft({ ...draft, commentary_points: e.target.value.split('\n') })} />
      </label>
      <div className="flex gap-3"><button className="btn btn-primary" disabled={busy} onClick={save}>Save draft</button>
        <button className="btn btn-ghost" disabled={busy} onClick={copy}>Copy package</button></div>
    </>}
  </section>
}
