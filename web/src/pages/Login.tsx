import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, session, type User } from '../lib/api'
import { ROLE_LABEL } from '../lib/format'
import { Btn, ErrorBox, useAsync } from '../components/ui'
import { Logo } from '../App'

export default function Login() {
  const nav = useNavigate()
  const [username, setU] = useState('')
  const [password, setP] = useState('')
  const [err, setErr] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const demo = useAsync<{ username: string; full_name: string; role: string }[]>(() => api('/auth/demo-users'), [])

  async function login(u = username, p = password) {
    setBusy(true); setErr(null)
    try {
      const r = await api<{ token: string; user: User }>('/auth/login', { method: 'POST', json: { username: u, password: p } })
      session.set(r.token, r.user)
      nav(r.user.role === 'taxpayer' ? '/portal' : '/queue')
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  return (
    <div className="min-h-full grid md:grid-cols-2">
      <div className="hidden md:flex flex-col justify-between bg-brand text-white p-10">
        <Logo light />
        <div>
          <h1 className="text-3xl font-semibold leading-tight max-w-md">Pay legitimate VAT refunds faster. Catch abusive ones with evidence.</h1>
          <ul className="mt-6 space-y-2 text-white/85 text-sm max-w-md">
            <li>• Every claim scored into <b>Fast-track</b>, <b>Officer review</b> or <b>Audit</b></li>
            <li>• Every flag explained in plain language, with the evidence behind it</li>
            <li>• Invoices read from photos and cross-matched with supplier declarations</li>
            <li>• Multinational group structures and intra-group charges made visible</li>
          </ul>
        </div>
        <div className="text-xs text-white/60">RSL Taxathon 2026 · Challenge #2 · Prototype using synthetic data only</div>
      </div>
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="md:hidden mb-8"><Logo /></div>
          <h2 className="text-xl font-semibold">Sign in</h2>
          <form className="mt-4 space-y-3" onSubmit={e => { e.preventDefault(); login() }}>
            <input aria-label="Username" className="w-full rounded-lg border border-line px-3 py-2" placeholder="Username" value={username} onChange={e => setU(e.target.value)} />
            <input aria-label="Password" type="password" className="w-full rounded-lg border border-line px-3 py-2" placeholder="Password" value={password} onChange={e => setP(e.target.value)} />
            <ErrorBox error={err} />
            <Btn type="submit" disabled={busy} className="w-full">Sign in</Btn>
          </form>
          <div className="mt-8">
            <div className="text-xs font-semibold text-muted uppercase tracking-wide">Demo accounts (password: demo)</div>
            <div className="mt-2 grid gap-1.5">
              {(demo.data || []).map(u => (
                <button key={u.username} onClick={() => login(u.username, 'demo')}
                  className="text-left rounded-lg border border-line bg-white hover:border-brand px-3 py-2 flex justify-between items-center">
                  <span className="text-sm font-medium">{u.full_name}</span>
                  <span className="text-xs text-muted">{ROLE_LABEL[u.role]}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
