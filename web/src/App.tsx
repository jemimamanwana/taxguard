import { BrowserRouter, Navigate, NavLink, Outlet, Route, Routes, useNavigate } from 'react-router-dom'
import { BarChart3, FlaskConical, Inbox, LogOut, Network, ScanLine, Settings, ShieldCheck, Menu } from 'lucide-react'
import { useState } from 'react'
import { session } from './lib/api'
import { ROLE_LABEL } from './lib/format'
import { lazy, Suspense } from 'react'
import Login from './pages/Login'
import Queue from './pages/Queue'
import { Spinner } from './components/ui'
const CaseView = lazy(() => import('./pages/CaseView'))
const Graph = lazy(() => import('./pages/Graph'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const ScanInvoice = lazy(() => import('./pages/ScanInvoice'))
const Evaluation = lazy(() => import('./pages/Evaluation'))
const Admin = lazy(() => import('./pages/Admin'))
const Portal = lazy(() => import('./pages/Portal'))

const NAV = [
  { to: '/queue', label: 'Refund queue', icon: Inbox, roles: ['refund_auditor', 'special_sectors', 'risk_analyst', 'admin'] },
  { to: '/dashboard', label: 'Dashboard', icon: BarChart3, roles: ['refund_auditor', 'special_sectors', 'risk_analyst', 'admin'] },
  { to: '/groups', label: 'Group explorer', icon: Network, roles: ['special_sectors', 'risk_analyst', 'admin', 'refund_auditor'] },
  { to: '/scan', label: 'Scan invoice', icon: ScanLine, roles: ['refund_auditor', 'special_sectors', 'risk_analyst', 'admin'] },
  { to: '/evaluation', label: 'Evidence & evaluation', icon: FlaskConical, roles: ['refund_auditor', 'special_sectors', 'risk_analyst', 'admin'] },
  { to: '/admin', label: 'Rules & audit log', icon: Settings, roles: ['admin', 'risk_analyst'] },
]

export function Logo({ light = false }: { light?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden>
        <rect width="32" height="32" rx="8" fill={light ? '#ffffff' : '#00209f'} />
        <circle cx="15" cy="14.5" r="6.8" fill="none" stroke={light ? '#00209f' : '#fff'} strokeWidth="3" />
        <path d="M20 19.5l5.5 5.5" stroke="#00b35c" strokeWidth="3.6" strokeLinecap="round" />
      </svg>
      <div className="leading-tight">
        <div className={`font-semibold tracking-tight ${light ? 'text-white' : 'text-ink'}`}>TaxGuard</div>
        <div className={`text-[11px] ${light ? 'text-white/70' : 'text-muted'}`}>Tax risk analytics · RSL</div>
      </div>
    </div>
  )
}

function Shell() {
  const user = session.user()
  const nav = useNavigate()
  const [open, setOpen] = useState(false)
  if (!user) return <Navigate to="/login" replace />
  if (user.role === 'taxpayer') return <Navigate to="/portal" replace />
  const items = NAV.filter(n => n.roles.includes(user.role))
  return (
    <div className="min-h-full flex">
      <aside className={`no-print fixed inset-y-0 left-0 z-40 w-60 bg-white border-r border-line flex flex-col transition-transform md:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="px-4 py-4 border-b border-line"><Logo /></div>
        <nav className="flex-1 p-2 space-y-0.5">
          {items.map(n => (
            <NavLink key={n.to} to={n.to} onClick={() => setOpen(false)}
              className={({ isActive }) => `flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm ${isActive ? 'bg-brand-soft text-brand font-semibold' : 'text-ink hover:bg-paper'}`}>
              <n.icon size={17} />{n.label}
            </NavLink>
          ))}
        </nav>
        <div className="p-3 border-t border-line">
          <div className="text-sm font-medium">{user.full_name}</div>
          <div className="text-xs text-muted flex items-center gap-1"><ShieldCheck size={12} />{ROLE_LABEL[user.role]}</div>
          <button onClick={() => { session.clear(); nav('/login') }} className="mt-2 text-xs text-muted hover:text-ink flex items-center gap-1"><LogOut size={13} />Sign out</button>
        </div>
        <div className="px-3 pb-3 text-[10px] leading-snug text-muted">Prototype · synthetic data only. The system recommends; officers decide.</div>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-ink/30 md:hidden" onClick={() => setOpen(false)} />}
      <div className="flex-1 md:ml-60 min-w-0">
        <div className="no-print md:hidden sticky top-0 z-20 bg-white border-b border-line px-4 py-2 flex items-center gap-3">
          <button aria-label="Menu" onClick={() => setOpen(true)} className="p-1.5 rounded hover:bg-paper"><Menu size={20} /></button>
          <Logo />
        </div>
        <main className="p-4 md:p-6 max-w-[1400px] mx-auto print-full"><Suspense fallback={<Spinner />}><Outlet /></Suspense></main>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/portal" element={<Suspense fallback={<Spinner />}><Portal /></Suspense>} />
        <Route element={<Shell />}>
          <Route path="/queue" element={<Queue />} />
          <Route path="/claims/:id" element={<CaseView />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/groups" element={<Graph />} />
          <Route path="/groups/:gid" element={<Graph />} />
          <Route path="/scan" element={<ScanInvoice />} />
          <Route path="/evaluation" element={<Evaluation />} />
          <Route path="/admin" element={<Admin />} />
        </Route>
        <Route path="*" element={<Navigate to={session.user()?.role === 'taxpayer' ? '/portal' : '/queue'} replace />} />
      </Routes>
    </BrowserRouter>
  )
}
