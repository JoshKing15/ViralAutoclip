import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type ReferenceStyle, type JobSettingsOverrides } from '../api'

export function ReferenceStyles() {
  const [profiles, setProfiles] = useState<ReferenceStyle[]>([])
  const [selected, setSelected] = useState<ReferenceStyle | null>(null)
  const [refs, setRefs] = useState<{id: string; title: string}[]>([])
  const [name, setName] = useState('My podcast style')
  const [url, setUrl] = useState('')
  const [vision, setVision] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const refresh = () => api.referenceStyles().then(setProfiles).catch(e => setError(String(e)))
  useEffect(() => { void refresh() }, [])
  useEffect(() => {
    if (selected?.status !== 'analysing') return
    const timer = window.setInterval(() => {
      api.referenceStyle(selected.id).then(p => { setSelected(p); void refresh() }).catch(e => setError(String(e)))
    }, 2500)
    return () => window.clearInterval(timer)
  }, [selected?.id, selected?.status])
  async function action(label: string, fn: () => Promise<void>) {
    setBusy(label); setError('')
    try { await fn() } catch(e) { setError(String(e)) } finally { setBusy('') }
  }
  const patch = (field: string, value: string | number) => setSelected(p => p ? {...p, reviewed: false, recommendations: {...p.recommendations, [field]: value}} : p)
  return <div className="max-w-4xl pt-14 space-y-6">
    <h1 className="font-display text-4xl">Learn from reference clips</h1>
    <p>Add 1–5 finished clips, ideally 3–5 from one channel. The app measures duration and scene changes, studies spoken openings and endings, and proposes an editable preset. Use clips up to five minutes each.</p>
    <section className="space-y-5 border border-ink-700 p-5">
      <label className="block">Preset name<input className="field" maxLength={80} value={name} onChange={e => setName(e.target.value)} /></label>
      <div className="flex gap-3"><input className="field" placeholder="Short YouTube reference video URL" value={url} onChange={e => setUrl(e.target.value)} />
        <button className="btn" disabled={!!busy || !url.trim() || refs.length >= 5} onClick={() => void action('Downloading reference', async () => {
          const source = await api.referenceYouTube(url.trim()); setRefs(r => [...r, source]); setUrl('')
        })}>Add link</button></div>
      <label className="block">Or upload a clip<input className="mt-2 block" type="file" accept="video/*" disabled={!!busy || refs.length >= 5} onChange={e => {
        const file = e.target.files?.[0]; if (!file) return
        void action('Uploading', async () => {
          const source = await api.uploadSource(file)
          if (source.duration_s > 300 || !source.has_video) throw Error('Choose a video up to five minutes.')
          setRefs(r => [...r, source])
        }); e.target.value = ''
      }} /></label>
      {refs.map((r,i) => <p key={i}>{r.title} <button className="ml-3 text-sodium-500" onClick={() => setRefs(v => v.filter((_,j) => j !== i))}>Remove</button></p>)}
      <label className="flex gap-3"><input type="checkbox" checked={vision} onChange={e => setVision(e.target.checked)} />Include visual observations from three frames per clip</label>
      <p className="text-xs text-ink-400">Optional vision requires <code>ollama pull qwen2.5vl:3b</code> first and can be slow. It cannot establish animation, music or exact fonts. Models are never installed automatically.</p>
      <button className="btn btn-primary" disabled={!!busy || !refs.length || !name.trim() || profiles.some(p => p.status === 'analysing')} onClick={() => void action('Starting', async () => {
        setSelected(await api.createReferenceStyle(name.trim(), refs.map(r => r.id), vision)); setRefs([]); void refresh()
      })}>Analyse references</button>
      <p className="text-xs text-ink-400">Analyse while clip jobs are idle to avoid competing for your GPU. This saves preferences; it does not train a model.</p>
    </section>
    {busy && <p className="text-sodium-500">{busy}…</p>}
    {error && <p role="alert" className="text-signal-bad">{error}</p>}
    <div className="flex flex-wrap gap-3">{profiles.map(p => <button className="btn" key={p.id} onClick={() => setSelected(p)}>{p.name} · {p.status}</button>)}</div>
    {selected && <section className="space-y-5">
      <h2 className="font-display text-3xl">{selected.name}</h2><p>{selected.message}</p>
      {selected.status === 'failed' && <button className="btn" disabled={!!busy} onClick={() => void action('Retrying', async () => setSelected(await api.retryReferenceStyle(selected.id)))}>Retry analysis</button>}
      {selected.status === 'ready' && <>
        <p className="whitespace-pre-wrap text-ink-300">{selected.summary}</p>
        <label className="block">Name<input className="field" value={selected.name} maxLength={80} onChange={e => setSelected({...selected, name: e.target.value, reviewed: false})} /></label>
        <label className="block">Editorial preferences<textarea className="field min-h-40" maxLength={1500} value={selected.guidance} onChange={e => setSelected({...selected, guidance: e.target.value, reviewed: false})} /></label>
        <div className="grid grid-cols-2 gap-5">
          {(['min_duration_s','max_duration_s'] as const).map(field => <label key={field}>{field === 'min_duration_s' ? 'Minimum seconds' : 'Maximum seconds'}<input className="field" type="number" min={10} max={600} value={selected.recommendations[field]} onChange={e => patch(field, Number(e.target.value))} /></label>)}
          {Object.entries({ratio:['9:16','16:9','1:1'],framing:['fit','auto','centre','split'],caption_style:['clean_lower','bold_pop','boxed','karaoke'],editorial_style:['story','newsroom','general']}).map(([field,opts]) => <label key={field}>{field.replaceAll('_',' ')}<select className="field" value={String(selected.recommendations[field as keyof JobSettingsOverrides])} onChange={e => patch(field,e.target.value)}>{opts.map(v => <option key={v}>{v}</option>)}</select></label>)}
        </div>
        <p className="text-xs text-ink-400">Length and aspect ratio are measured. Caption style and framing are editable suggestions. Measured cuts do not automatically insert cuts into your exports.</p>
        <button className="btn btn-primary" disabled={!!busy || !selected.name.trim() || !selected.guidance.trim()} onClick={() => void action('Saving', async () => {
          setSelected(await api.saveReferenceStyle(selected)); void refresh()
        })}>{selected.reviewed ? 'Save changes' : 'Review and save preset'}</button>
        {selected.reviewed && <Link className="ml-5 text-sodium-500" to="/">Use on a new video →</Link>}
      </>}
      <details><summary>Reference evidence and limitations</summary>
        <p className="my-4 text-sm text-ink-400">{selected.limits || 'Evidence appears as analysis completes.'}</p>
        {selected.evidence.map(e => <div key={e.source_id} className="my-5 text-sm space-y-2">
          <p>{e.title}</p><p>{e.measurements.duration_s}s · {e.measurements.width}×{e.measurements.height} · {e.measurements.cut_count} image-change cuts · median shot {e.measurements.median_shot_s}s</p>
          <p>Opening: {e.opening}</p><p>Ending: {e.ending}</p>
          {!!e.visual && <pre className="whitespace-pre-wrap text-xs">{JSON.stringify(e.visual,null,2)}</pre>}
        </div>)}
      </details>
    </section>}
  </div>
}
