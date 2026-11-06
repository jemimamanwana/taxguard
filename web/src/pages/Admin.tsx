import { useEffect, useState } from 'react'
import { api, session } from '../lib/api'
import { RULE_SHORT } from '../lib/format'
import { Btn, Card, ErrorBox, Spinner, useAsync } from '../components/ui'

const LABELS: Record<string, string> = {
  lane_review_threshold: 'Officer review from score', lane_audit_threshold: 'Audit from score',
  capital_verify_vat: 'Capital VAT needing one-document check (M)', r01_min_months: 'R01 – refund months (of 12)',
  r02_gap_pct: 'R02 – unsupported input VAT tolerance', r06_peer_z: 'R06 – peer deviation (robust z)', r07_spike_z: 'R07 – spike z-score',
  r09_lowtax_pct: 'R09 – low-tax charges / turnover', r10_loss_years: 'R10 – consecutive loss years',
}

export default function Admin() {
  const user = session.user()!
  const isAdmin = user.role === 'admin'
  const s = useAsync<any>(() => api('/admin/settings'), [])
  const log = useAsync<any[]>(() => (isAdmin ? api('/admin/audit-log?limit=200') : Promise.resolve([])), [])
  const [form, setForm] = useState<any>(null)
  const [reason, setReason] = useState('')
  const [err, setErr] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  useEffect(() => { if (s.data) setForm(structuredClone(s.data.settings)) }, [s.data])

  async function save() {
    setBusy(true); setErr(null); setMsg('')
    try {
      await api('/admin/settings', { method: 'PUT', json: { settings: form, reason } })
      setMsg('Saved. All claims were re-scored with the new settings.'); setReason(''); s.reload(); log.reload()
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  if (s.loading || !form) return <Spinner />
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Rules, thresholds & audit log</h1>
        <p className="text-sm text-muted">{isAdmin ? 'Changes re-score every claim and are recorded in the audit log with your reason.' : 'Read-only for risk analysts – an administrator applies changes.'}</p>
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Lane thresholds & rule parameters">
          <div className="grid sm:grid-cols-2 gap-3">
            {Object.keys(LABELS).map(k => (
              <label key={k} className="text-xs text-muted">{LABELS[k]}
                <input type="number" step="any" disabled={!isAdmin} value={form[k]} onChange={e => setForm({ ...form, [k]: Number(e.target.value) })}
                  className="mt-1 w-full rounded-lg border border-line px-2 py-1.5 text-sm text-ink num disabled:bg-paper" />
              </label>
            ))}
          </div>
        </Card>
        <Card title="Rule weights (maximum points)">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {Object.entries(form.weights).map(([k, v]: any) => (
              <label key={k} className="text-xs text-muted">{k} · {RULE_SHORT[k]}
                <input type="number" disabled={!isAdmin} value={v} onChange={e => setForm({ ...form, weights: { ...form.weights, [k]: Number(e.target.value) } })}
                  className="mt-1 w-full rounded-lg border border-line px-2 py-1.5 text-sm text-ink num disabled:bg-paper" />
              </label>
            ))}
          </div>
          {isAdmin && (
            <div className="mt-4 space-y-2">
              <input value={reason} onChange={e => setReason(e.target.value)} placeholder="Reason for change (required)" className="w-full rounded-lg border border-line px-3 py-2 text-sm" />
              <ErrorBox error={err} />{msg && <div className="text-sm text-fast">{msg}</div>}
              <div className="flex gap-2">
                <Btn onClick={save} disabled={busy || reason.trim().length < 5}>{busy ? 'Re-scoring…' : 'Save & re-score'}</Btn>
                <Btn tone="ghost" onClick={() => setForm(structuredClone(s.data.defaults))}>Load defaults</Btn>
              </div>
            </div>
          )}
        </Card>
      </div>
      {isAdmin && (
        <Card title="Audit log (latest 200)" pad={false}>
          <div className="overflow-x-auto max-h-[480px]">
            <table className="w-full text-xs">
              <thead className="bg-paper text-muted text-left sticky top-0"><tr><th className="px-3 py-2">Time (UTC)</th><th className="px-3 py-2">User</th><th className="px-3 py-2">Role</th><th className="px-3 py-2">Action</th><th className="px-3 py-2">Entity</th><th className="px-3 py-2">Detail</th></tr></thead>
              <tbody>{log.data?.map((r, i) => (
                <tr key={i} className="border-t border-line"><td className="px-3 py-1.5 num whitespace-nowrap">{String(r.ts).replace('T', ' ').slice(0, 19)}</td><td className="px-3 py-1.5">{r.username}</td>
                  <td className="px-3 py-1.5 text-muted">{r.role}</td><td className="px-3 py-1.5 font-medium">{r.action}</td><td className="px-3 py-1.5">{r.entity}</td>
                  <td className="px-3 py-1.5 text-muted max-w-md truncate" title={r.detail}>{r.detail}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}
