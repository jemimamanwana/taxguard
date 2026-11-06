import { useEffect, useState, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { apiBlobUrl } from '../lib/api'
import { LANE_LABEL } from '../lib/format'

export function Card({ title, actions, children, className = '', pad = true }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; pad?: boolean }) {
  return (
    <section className={`bg-white border border-line rounded-xl ${className}`}>
      {title && (
        <header className="flex items-center justify-between gap-3 px-4 py-3 border-b border-line">
          <h2 className="text-sm font-semibold text-ink">{title}</h2>
          {actions}
        </header>
      )}
      <div className={pad ? 'p-4' : ''}>{children}</div>
    </section>
  )
}

const laneCls: Record<string, string> = {
  fast_track: 'bg-fast-soft text-fast ring-fast/25',
  review: 'bg-review-soft text-review ring-review/25',
  audit: 'bg-audit-soft text-audit ring-audit/25',
}

export function LanePill({ lane, large = false }: { lane?: string | null; large?: boolean }) {
  if (!lane) return <span className="text-muted">—</span>
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full ring-1 font-semibold whitespace-nowrap ${laneCls[lane]} ${large ? 'px-3.5 py-1.5 text-base' : 'px-2.5 py-0.5 text-xs'}`}>
      <span className={`rounded-full ${large ? 'w-2.5 h-2.5' : 'w-1.5 h-1.5'} ${lane === 'fast_track' ? 'bg-fast' : lane === 'review' ? 'bg-review' : 'bg-audit'}`} />
      {LANE_LABEL[lane]}
    </span>
  )
}

export function ScoreBar({ score, width = 'w-20' }: { score?: number | null; width?: string }) {
  const s = score ?? 0
  const col = s >= 35 ? 'bg-audit' : s >= 15 ? 'bg-review' : 'bg-fast'
  return (
    <div className="flex items-center gap-2">
      <div className={`${width} h-1.5 rounded-full bg-line overflow-hidden`}>
        <div className={`h-full ${col}`} style={{ width: `${Math.min(100, s)}%` }} />
      </div>
      <span className="num text-xs text-muted w-7 text-right">{s.toFixed(0)}</span>
    </div>
  )
}

export function Chip({ children, tone = 'neutral', title }: { children: ReactNode; tone?: 'neutral' | 'risk' | 'good' | 'warn' | 'brand'; title?: string }) {
  const cls = {
    neutral: 'bg-paper text-muted ring-line', risk: 'bg-audit-soft text-audit ring-audit/20',
    good: 'bg-fast-soft text-fast ring-fast/20', warn: 'bg-review-soft text-review ring-review/20',
    brand: 'bg-brand-soft text-brand ring-brand/20',
  }[tone]
  return <span title={title} className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px] font-medium ring-1 ${cls}`}>{children}</span>
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: 'fast' | 'review' | 'audit' | 'brand' }) {
  const bar = tone ? { fast: 'border-l-fast', review: 'border-l-review', audit: 'border-l-audit', brand: 'border-l-brand' }[tone] : 'border-l-line'
  return (
    <div className={`bg-white border border-line border-l-4 ${bar} rounded-xl px-4 py-3`}>
      <div className="text-xs text-muted">{label}</div>
      <div className="text-2xl font-semibold num mt-0.5">{value}</div>
      {sub && <div className="text-xs text-muted mt-0.5">{sub}</div>}
    </div>
  )
}

export function AuthImage({ path, alt, className }: { path: string; alt: string; className?: string }) {
  const [url, setUrl] = useState<string | null>(null)
  const [err, setErr] = useState(false)
  useEffect(() => {
    let u: string | null = null
    setUrl(null); setErr(false)
    apiBlobUrl(path).then(x => { u = x; setUrl(x) }).catch(() => setErr(true))
    return () => { if (u) URL.revokeObjectURL(u) }
  }, [path])
  if (err) return <div className="text-sm text-muted p-6 text-center">Image unavailable</div>
  if (!url) return <div className="animate-pulse bg-paper rounded-lg h-64" />
  return <img src={url} alt={alt} className={className} />
}

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 bg-ink/50 flex items-start justify-center p-4 overflow-auto" onClick={onClose}>
      <div role="dialog" aria-label={title} className={`bg-white rounded-xl shadow-xl w-full ${wide ? 'max-w-5xl' : 'max-w-2xl'} my-8`} onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-line">
          <h3 className="font-semibold">{title}</h3>
          <button onClick={onClose} aria-label="Close" className="p-1 rounded hover:bg-paper"><X size={18} /></button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  )
}

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted p-6">
      <span className="w-4 h-4 rounded-full border-2 border-brand border-t-transparent animate-spin" />{label}
    </div>
  )
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null
  return <div className="rounded-lg bg-audit-soft text-audit text-sm px-3 py-2">{String((error as Error).message || error)}</div>
}

export function Btn({ children, onClick, tone = 'primary', disabled, type = 'button', className = '', title }: {
  children: ReactNode; onClick?: () => void; tone?: 'primary' | 'ghost' | 'fast' | 'review' | 'audit'; disabled?: boolean; type?: 'button' | 'submit'; className?: string; title?: string
}) {
  const cls = {
    primary: 'bg-brand text-white hover:bg-brand-dark', ghost: 'bg-white text-ink ring-1 ring-line hover:bg-paper',
    fast: 'bg-fast text-white hover:brightness-95', review: 'bg-review text-white hover:brightness-95', audit: 'bg-audit text-white hover:brightness-95',
  }[tone]
  return (
    <button type={type} title={title} disabled={disabled} onClick={onClick}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition disabled:opacity-40 disabled:cursor-not-allowed ${cls} ${className}`}>
      {children}
    </button>
  )
}

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)
  const [n, setN] = useState(0)
  useEffect(() => {
    let alive = true
    setLoading(true); setError(null)
    fn().then(d => alive && setData(d)).catch(e => alive && setError(e)).finally(() => alive && setLoading(false))
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, n])
  return { data, error, loading, reload: () => setN(x => x + 1), setData }
}
