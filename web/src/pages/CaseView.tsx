import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, CheckCircle2, Copy, FileWarning, Image as ImageIcon, Info, Network, Printer, ShieldAlert, XCircle } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, ComposedChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../lib/api'
import { M, Mshort, pct } from '../lib/format'
import { AuthImage, Btn, Card, Chip, ErrorBox, LanePill, Modal, Spinner, useAsync } from '../components/ui'

type Reason = { code: string; title: string; detail: string; severity: number; bucket: string; points: number; evidence: any }

const BUCKET: Record<string, { label: string; tone: 'risk' | 'warn' | 'brand' }> = {
  evidence: { label: 'Document evidence', tone: 'risk' }, group: { label: 'Group structure', tone: 'brand' }, pattern: { label: 'Behaviour pattern', tone: 'warn' },
}

const FR_LABEL: Record<string, { label: string; tone: 'good' | 'neutral' | 'warn' }> = {
  reviewed: { label: 'Reviewed', tone: 'good' }, not_applicable: { label: 'Not applicable', tone: 'neutral' }, info_required: { label: 'Information required', tone: 'warn' },
}

function FlagReviewCtl({ code, review, claimId, canReview, onDone }: { code: string; review?: any; claimId: number; canReview: boolean; onDone: (d: any) => void }) {
  const [open, setOpen] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [err, setErr] = useState<unknown>(null)
  async function save() {
    setErr(null)
    try { onDone(await api(`/claims/${claimId}/flags`, { method: 'POST', json: { code, status: open, note } })); setOpen(null); setNote('') } catch (e) { setErr(e) }
  }
  return (
    <div className="mt-1.5 no-print">
      {review && <div className="text-xs"><Chip tone={FR_LABEL[review.status].tone}>{FR_LABEL[review.status].label}</Chip> <span className="text-muted">{review.username}: “{review.note}”</span></div>}
      {canReview && !open && (
        <div className="flex gap-2 mt-1 text-[11px]">
          {Object.entries(FR_LABEL).map(([k, v]) => <button key={k} onClick={() => setOpen(k)} className="text-muted hover:text-brand underline-offset-2 hover:underline">{review ? '' : 'Mark '}{v.label.toLowerCase()}</button>)}
        </div>
      )}
      {open && (
        <div className="mt-1.5 flex flex-wrap gap-2 items-start">
          <input autoFocus value={note} onChange={e => setNote(e.target.value)} placeholder={`Reason – ${FR_LABEL[open].label.toLowerCase()}`} className="flex-1 min-w-48 rounded-md border border-line px-2 py-1 text-xs" />
          <Btn tone="ghost" className="py-1! px-2! text-xs!" onClick={() => setOpen(null)}>Cancel</Btn>
          <Btn className="py-1! px-2! text-xs!" disabled={note.trim().length < 5} onClick={save}>Save</Btn>
          <ErrorBox error={err} />
        </div>
      )}
    </div>
  )
}

function ReasonRow({ r, max, children }: { r: Reason; max: number; children?: React.ReactNode }) {
  const offset = r.points < 0.5 && r.severity > 0
  return (
    <li className={`py-3 ${offset ? 'opacity-60' : ''}`}>
      <div className="flex items-start gap-3">
        <span className="mt-0.5 font-mono text-xs font-semibold rounded bg-ink text-white px-1.5 py-0.5">{r.code}</span>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-sm">{r.title}</span>
            {BUCKET[r.bucket] && <Chip tone={BUCKET[r.bucket].tone}>{BUCKET[r.bucket].label}</Chip>}
            {offset && <Chip tone="good">explained by mitigating factor</Chip>}
          </div>
          <p className="text-sm text-muted mt-0.5">{r.detail}</p>
          {children}
        </div>
        <div className="w-24 shrink-0 text-right">
          <div className="text-sm num font-semibold">+{r.points.toFixed(1)}</div>
          <div className="h-1.5 bg-line rounded-full mt-1 overflow-hidden"><div className="h-full bg-audit" style={{ width: `${Math.min(100, (r.points / max) * 100)}%` }} /></div>
        </div>
      </div>
    </li>
  )
}

function InvoiceStatus({ flags }: { flags: string[] }) {
  if (flags.includes('DUP')) return <span className="inline-flex items-center gap-1 text-audit text-xs font-medium"><Copy size={14} />Duplicate</span>
  if (flags.includes('NOMATCH')) return <span className="inline-flex items-center gap-1 text-audit text-xs font-medium"><XCircle size={14} />Supplier did not declare</span>
  if (flags.includes('PREREG') || flags.includes('UNREG')) return <span className="inline-flex items-center gap-1 text-audit text-xs font-medium"><ShieldAlert size={14} />Supplier not registered</span>
  if (flags.includes('NOLIST')) return <span className="inline-flex items-center gap-1 text-review text-xs font-medium"><AlertTriangle size={14} />Not yet listed</span>
  if (flags.length) return <span className="inline-flex items-center gap-1 text-review text-xs font-medium"><FileWarning size={14} />{flags.join(', ')}</span>
  return <span className="inline-flex items-center gap-1 text-fast text-xs font-medium"><CheckCircle2 size={14} />Cross-matched</span>
}

const SEL = { fast: 'ring-fast bg-fast-soft', review: 'ring-review bg-review-soft', audit: 'ring-audit bg-audit-soft' }

function DecisionPanel({ c, onDone }: { c: any; onDone: (d: any) => void }) {
  const ex = c.explanation
  const [action, setAction] = useState<string>('')
  const [comment, setComment] = useState('')
  const [docs, setDocs] = useState<string>((ex.requested_documents || []).join('\n'))
  const [err, setErr] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const rec = c.claim.lane === 'fast_track' ? 'approve' : c.claim.lane === 'review' ? 'request_documents' : 'escalate'
  async function submit() {
    setBusy(true); setErr(null)
    try {
      onDone(await api(`/claims/${c.claim.claim_id}/decision`, { method: 'POST', json: { action, comment, requested_docs: action === 'request_documents' ? docs : null } }))
      setAction(''); setComment('')
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  if (!c.can_decide) return (
    <div className="text-sm text-muted">
      {c.claim.status === 'pending' ? 'Your role can view this case but cannot decide it.' : <>Decision recorded: <b className="capitalize text-ink">{c.claim.status.replace('_', ' ')}</b>.</>}
    </div>
  )
  const opts = [
    { k: 'approve', label: 'Approve refund', tone: 'fast' as const },
    { k: 'request_documents', label: 'Request documents', tone: 'review' as const },
    { k: 'escalate', label: 'Escalate to audit', tone: 'audit' as const },
  ]
  return (
    <div className="space-y-3">
      <div className="grid gap-1.5">
        {opts.map(o => (
          <button key={o.k} onClick={() => setAction(o.k)}
            className={`text-left rounded-lg px-3 py-2 text-sm flex justify-between items-center ${action === o.k ? `ring-2 font-semibold ${SEL[o.tone]}` : 'ring-1 ring-line hover:bg-paper'}`}>
            {o.label}{rec === o.k && <Chip tone="brand">recommended</Chip>}
          </button>
        ))}
      </div>
      {action === 'request_documents' && (
        <label className="block text-xs text-muted">Documents to request (one per line)
          <textarea value={docs} onChange={e => setDocs(e.target.value)} rows={3} className="mt-1 w-full rounded-lg border border-line p-2 text-sm text-ink" />
        </label>
      )}
      {action && (
        <>
          <label className="block text-xs text-muted">Reason for decision (required – kept in the audit log)
            <textarea value={comment} onChange={e => setComment(e.target.value)} rows={3} placeholder="e.g. Export documents verified against customs data"
              className="mt-1 w-full rounded-lg border border-line p-2 text-sm text-ink" />
          </label>
          {action !== rec && <div className="text-xs text-review flex gap-1"><Info size={14} className="shrink-0" />This differs from the recommendation – your reason will be recorded as an override.</div>}
          <ErrorBox error={err} />
          <Btn onClick={submit} disabled={busy || comment.trim().length < 5} tone={opts.find(o => o.k === action)!.tone} className="w-full">Confirm decision</Btn>
        </>
      )}
    </div>
  )
}

export default function CaseView() {
  const { id } = useParams()
  const { data: c, error, loading, setData } = useAsync<any>(() => api(`/claims/${id}`), [id])
  const [tab, setTab] = useState('invoices')
  const [img, setImg] = useState<any>(null)
  if (loading && !c) return <Spinner />
  if (error) return <ErrorBox error={error} />
  if (!c) return null
  const ex = c.explanation
  const reasons: Reason[] = ex.reasons || []
  const max = Math.max(35, ...reasons.map(r => r.points))
  const flagged = c.invoices.filter((i: any) => i.flags.length && !(i.flags.length === 1 && i.flags[0] === 'NOLIST')).length
  const chart = c.returns.map((r: any) => ({ ...r, position: -r.net_vat, highlight: r.period === c.claim.period }))

  return (
    <div className="space-y-4">
      <Link to="/queue" className="no-print text-sm text-muted hover:text-ink inline-flex items-center gap-1"><ArrowLeft size={15} />Back to queue</Link>

      <div className="bg-white border border-line rounded-xl p-4 md:p-5 flex flex-wrap gap-4 items-start justify-between">
        <div className="min-w-0">
          <div className="text-xs text-muted">Refund claim #{c.claim.claim_id} · period {c.claim.period} · submitted {c.claim.submitted_on}</div>
          <h1 className="text-xl font-semibold mt-0.5">{c.taxpayer.name}</h1>
          <div className="text-sm text-muted mt-0.5 flex flex-wrap gap-x-3">
            <span>TIN {c.taxpayer.tin}{c.tin_masked && <span title="TINs are visible only to the assigned officer"> (masked)</span>}</span>
            <span>{c.taxpayer.sector}</span><span>Registered {c.taxpayer.registration_date}</span><span>{c.taxpayer.town}</span>
            {c.taxpayer.group && <Link to={`/groups/${c.taxpayer.group.group_id}`} className="text-brand inline-flex items-center gap-1"><Network size={14} />{c.taxpayer.group.name}</Link>}
          </div>
        </div>
        <div className="flex items-center gap-5">
          <div className="text-right">
            <div className="text-xs text-muted">Refund claimed</div>
            <div className="text-2xl font-semibold num">{M(c.claim.refund_claimed)}</div>
          </div>
          <div className="text-right">
            <div className="text-xs text-muted mb-1">Recommendation · score {c.claim.score?.toFixed(0)}/100</div>
            <LanePill lane={c.claim.lane} large />
          </div>
        </div>
        <p className={`w-full text-sm rounded-lg px-3 py-2 ${c.claim.lane === 'audit' ? 'bg-audit-soft' : c.claim.lane === 'review' ? 'bg-review-soft' : 'bg-fast-soft'}`}>{ex.summary}</p>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <Card title="Why this recommendation" actions={<span className="text-xs text-muted">points add up to the score · model {c.claim.model_version}</span>}>
            {reasons.length ? <ul className="divide-y divide-line -my-3">{reasons.map(r => (
              <ReasonRow key={r.code} r={r} max={max}>
                <FlagReviewCtl code={r.code} review={c.flag_reviews?.[r.code]} claimId={c.claim.claim_id} canReview={c.can_review_flags} onDone={setData} />
              </ReasonRow>
            ))}</ul>
              : <p className="text-sm text-muted">No risk rule fired for this claim.</p>}
            {(ex.mitigations?.length > 0) && (
              <div className="mt-4 rounded-lg bg-fast-soft/60 ring-1 ring-fast/20 p-3">
                <div className="text-xs font-semibold text-fast uppercase tracking-wide">Mitigating factors</div>
                <ul className="mt-1 space-y-2">
                  {ex.mitigations.map((m: Reason) => (
                    <li key={m.code} className="flex gap-3 text-sm">
                      <span className="font-mono text-xs font-semibold rounded bg-fast text-white px-1.5 py-0.5 h-fit">{m.code}</span>
                      <div className="flex-1"><div className="font-medium">{m.title}</div><div className="text-muted">{m.detail}</div></div>
                      <span className="num font-semibold text-fast">{m.points.toFixed(1)}</span>
                    </li>
                  ))}
                </ul>
                <div className="text-xs text-muted mt-2">Mitigations can only offset behaviour patterns – never document evidence or group-structure findings.</div>
              </div>
            )}
            {ex.data_gaps?.length > 0 && (
              <div className="mt-4 rounded-lg bg-paper ring-1 ring-line p-3">
                <div className="text-xs font-semibold text-muted uppercase tracking-wide">Data completeness – not scored</div>
                <ul className="mt-1 space-y-2">
                  {ex.data_gaps.map((g: Reason) => (
                    <li key={g.code} className="flex gap-3 text-sm">
                      <span className="font-mono text-xs font-semibold rounded bg-muted text-white px-1.5 py-0.5 h-fit">{g.code}</span>
                      <div className="flex-1"><div className="font-medium">{g.title}</div><div className="text-muted">{g.detail}</div>
                        <FlagReviewCtl code={g.code} review={c.flag_reviews?.[g.code]} claimId={c.claim.claim_id} canReview={c.can_review_flags} onDone={setData} /></div>
                    </li>
                  ))}
                </ul>
                <div className="text-xs text-muted mt-2">Missing or contradictory records are shown explicitly. They neither lower nor raise the risk score, but they stop a claim from being fast-tracked until they are resolved.</div>
              </div>
            )}
            {ex.floors?.map((f: Reason) => (
              <div key={f.code} className="mt-3 rounded-lg bg-brand-soft ring-1 ring-brand/20 p-3 text-sm flex gap-2">
                <Info size={16} className="text-brand shrink-0 mt-0.5" /><div><b>{f.title}.</b> {f.detail}</div>
              </div>
            ))}
            {ex.anomaly && (
              <div className="mt-4 text-xs text-muted border-t border-line pt-3">
                <b className="text-ink">Anomaly model:</b> this claim is more unusual than {pct(ex.anomaly.percentile)} of all claims.
                {ex.anomaly.top_features?.length > 0 && <> Main drivers: {ex.anomaly.top_features.map((t: any) => `${t.label.toLowerCase()} (${t.value} vs typical ${t.typical})`).join('; ')}.</>}
              </div>
            )}
          </Card>

          <Card pad={false}>
            <div className="no-print flex gap-1 border-b border-line px-2 pt-2 overflow-x-auto">
              {[['invoices', `Invoices (${c.invoices.length}${flagged ? `, ${flagged} flagged` : ''})`], ['returns', 'VAT returns'], ['financials', 'Financials']].map(([k, l]) => (
                <button key={k} onClick={() => setTab(k)} className={`px-3 py-2 text-sm rounded-t-lg whitespace-nowrap ${tab === k ? 'bg-paper font-semibold border border-b-0 border-line' : 'text-muted'}`}>{l}</button>
              ))}
            </div>
            <div className="p-4">
              {tab === 'invoices' && (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-xs text-muted text-left"><tr>
                      <th className="py-1.5 pr-3 font-medium">Supplier</th><th className="py-1.5 pr-3 font-medium">Invoice</th>
                      <th className="py-1.5 pr-3 font-medium text-right">VAT</th><th className="py-1.5 pr-3 font-medium">Cross-check</th><th />
                    </tr></thead>
                    <tbody>
                      {c.invoices.map((iv: any) => (
                        <tr key={iv.invoice_id} className="border-t border-line align-top">
                          <td className="py-2 pr-3"><div className="font-medium">{iv.supplier_name}</div><div className="text-xs text-muted">TIN {iv.supplier_tin}</div></td>
                          <td className="py-2 pr-3 num"><div>{iv.invoice_no}</div><div className="text-xs text-muted">{iv.invoice_date}</div></td>
                          <td className="py-2 pr-3 text-right num">{M(iv.vat)}</td>
                          <td className="py-2 pr-3 max-w-sm"><InvoiceStatus flags={iv.flags} />
                            {iv.messages.length > 0 && <ul className="text-xs text-muted mt-0.5 space-y-0.5">{iv.messages.map((m: string, i: number) => <li key={i}>{m}</li>)}</ul>}
                          </td>
                          <td className="py-2">{iv.has_image && <button onClick={() => setImg(iv)} className="text-brand text-xs inline-flex items-center gap-1 whitespace-nowrap"><ImageIcon size={14} />View</button>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="text-xs text-muted mt-3">Total invoice VAT {M(c.invoices.reduce((a: number, i: any) => a + i.vat, 0))} vs input VAT claimed {M(c.claim.input_vat_claimed)}.</div>
                </div>
              )}
              {tab === 'returns' && (
                <div>
                  <div className="text-xs text-muted mb-2">Monthly VAT position (positive = refund claimed). Highlighted bar = this claim.</div>
                  <div className="h-64">
                    <ResponsiveContainer>
                      <ComposedChart data={chart}>
                        <CartesianGrid stroke="#eef1f5" vertical={false} />
                        <XAxis dataKey="period" tick={{ fontSize: 11 }} interval={2} />
                        <YAxis tickFormatter={Mshort} tick={{ fontSize: 11 }} width={70} />
                        <Tooltip formatter={(v: number) => M(v)} />
                        <Legend wrapperStyle={{ fontSize: 12 }} />
                        <ReferenceLine y={0} stroke="#9aa7b6" />
                        <Bar dataKey="position" name="Refund position (input − output VAT)">
                          {chart.map((d: any) => <Cell key={d.period} fill={d.highlight ? '#00209f' : d.position > 0 ? '#e0a526' : '#9fc5ae'} />)}
                        </Bar>
                        <Line dataKey="output_vat" name="Output VAT" stroke="#138a4b" dot={false} strokeWidth={2} />
                        <Line dataKey="input_vat" name="Input VAT" stroke="#b3261e" dot={false} strokeWidth={2} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
              {tab === 'financials' && (
                <div className="grid md:grid-cols-2 gap-4">
                  <table className="w-full text-sm">
                    <thead className="text-xs text-muted text-left"><tr><th className="py-1">Year</th><th className="text-right">Turnover</th><th className="text-right">Gross margin</th><th className="text-right">Net profit</th><th className="text-right">Losses c/f</th></tr></thead>
                    <tbody>{c.financials.map((f: any) => (
                      <tr key={f.year} className="border-t border-line num"><td className="py-1.5">{f.year}</td><td className="text-right">{Mshort(f.turnover)}</td>
                        <td className="text-right">{pct(f.gross_margin, 1)}</td><td className={`text-right ${f.net_profit < 0 ? 'text-audit' : ''}`}>{Mshort(f.net_profit)}</td><td className="text-right">{Mshort(f.losses_carried_forward)}</td></tr>
                    ))}</tbody>
                  </table>
                  <div className="h-48">
                    <ResponsiveContainer>
                      <BarChart data={c.financials}><XAxis dataKey="year" tick={{ fontSize: 11 }} /><YAxis tickFormatter={Mshort} tick={{ fontSize: 11 }} width={60} />
                        <Tooltip formatter={(v: number) => M(v)} /><ReferenceLine y={0} stroke="#9aa7b6" />
                        <Bar dataKey="net_profit" name="Net profit">{c.financials.map((f: any) => <Cell key={f.year} fill={f.net_profit < 0 ? '#b3261e' : '#138a4b'} />)}</Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </div>
          </Card>
        </div>

        <div className="space-y-4">
          <Card title="Recommended next steps">
            <ol className="text-sm space-y-1.5 list-decimal pl-4">{ex.recommended_actions?.map((a: string, i: number) => <li key={i}>{a}</li>)}</ol>
            {ex.requested_documents?.length > 0 && (
              <div className="mt-3">
                <div className="text-xs font-semibold text-muted uppercase tracking-wide">Documents to request</div>
                <ul className="text-sm mt-1 space-y-1">{ex.requested_documents.map((d: string, i: number) => <li key={i} className="flex gap-1.5"><FileWarning size={15} className="text-review shrink-0 mt-0.5" />{d}</li>)}</ul>
              </div>
            )}
          </Card>
          <Card title="Decision" className="no-print"><DecisionPanel c={c} onDone={setData} /></Card>
          {c.decisions.length > 0 && (
            <Card title="Decision history">
              <ul className="space-y-2 text-sm">{c.decisions.map((d: any, i: number) => (
                <li key={i}><div className="font-medium capitalize">{d.action.replace('_', ' ')} <span className="text-muted font-normal">by {d.username}</span></div>
                  <div className="text-muted">{d.comment}</div>
                  <div className="text-xs text-muted">{new Date(d.created_at + 'Z').toLocaleString()} · {d.followed_recommendation ? 'followed recommendation' : 'override of recommendation'}</div></li>
              ))}</ul>
            </Card>
          )}
          <Btn tone="ghost" className="no-print w-full" onClick={() => window.print()}><Printer size={16} />Print evidence pack</Btn>
        </div>
      </div>

      <Modal open={!!img} onClose={() => setImg(null)} title={img ? `${img.supplier_name} · ${img.invoice_no}` : ''} wide>
        {img && (
          <div className="grid md:grid-cols-5 gap-4">
            <div className="md:col-span-3 bg-paper rounded-lg p-2"><AuthImage path={`/invoices/${img.invoice_id}/image`} alt="Invoice image" className="w-full rounded" /></div>
            <div className="md:col-span-2 text-sm space-y-2">
              <InvoiceStatus flags={img.flags} />
              <dl className="grid grid-cols-2 gap-1 num">
                <dt className="text-muted">Net</dt><dd>{M(img.net, 2)}</dd><dt className="text-muted">VAT</dt><dd>{M(img.vat, 2)}</dd>
                <dt className="text-muted">Total</dt><dd>{M(img.total, 2)}</dd><dt className="text-muted">Date</dt><dd>{img.invoice_date}</dd>
              </dl>
              {img.messages.map((m: string, i: number) => <p key={i} className="text-muted">{m}</p>)}
              {img.duplicate && <Link to="#" onClick={e => { e.preventDefault() }} className="text-xs text-muted">Original: invoice #{img.duplicate.invoice_id}</Link>}
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
