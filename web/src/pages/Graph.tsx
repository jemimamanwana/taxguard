import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import cytoscape from 'cytoscape'
import { ArrowLeft, Printer } from 'lucide-react'
import { api } from '../lib/api'
import { M, Mshort, pct } from '../lib/format'
import { Btn, Card, Chip, ErrorBox, Spinner, useAsync } from '../components/ui'

const RISK_TONE: Record<string, 'risk' | 'warn' | 'good'> = { high: 'risk', medium: 'warn', low: 'good' }

function GroupList() {
  const nav = useNavigate()
  const { data, error, loading } = useAsync<any[]>(() => api('/graph/groups'), [])
  if (loading) return <Spinner />
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Multinational group explorer</h1>
        <p className="text-sm text-muted">Related-party structures of MNE groups with Lesotho subsidiaries, ranked by risk.</p>
      </div>
      <ErrorBox error={error} />
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {data?.map(g => (
          <button key={g.group_id} onClick={() => nav(`/groups/${g.group_id}`)} className="text-left bg-white border border-line rounded-xl p-4 hover:border-brand">
            <div className="flex justify-between items-start gap-2"><div className="font-semibold">{g.name}</div><Chip tone={RISK_TONE[g.risk]}>{g.risk} risk</Chip></div>
            <div className="text-xs text-muted mt-1">{g.entities} entities · {g.lesotho_entities} in Lesotho</div>
            <div className="flex gap-1 mt-2">{g.codes.map((c: string) => <Chip key={c} tone="risk">{c}</Chip>)}</div>
          </button>
        ))}
      </div>
    </div>
  )
}

function GraphCanvas({ g, onSelect }: { g: any; onSelect: (id: string) => void }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    const maxAmt = Math.max(1, ...g.edges.map((e: any) => e.amount))
    const cy = cytoscape({
      container: ref.current,
      elements: [
        ...g.nodes.map((n: any) => ({ data: { id: n.id, label: n.name.replace(' (Pty) Ltd', '').replace(' Ltd', '').replace(' plc', ''), jur: n.jurisdiction, kind: n.foreign ? (n.low_tax ? 'lowtax' : 'foreign') : 'local', flagged: n.flagged ? 1 : 0 } })),
        ...g.edges.map((e: any, i: number) => ({ data: { id: `e${i}`, source: e.source, target: e.target, w: 1.5 + 9 * Math.sqrt(e.amount / maxAmt), label: `${Object.keys(e.types).join(', ')} · ${Mshort(e.amount)}`, sus: e.suspicious ? 1 : 0 } })),
      ],
      style: [
        { selector: 'node', style: { label: 'data(label)', 'font-size': 11, 'text-wrap': 'wrap', 'text-max-width': '120px', 'text-valign': 'bottom', 'text-margin-y': 6, width: 34, height: 34, 'background-color': '#7d8b9c', color: '#0f1b2d', 'border-width': 2, 'border-color': '#fff' } },
        { selector: 'node[kind="local"]', style: { 'background-color': '#00209f', shape: 'round-rectangle', width: 40, height: 40 } },
        { selector: 'node[kind="lowtax"]', style: { 'background-color': '#e07a1f', shape: 'diamond', width: 42, height: 42 } },
        { selector: 'node[flagged=1]', style: { 'border-color': '#b3261e', 'border-width': 4 } },
        { selector: 'edge', style: { width: 'data(w)', 'line-color': '#b8c3cf', 'target-arrow-color': '#b8c3cf', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', label: 'data(label)', 'font-size': 9, color: '#5b6b80', 'text-background-color': '#fff', 'text-background-opacity': 1, 'text-background-padding': '2px', 'text-rotation': 'autorotate' } },
        { selector: 'edge[sus=1]', style: { 'line-color': '#b3261e', 'target-arrow-color': '#b3261e', color: '#b3261e' } },
        { selector: ':selected', style: { 'overlay-opacity': 0.15, 'overlay-color': '#00209f' } },
      ],
      layout: { name: 'cose', animate: false, padding: 40, nodeRepulsion: () => 90000, idealEdgeLength: () => 170 } as any,
      wheelSensitivity: 0.3,
    })
    cy.on('tap', 'node', e => onSelect(e.target.id()))
    return () => cy.destroy()
  }, [g, onSelect])
  return <div ref={ref} className="w-full h-[460px] bg-paper/60 rounded-lg" aria-label="Related-party graph" />
}

export default function Graph() {
  const { gid } = useParams()
  const [sel, setSel] = useState<string | null>(null)
  const { data: g, error, loading } = useAsync<any>(() => (gid ? api(`/graph/groups/${gid}`) : Promise.resolve(null)), [gid])
  useEffect(() => setSel(null), [gid])
  if (!gid) return <GroupList />
  if (loading) return <Spinner />
  if (error) return <ErrorBox error={error} />
  const node = g.nodes.find((n: any) => n.id === (sel ?? g.nodes.find((n: any) => n.flagged)?.id ?? g.nodes.find((n: any) => !n.foreign)?.id))
  const p = node?.profile
  return (
    <div className="space-y-4">
      <Link to="/groups" className="no-print text-sm text-muted hover:text-ink inline-flex items-center gap-1"><ArrowLeft size={15} />All groups</Link>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">{g.name} <Chip tone={RISK_TONE[g.risk]}>{g.risk} risk</Chip></h1>
          <p className="text-sm text-muted">Related-party flows in {g.year}. Edge thickness = amount; red = suspicious path.</p>
        </div>
        <Btn tone="ghost" className="no-print" onClick={() => window.print()}><Printer size={16} />Group risk summary</Btn>
      </div>
      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2" title="Group structure" actions={
          <div className="flex gap-3 text-xs text-muted">
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm bg-brand" />Lesotho entity</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full bg-[#7d8b9c]" />Foreign</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rotate-45 bg-[#e07a1f]" />Low-tax jurisdiction</span>
          </div>}>
          <GraphCanvas g={g} onSelect={setSel} />
        </Card>
        <div className="space-y-4">
          <Card title={node ? node.name : 'Entity'}>
            {node && (
              <div className="text-sm space-y-2">
                <div className="flex flex-wrap gap-1"><Chip>{node.jurisdiction}</Chip>{node.low_tax && <Chip tone="warn">low-tax</Chip>}<Chip>{node.role}</Chip><Chip>TIN {node.label_tin}</Chip></div>
                {p?.turnover != null ? (
                  <dl className="grid grid-cols-2 gap-x-2 gap-y-1 num">
                    <dt className="text-muted">Turnover {p.year}</dt><dd>{Mshort(p.turnover)}</dd>
                    <dt className="text-muted">Gross margin</dt><dd>{pct(p.gross_margin, 1)} <span className="text-muted text-xs">(sector {pct(p.sector_margin, 1)})</span></dd>
                    <dt className="text-muted">Net profit</dt><dd className={p.net_profit < 0 ? 'text-audit' : ''}>{Mshort(p.net_profit)}</dd>
                    <dt className="text-muted">Loss years in a row</dt><dd>{p.consecutive_loss_years}</dd>
                    <dt className="text-muted">Losses carried fwd</dt><dd>{Mshort(p.losses_carried_forward)}</dd>
                    <dt className="text-muted">RP charges / turnover</dt><dd>{pct(p.rp_charges_pct, 1)}</dd>
                    <dt className="text-muted">…to low-tax entities</dt><dd className={p.rp_lowtax_pct > 0.05 ? 'text-audit font-semibold' : ''}>{pct(p.rp_lowtax_pct, 1)}</dd>
                    <dt className="text-muted">Intra-group purchases</dt><dd>{pct(p.rp_goods_pct_of_purchases)}</dd>
                  </dl>
                ) : <p className="text-muted">Foreign group entity – no Lesotho filings. Payments it receives from Lesotho entities are shown as incoming edges.</p>}
              </div>
            )}
          </Card>
          <Card title={`Findings (${g.findings.length})`}>
            {g.findings.length ? (
              <ul className="space-y-2 text-sm">{g.findings.map((f: any, i: number) => (
                <li key={i} className="flex gap-2"><span className="font-mono text-xs font-semibold rounded bg-ink text-white px-1.5 py-0.5 h-fit">{f.code}</span><span>{f.text}</span></li>
              ))}</ul>
            ) : <p className="text-sm text-muted">No related-party risk indicators. Intra-group charges look consistent with arm’s-length levels.</p>}
            {g.suspicious_paths.length > 0 && <div className="text-xs text-muted mt-3">{g.suspicious_paths.length} suspicious path(s) from Lesotho entities to low-tax jurisdictions highlighted in red.</div>}
          </Card>
          <Card title="Flows">
            <ul className="text-xs space-y-1 num">{g.edges.map((e: any, i: number) => {
              const s = g.nodes.find((n: any) => n.id === e.source), t = g.nodes.find((n: any) => n.id === e.target)
              return <li key={i} className={e.suspicious ? 'text-audit' : ''}>{s?.name.split(' ')[0]} → {t?.name.split(' ').slice(0, 2).join(' ')}: {Object.entries(e.types).map(([k, v]: any) => `${k} ${M(v)}`).join(', ')}</li>
            })}</ul>
          </Card>
        </div>
      </div>
    </div>
  )
}
