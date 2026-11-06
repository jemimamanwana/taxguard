import { useEffect, useRef, useState } from 'react'
import { Camera, CheckCircle2, Cpu, FileImage, Loader2, Upload, XCircle, AlertTriangle } from 'lucide-react'
import { api, apiBlobUrl, compressImage } from '../lib/api'
import { M } from '../lib/format'
import { Btn, Chip, ErrorBox, LanePill } from './ui'

const LABELS: Record<string, string> = {
  supplier_name: 'Supplier name', supplier_tin: 'Supplier TIN', buyer_name: 'Buyer name', buyer_tin: 'Buyer TIN',
  invoice_number: 'Invoice number', invoice_date: 'Invoice date', currency: 'Currency', net_amount: 'Net amount',
  vat_amount: 'VAT amount', total_amount: 'Total',
}
const ORDER = ['supplier_name', 'supplier_tin', 'invoice_number', 'invoice_date', 'buyer_name', 'buyer_tin', 'net_amount', 'vat_amount', 'total_amount', 'currency']

export type ScanText = { pick: string; camera: string; reading: string; attach: string; checks: string; fields: string }
const EN: ScanText = { pick: 'Upload JPG, PNG or PDF', camera: 'Take photo', reading: 'Reading invoice…', attach: 'Confirm & attach to claim', checks: 'Automatic checks', fields: 'Extracted fields' }

function Check({ ok, warn, children }: { ok: boolean; warn?: boolean; children: React.ReactNode }) {
  return (
    <li className="flex gap-2 text-sm">
      {ok ? <CheckCircle2 size={16} className="text-fast shrink-0 mt-0.5" /> : warn ? <AlertTriangle size={16} className="text-review shrink-0 mt-0.5" /> : <XCircle size={16} className="text-audit shrink-0 mt-0.5" />}
      <span>{children}</span>
    </li>
  )
}

export default function InvoiceScanner({ claimId, samples = true, text = EN, onAttached }: { claimId?: number; samples?: boolean; text?: ScanText; onAttached?: (r: any) => void }) {
  const [preview, setPreview] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<unknown>(null)
  const [res, setRes] = useState<any>(null)
  const [vals, setVals] = useState<Record<string, string>>({})
  const [size, setSize] = useState<{ before: number; after: number } | null>(null)
  const [target, setTarget] = useState<string>(claimId ? String(claimId) : '')
  const [attached, setAttached] = useState<any>(null)
  const [sampleList, setSampleList] = useState<any[]>([])
  const [ext, setExt] = useState<{ claude: boolean; tesseract: boolean } | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const camRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api('/invoices/extractors').then(setExt).catch(() => {})
    if (samples) api('/invoices/samples').then(setSampleList).catch(() => {})
  }, [samples])

  async function run(file: File, claim?: number) {
    setBusy(true); setErr(null); setRes(null); setAttached(null)
    try {
      const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
      const { blob, before, after } = isPdf ? { blob: file as Blob, before: file.size, after: file.size } : await compressImage(file)
      setSize(isPdf ? null : { before, after })
      setPreview(isPdf ? null : URL.createObjectURL(blob))
      const fd = new FormData()
      fd.append('file', blob, isPdf ? 'invoice.pdf' : 'invoice.jpg')
      const cid = claim ?? (target ? Number(target) : undefined)
      if (cid) fd.append('claim_id', String(cid))
      const r = await api('/invoices/scan', { method: 'POST', body: fd })
      if (isPdf) setPreview(await apiBlobUrl(`/invoices/image/upload:${r.upload_id}.jpg`))
      setRes(r)
      setVals(Object.fromEntries(Object.entries(r.fields).map(([k, v]: any) => [k, v.value == null ? '' : String(v.value)])))
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  async function pickSample(s: any) {
    if (!claimId) setTarget(String(s.claim_id))
    const url = await apiBlobUrl(`/invoices/image/${s.file}`)
    const blob = await (await fetch(url)).blob()
    run(new File([blob], s.file, { type: 'image/jpeg' }), claimId ?? s.claim_id)
  }

  async function confirm() {
    setBusy(true); setErr(null)
    try {
      const edited: Record<string, string> = {}
      for (const [k, v] of Object.entries(vals)) {
        const orig = res.fields[k]?.value
        if (String(orig ?? '') !== v) edited[k] = v
      }
      const r = await api('/invoices/confirm', { method: 'POST', json: { upload_id: res.upload_id, claim_id: Number(target), fields: edited } })
      setAttached(r); onAttached?.(r)
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const ch = res?.checks
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 items-center">
        <input ref={fileRef} type="file" accept="image/jpeg,image/png,application/pdf" className="hidden" onChange={e => e.target.files?.[0] && run(e.target.files[0])} />
        <input ref={camRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={e => e.target.files?.[0] && run(e.target.files[0])} />
        <Btn onClick={() => camRef.current?.click()}><Camera size={16} />{text.camera}</Btn>
        <Btn tone="ghost" onClick={() => fileRef.current?.click()}><Upload size={16} />{text.pick}</Btn>
        {!claimId && (
          <label className="text-sm flex items-center gap-2 ml-auto">Claim #
            <input value={target} onChange={e => setTarget(e.target.value.replace(/\D/g, ''))} className="w-24 rounded-lg border border-line px-2 py-1.5 num" placeholder="optional" />
          </label>
        )}
      </div>
      {ext && (
        <div className="text-xs text-muted flex items-center gap-1.5"><Cpu size={13} />
          Reader: {ext.claude ? 'Claude vision (primary)' : 'Claude vision unavailable – no API key'} · offline fallback: {ext.tesseract ? 'Tesseract OCR' : 'manual entry'}
        </div>
      )}
      {samples && sampleList.length > 0 && !res && !busy && (
        <div>
          <div className="text-xs font-semibold text-muted uppercase tracking-wide mb-1.5">Or try a sample invoice photo</div>
          <div className="flex flex-wrap gap-1.5">
            {sampleList.slice(0, 16).map(s => (
              <button key={s.file} onClick={() => pickSample(s)} className="text-xs rounded-md ring-1 ring-line bg-white hover:ring-brand px-2 py-1 inline-flex items-center gap-1"><FileImage size={13} />{s.label}</button>
            ))}
          </div>
        </div>
      )}
      <ErrorBox error={err} />
      {busy && <div className="flex items-center gap-2 text-sm text-muted"><Loader2 size={16} className="animate-spin" />{text.reading}</div>}

      {res && (
        <div className="grid lg:grid-cols-5 gap-4">
          <div className="lg:col-span-2">
            {preview && <img src={preview} alt="Uploaded invoice" className="w-full rounded-lg ring-1 ring-line" />}
            {size && <div className="text-xs text-muted mt-1">Compressed on device: {(size.before / 1024).toFixed(0)} KB → {(size.after / 1024).toFixed(0)} KB</div>}
            <div className="text-xs text-muted mt-1">{res.file_type === 'pdf' ? 'PDF – first page read; original file preserved unchanged.' : 'Original upload preserved unchanged.'} Fields marked “auto” are machine-extracted.</div>
          </div>
          <div className="lg:col-span-3 space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Chip tone={res.extractor.startsWith('claude') ? 'brand' : 'warn'}>{res.extractor.startsWith('claude') ? 'Read by Claude vision' : res.extractor === 'tesseract' ? 'Offline OCR' : 'Manual entry mode'}</Chip>
              <Chip tone={res.autofill.fully_automatic ? 'good' : 'warn'}>{res.autofill.auto_filled}/{res.autofill.required_fields} key fields auto-filled</Chip>
              {res.latency_s && <span className="text-xs text-muted">{res.latency_s}s</span>}
              {res.fallback_reason && <span className="text-xs text-muted">({res.fallback_reason})</span>}
            </div>
            <div>
              <div className="text-xs font-semibold text-muted uppercase tracking-wide mb-1.5">{text.fields}</div>
              <div className="grid sm:grid-cols-2 gap-2">
                {ORDER.map(k => {
                  const f = res.fields[k]
                  return (
                    <label key={k} className={`rounded-lg p-2 ring-1 ${f.needs_review ? 'ring-review bg-review-soft/50' : 'ring-line bg-white'}`}>
                      <div className="flex justify-between text-[11px] text-muted">
                        <span>{LABELS[k]}</span>
                        <span className={f.needs_review ? 'text-review font-semibold' : 'text-fast'}>{f.source === 'claim' ? 'from claim' : f.needs_review ? `check · ${(f.confidence * 100).toFixed(0)}%` : `auto · ${(f.confidence * 100).toFixed(0)}%`}</span>
                      </div>
                      <input value={vals[k] ?? ''} onChange={e => setVals(v => ({ ...v, [k]: e.target.value }))} className="w-full bg-transparent text-sm font-medium outline-none num" />
                    </label>
                  )
                })}
              </div>
              {res.legibility_notes && <div className="text-xs text-muted mt-1.5">Note: {res.legibility_notes}</div>}
            </div>
            <div>
              <div className="text-xs font-semibold text-muted uppercase tracking-wide mb-1.5">{text.checks}</div>
              <ul className="space-y-1">
                <Check ok={ch.arithmetic_ok}>Net + VAT = total</Check>
                <Check ok={ch.vat_rate_ok}>VAT rate {(ch.vat_rate * 100).toFixed(1)}% is an applicable rate</Check>
                <Check ok={ch.supplier_tin_valid}>Supplier TIN passes format & check-digit test</Check>
                <Check ok={ch.supplier_registered && !ch.flags.includes('PREREG')}>Supplier on VAT register{ch.registry_name ? ` as “${ch.registry_name}”` : ''}{ch.supplier_age_days != null ? ` (registered ${Math.round(ch.supplier_age_days / 30)} months before invoice)` : ''}</Check>
                <Check ok={ch.listed_by_supplier} warn={!ch.listed_by_supplier && !ch.supplier_low_declarer}>
                  {ch.listed_by_supplier ? 'Found in supplier’s declared sales listing' : ch.supplier_low_declarer ? `Supplier declared ${ch.supplier_output_vat == null ? 'no return' : M(ch.supplier_output_vat) + ' output VAT'} – sale not declared` : 'Not yet in supplier’s sales listing (supplier is an active filer)'}
                </Check>
                <Check ok={!ch.duplicate}>{ch.duplicate ? ch.duplicate.message : 'Not a duplicate of any stored invoice (number, fields and image hash)'}</Check>
                {'date_in_period' in ch && <Check ok={ch.date_in_period}>Invoice date within claim period</Check>}
              </ul>
            </div>
            {!attached ? (
              <div className="flex flex-wrap gap-2 items-center">
                <Btn onClick={confirm} disabled={busy || !target}>{text.attach}{target ? ` #${target}` : ''}</Btn>
                {!target && <span className="text-xs text-muted">Enter a claim number to attach this invoice.</span>}
              </div>
            ) : (
              <div className="rounded-lg bg-fast-soft p-3 text-sm flex flex-wrap items-center gap-2">
                <CheckCircle2 size={16} className="text-fast" />Attached as invoice #{attached.invoice_id}. Claim re-scored:
                <LanePill lane={attached.claim.lane} /> <span className="num">score {attached.claim.score?.toFixed(0)}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
