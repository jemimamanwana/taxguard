import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../lib/api'
import { Mshort, pct } from '../lib/format'
import { Card, ErrorBox, Spinner, Stat, useAsync } from '../components/ui'

export default function Dashboard() {
  const { data: d, error, loading } = useAsync<any>(() => api('/dashboard/metrics'), [])
  if (loading) return <Spinner />
  if (error) return <ErrorBox error={error} />
  const bl = d.pending.by_lane
  const ta = d.turnaround_assumption_days
  const all = d.all_time
  const weighted = all.fast_track_share * ta.fast_track + (1 - all.fast_track_share) * ((ta.review + ta.audit) / 2)
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Refund operations dashboard</h1>
        <p className="text-sm text-muted">Synthetic portfolio of 500 taxpayers, 24 months. Turnaround figures use the stated assumptions until pilot data replaces them.</p>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Claims awaiting decision" value={d.pending.claims} sub={`${Mshort(d.pending.value)} claimed`} tone="brand" />
        <Stat label="Ready to fast-track" value={bl.fast_track?.n ?? 0} sub={`${Mshort(bl.fast_track?.value)} can be paid quickly`} tone="fast" />
        <Stat label="Officer review" value={bl.review?.n ?? 0} sub={`${Mshort(bl.review?.value)} – specific items to check`} tone="review" />
        <Stat label="Audit" value={bl.audit?.n ?? 0} sub={`${Mshort(bl.audit?.value)} – evidence packs ready`} tone="audit" />
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Share of claims fast-tracked (24m)" value={pct(all.fast_track_share)} sub={`${all.fast_tracked} claims · ${Mshort(all.fast_tracked_value)}`} />
        <Stat label="Est. VAT protected (evidence-based)" value={Mshort(all.estimated_vat_protected)} sub="Unsupported, undeclared-supplier and duplicate VAT on flagged claims" />
        <Stat label="Avg. turnaround (assumed)" value={`${weighted.toFixed(0)} days`} sub={`vs ~${ta.current_manual_average} days manual baseline`} />
        <Stat label="Officer decisions recorded" value={d.decisions.count} sub={`${d.decisions.followed_recommendation} followed the recommendation`} />
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Claims per month by lane">
          <div className="h-72">
            <ResponsiveContainer>
              <BarChart data={d.by_period}>
                <CartesianGrid stroke="#eef1f5" vertical={false} />
                <XAxis dataKey="period" tick={{ fontSize: 11 }} interval={2} /><YAxis tick={{ fontSize: 11 }} />
                <Tooltip /><Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="fast_track" stackId="a" name="Fast-track" fill="#138a4b" />
                <Bar dataKey="review" stackId="a" name="Officer review" fill="#e0a526" />
                <Bar dataKey="audit" stackId="a" name="Audit" fill="#b3261e" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="Refund value per month by lane">
          <div className="h-72">
            <ResponsiveContainer>
              <BarChart data={d.value_by_period}>
                <CartesianGrid stroke="#eef1f5" vertical={false} />
                <XAxis dataKey="period" tick={{ fontSize: 11 }} interval={2} /><YAxis tickFormatter={Mshort} tick={{ fontSize: 11 }} width={70} />
                <Tooltip formatter={(v: number) => Mshort(v)} /><Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="fast_track" stackId="a" name="Fast-track" fill="#138a4b" />
                <Bar dataKey="review" stackId="a" name="Officer review" fill="#e0a526" />
                <Bar dataKey="audit" stackId="a" name="Audit" fill="#b3261e" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>
      <Card title="By sector">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-muted text-left"><tr><th className="py-1.5">Sector</th><th className="text-right">Claims</th><th className="text-right">Flagged</th><th className="text-right">Flag rate</th><th className="text-right">VAT at risk (evidence)</th></tr></thead>
            <tbody>{d.by_sector.sort((a: any, b: any) => b.at_risk - a.at_risk).map((s: any) => (
              <tr key={s.sector} className="border-t border-line num"><td className="py-1.5">{s.sector}</td><td className="text-right">{s.claims}</td><td className="text-right">{s.flagged}</td>
                <td className="text-right">{pct(s.flagged / s.claims)}</td><td className="text-right">{Mshort(s.at_risk)}</td></tr>
            ))}</tbody>
          </table>
        </div>
        <p className="text-xs text-muted mt-2">Turnaround assumptions (days): fast-track {ta.fast_track}, review {ta.review}, audit {ta.audit}, current manual {ta.current_manual_average}. To be replaced with measured values during the pilot.</p>
      </Card>
    </div>
  )
}
