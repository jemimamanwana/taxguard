import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { FileWarning, LogOut } from 'lucide-react'
import { api, session } from '../lib/api'
import { M } from '../lib/format'
import { Btn, Card, ErrorBox, Modal, Spinner, useAsync } from '../components/ui'
import InvoiceScanner, { type ScanText } from '../components/InvoiceScanner'
import { Logo } from '../App'

type Lang = 'en' | 'st'
// Sesotho labels: draft translations - to be reviewed by a native speaker before any pilot.
const T = {
  en: {
    title: 'My VAT refunds', sub: 'Submit a refund claim, add invoice photos and follow its progress.', newClaim: 'New refund claim',
    period: 'Tax period', output: 'Output VAT (on your sales)', input: 'Input VAT (on your purchases)', submit: 'Submit claim',
    refund: 'Refund', status: 'Status', addInv: 'Add invoice photos', docs: 'Documents requested', signout: 'Sign out',
    scan: { pick: 'Choose a photo', camera: 'Take photo of invoice', reading: 'Reading your invoice…', attach: 'Add to claim', checks: 'Checks', fields: 'What we read' } as ScanText,
  },
  st: {
    title: 'Litefo tsa ka tsa VAT', sub: 'Romela kopo ea tefo, kenya lifoto tsa li-invoice ’me u latele tsoelo-pele ea eona.', newClaim: 'Kopo e ncha ea tefo',
    period: 'Nako ea lekhetho', output: 'VAT ea thekiso', input: 'VAT ea theko', submit: 'Romela kopo',
    refund: 'Tefo', status: 'Boemo', addInv: 'Kenya lifoto tsa li-invoice', docs: 'Litokomane tse hlokahalang', signout: 'Tsoa',
    scan: { pick: 'Khetha foto', camera: 'Nka foto ea invoice', reading: 'Re bala invoice ea hau…', attach: 'Kenya kopong', checks: 'Litlhahlobo', fields: 'Seo re se balileng' } as ScanText,
  },
}

export default function Portal() {
  const user = session.user()
  const nav = useNavigate()
  const [lang, setLang] = useState<Lang>('en')
  const [scanFor, setScanFor] = useState<number | null>(null)
  const [form, setForm] = useState({ period: '2026-10', output_vat: '', input_vat: '' })
  const [err, setErr] = useState<unknown>(null)
  const data = useAsync<any>(() => (user?.role === 'taxpayer' ? api('/portal/claims') : Promise.resolve(null)), [])
  if (!user) return <Navigate to="/login" replace />
  if (user.role !== 'taxpayer') return <Navigate to="/queue" replace />
  const t = T[lang]

  async function submit() {
    setErr(null)
    try {
      const r = await api('/portal/claims', { method: 'POST', json: { period: form.period, output_vat: Number(form.output_vat), input_vat: Number(form.input_vat) } })
      data.reload(); setScanFor(r.claim_id)
    } catch (e) { setErr(e) }
  }

  return (
    <div className="min-h-full">
      <header className="bg-white border-b border-line">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between">
          <Logo />
          <div className="flex items-center gap-3 text-sm">
            <div className="flex rounded-lg ring-1 ring-line overflow-hidden" role="group" aria-label="Language">
              {(['en', 'st'] as Lang[]).map(l => <button key={l} onClick={() => setLang(l)} className={`px-2.5 py-1 ${lang === l ? 'bg-ink text-white' : 'bg-white'}`}>{l === 'en' ? 'English' : 'Sesotho'}</button>)}
            </div>
            <button onClick={() => { session.clear(); nav('/login') }} className="text-muted flex items-center gap-1"><LogOut size={14} />{t.signout}</button>
          </div>
        </div>
      </header>
      <main className="max-w-3xl mx-auto p-4 space-y-4">
        {data.loading ? <Spinner /> : <ErrorBox error={data.error} />}
        {data.data && (
          <>
            <div>
              <h1 className="text-xl font-semibold">{t.title}</h1>
              <p className="text-sm text-muted">{data.data.taxpayer.name} · TIN {data.data.taxpayer.tin}</p>
              <p className="text-sm text-muted mt-1">{t.sub}</p>
            </div>
            <div className="space-y-2">
              {data.data.claims.slice(0, 8).map((c: any) => (
                <div key={c.claim_id} className={`bg-white rounded-xl border p-3 ${c.status === 'docs_requested' ? 'border-review' : 'border-line'}`}>
                  <div className="flex flex-wrap justify-between gap-2 items-start">
                    <div>
                      <div className="text-xs text-muted">#{c.claim_id} · {t.period} {c.period}</div>
                      <div className="font-semibold num">{t.refund}: {M(c.refund_claimed)}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-muted">{t.status}</div>
                      <div className={`text-sm font-medium ${c.status === 'docs_requested' ? 'text-review' : c.status === 'approved' ? 'text-fast' : ''}`}>{c.status_text}</div>
                    </div>
                  </div>
                  {c.documents_requested && (
                    <div className="mt-2 rounded-lg bg-review-soft p-2 text-sm">
                      <div className="font-medium flex items-center gap-1"><FileWarning size={15} />{t.docs}</div>
                      <div className="whitespace-pre-line">{c.documents_requested}</div>
                      {c.message && <div className="text-muted text-xs mt-1">“{c.message}”</div>}
                    </div>
                  )}
                  {['pending', 'docs_requested'].includes(c.status) && <Btn tone="ghost" className="mt-2" onClick={() => setScanFor(c.claim_id)}>{t.addInv}</Btn>}
                </div>
              ))}
            </div>
            <Card title={t.newClaim}>
              <div className="grid sm:grid-cols-3 gap-3">
                <label className="text-xs text-muted">{t.period}<input value={form.period} onChange={e => setForm({ ...form, period: e.target.value })} className="mt-1 w-full rounded-lg border border-line px-2 py-1.5 text-sm text-ink" /></label>
                <label className="text-xs text-muted">{t.output}<input inputMode="decimal" value={form.output_vat} onChange={e => setForm({ ...form, output_vat: e.target.value })} className="mt-1 w-full rounded-lg border border-line px-2 py-1.5 text-sm text-ink num" /></label>
                <label className="text-xs text-muted">{t.input}<input inputMode="decimal" value={form.input_vat} onChange={e => setForm({ ...form, input_vat: e.target.value })} className="mt-1 w-full rounded-lg border border-line px-2 py-1.5 text-sm text-ink num" /></label>
              </div>
              {Number(form.input_vat) > Number(form.output_vat) && <div className="text-sm mt-2">{t.refund}: <b className="num">{M(Number(form.input_vat) - Number(form.output_vat))}</b></div>}
              <ErrorBox error={err} />
              <Btn className="mt-3" onClick={submit} disabled={!form.input_vat || !form.output_vat}>{t.submit}</Btn>
            </Card>
          </>
        )}
      </main>
      <Modal open={scanFor != null} onClose={() => { setScanFor(null); data.reload() }} title={`${t.addInv} · #${scanFor}`} wide>
        {scanFor != null && <InvoiceScanner claimId={scanFor} samples text={t.scan} />}
      </Modal>
    </div>
  )
}
