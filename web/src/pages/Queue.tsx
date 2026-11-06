import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import { api } from '../lib/api'
import { M, RULE_SHORT } from '../lib/format'
import { Chip, ErrorBox, LanePill, ScoreBar, Spinner, useAsync } from '../components/ui'

type Row = {
  claim_id: number; tin: string; taxpayer: string; sector: string; period: string; refund_claimed: number; status: string
  score: number; lane: string; assigned_officer: string; codes: string[]; mitigations: string[]; summary: string; source: string
}

const TABS = [
  { k: '', label: 'All' }, { k: 'audit', label: 'Audit' }, { k: 'review', label: 'Officer review' }, { k: 'fast_track', label: 'Fast-track' },
]

export default function Queue() {
  const nav = useNavigate()
  const [lane, setLane] = useState('')
  const [status, setStatus] = useState('pending')
  const [sector, setSector] = useState('')
  const [period, setPeriod] = useState('')
  const [q, setQ] = useState('')
  const [mine, setMine] = useState(false)
  const filters = useAsync<{ sectors: string[]; periods: string[] }>(() => api('/claims/filters'), [])
  const params = new URLSearchParams({ status, ...(lane && { lane }), ...(sector && { sector }), ...(period && { period }), ...(q && { q }), ...(mine && { mine: 'true' }) })
  const data = useAsync<{ total: number; lane_counts: Record<string, number>; items: Row[] }>(() => api(`/claims?${params}&limit=300`), [params.toString()])
  const counts = data.data?.lane_counts || {}
  const all = Object.values(counts).reduce((a, b) => a + b, 0)

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Refund queue</h1>
          <p className="text-sm text-muted">Highest risk first. The lane is a recommendation – you make the decision.</p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2" role="tablist">
        {TABS.map(t => {
          const n = t.k ? counts[t.k] || 0 : all
          const active = lane === t.k
          return (
            <button key={t.k} role="tab" aria-selected={active} onClick={() => setLane(t.k)}
              className={`rounded-lg px-3 py-1.5 text-sm ring-1 ${active ? 'bg-ink text-white ring-ink' : 'bg-white ring-line hover:bg-paper'}`}>
              {t.label} <span className={`num ml-1 ${active ? 'text-white/70' : 'text-muted'}`}>{n}</span>
            </button>
          )
        })}
      </div>

      <div className="mt-3 flex flex-wrap gap-2 items-center">
        <div className="relative">
          <Search size={15} className="absolute left-2.5 top-2.5 text-muted" />
          <input aria-label="Search taxpayer" value={q} onChange={e => setQ(e.target.value)} placeholder="Search taxpayer"
            className="pl-8 pr-3 py-1.5 rounded-lg border border-line text-sm w-56" />
        </div>
        <select aria-label="Status" value={status} onChange={e => setStatus(e.target.value)} className="rounded-lg border border-line text-sm px-2 py-1.5 bg-white">
          <option value="pending">Pending decision</option><option value="docs_requested">Documents requested</option>
          <option value="escalated">Escalated</option><option value="approved">Approved</option><option value="all">All statuses</option>
        </select>
        <select aria-label="Sector" value={sector} onChange={e => setSector(e.target.value)} className="rounded-lg border border-line text-sm px-2 py-1.5 bg-white">
          <option value="">All sectors</option>{filters.data?.sectors.map(s => <option key={s}>{s}</option>)}
        </select>
        <select aria-label="Period" value={period} onChange={e => setPeriod(e.target.value)} className="rounded-lg border border-line text-sm px-2 py-1.5 bg-white">
          <option value="">All periods</option>{filters.data?.periods.map(s => <option key={s}>{s}</option>)}
        </select>
        <label className="text-sm flex items-center gap-1.5"><input type="checkbox" checked={mine} onChange={e => setMine(e.target.checked)} />Assigned to me</label>
      </div>

      <div className="mt-4 bg-white border border-line rounded-xl overflow-hidden">
        {data.loading && !data.data ? <Spinner /> : <ErrorBox error={data.error} />}
        {data.data && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-paper text-xs text-muted text-left">
                <tr>
                  <th className="px-3 py-2 font-medium">Lane</th><th className="px-3 py-2 font-medium">Risk</th>
                  <th className="px-3 py-2 font-medium">Taxpayer</th><th className="px-3 py-2 font-medium">Period</th>
                  <th className="px-3 py-2 font-medium text-right">Refund claimed</th><th className="px-3 py-2 font-medium">Why</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.data.items.map(r => (
                  <tr key={r.claim_id} onClick={() => nav(`/claims/${r.claim_id}`)} className="border-t border-line hover:bg-brand-soft/40 cursor-pointer"
                    tabIndex={0} onKeyDown={e => e.key === 'Enter' && nav(`/claims/${r.claim_id}`)}>
                    <td className="px-3 py-2.5"><LanePill lane={r.lane} /></td>
                    <td className="px-3 py-2.5"><ScoreBar score={r.score} /></td>
                    <td className="px-3 py-2.5">
                      <div className="font-medium">{r.taxpayer}</div>
                      <div className="text-xs text-muted">{r.sector} · TIN {r.tin}{r.source === 'portal' && ' · via portal'}</div>
                    </td>
                    <td className="px-3 py-2.5 num">{r.period}</td>
                    <td className="px-3 py-2.5 text-right num font-medium">{M(r.refund_claimed)}</td>
                    <td className="px-3 py-2.5">
                      <div className="flex flex-wrap gap-1 max-w-xs">
                        {r.codes.slice(0, 4).map(c => <Chip key={c} tone="risk" title={RULE_SHORT[c]}>{c} {RULE_SHORT[c]}</Chip>)}
                        {r.codes.length > 4 && <Chip>+{r.codes.length - 4}</Chip>}
                        {r.mitigations.map(c => <Chip key={c} tone="good" title={RULE_SHORT[c]}>{c} {RULE_SHORT[c]}</Chip>)}
                        {!r.codes.length && !r.mitigations.length && <span className="text-xs text-muted">No flags</span>}
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-xs text-muted capitalize">{r.status.replace('_', ' ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!data.data.items.length && <div className="p-8 text-center text-sm text-muted">No claims match these filters.</div>}
            <div className="px-3 py-2 text-xs text-muted border-t border-line">{data.data.total} claims</div>
          </div>
        )}
      </div>
    </div>
  )
}
