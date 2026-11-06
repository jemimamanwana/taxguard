import { api } from '../lib/api'
import { Mshort, pct } from '../lib/format'
import { AuthImage, Card, ErrorBox, Spinner, Stat, useAsync } from '../components/ui'

const SCEN: Record<string, string> = {
  normal: 'Ordinary taxpayer (occasional refund)', exporter: 'Exporter – zero-rated sales', seasonal: 'Seasonal FMCG wholesaler',
  capital_newbiz: 'New business – capital purchases', mne_armslength: 'MNE subsidiary – arm’s length',
  abuse_unsupported: 'Input VAT without invoices', abuse_phantom: 'Phantom supplier invoices', abuse_duplicate: 'Duplicate invoices',
  abuse_reverse_charge: 'Missing reverse-charge VAT', abuse_profit_shift: 'Profit shifting to low-tax sister', abuse_low_margin: 'Low margin / intra-group purchases',
  incomplete_records: 'Exporter with missing / contradictory records', demo_exporter: 'Demo 1 – exporter', demo_newbiz: 'Demo 2 – new distributor', demo_abuse: 'Demo 3 – retail group',
}

export default function Evaluation() {
  const { data: r, error, loading } = useAsync<any>(() => api('/eval/results'), [])
  if (loading) return <Spinner />
  if (error) return <ErrorBox error={error} />
  const m = r.model, b = r.baseline_same_volume, inv = r.invoices
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Performance & evidence</h1>
        <p className="text-sm text-muted max-w-3xl">Scored on {r.dataset.claims.toLocaleString()} labelled synthetic claims ({r.dataset.abusive_claims} abusive) from {r.dataset.taxpayers} taxpayers,
          {` ${r.dataset.periods}`}. Baseline = “review every claim above M {Math.round(b.threshold).toLocaleString()}”, set to flag the same number of claims as TaxGuard.</p>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Precision (flagged claims that are abusive)" value={pct(m.precision)} sub={`baseline ${pct(b.precision)}`} tone="brand" />
        <Stat label="Recall (abusive claims caught)" value={pct(m.recall)} sub={`baseline ${pct(b.recall)}`} tone="brand" />
        <Stat label="Legit refunds fast-tracked (complete records)" value={pct(r.legit_fast_track_rate_complete_records)} sub={`${pct(r.legit_fast_track_rate)} incl. records requests · baseline ${pct(1 - b.false_positive_rate)}`} tone="fast" />
        <Stat label="Abusive refund value flagged" value={Mshort(r.abusive_value_flagged_model)} sub={`baseline ${Mshort(r.abusive_value_flagged_baseline)} of ${Mshort(r.abusive_value_total)}`} tone="audit" />
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Flags with a plain-language explanation" value={pct(r.explainability.explained_share)} sub={`${r.explainability.flags_fired.toLocaleString()} flags fired`} />
        <Stat label="Claims sent for missing records" value={r.records_requested.claims} sub={`${r.records_requested.abusive_among_them} abusive – a document request, not a risk flag`} />
        <Stat label="Case view response (median / p95)" value={`${r.performance.case_view.median_ms} ms`} sub={`p95 ${r.performance.case_view.p95_ms} ms · queue ${r.performance.queue.median_ms} ms`} />
        <Stat label="Overall incl. records requests" value={`P ${pct(r.model_incl_records_requests.precision)}`} sub={`recall ${pct(r.model_incl_records_requests.recall)} · ${r.model_incl_records_requests.flagged} claims to review/audit`} />
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Model vs amount-based baseline"><AuthImage path="/eval/charts/model_vs_baseline.png" alt="Model vs baseline chart" className="w-full" /></Card>
        <Card title="Threshold sensitivity"><AuthImage path="/eval/charts/threshold_sensitivity.png" alt="Threshold sensitivity chart" className="w-full" /></Card>
      </div>
      <div className="grid lg:grid-cols-3 gap-4">
        <Card title="Confusion matrix (any flag = review or audit)">
          <table className="w-full text-sm num text-center">
            <thead><tr className="text-xs text-muted"><th /><th>Flagged</th><th>Fast-tracked</th></tr></thead>
            <tbody>
              <tr><th className="text-left text-xs text-muted py-2">Abusive</th><td className="bg-fast-soft font-semibold">{m.tp}</td><td className="bg-audit-soft">{m.fn}</td></tr>
              <tr><th className="text-left text-xs text-muted py-2">Legitimate</th><td className="bg-review-soft">{m.fp}</td><td className="bg-fast-soft font-semibold">{m.tn}</td></tr>
            </tbody>
          </table>
          <div className="text-xs text-muted mt-2">F1 {m.f1} vs baseline {b.f1}. Audit lane alone: precision {pct(r.model_audit_lane.precision)}, recall {pct(r.model_audit_lane.recall)}.</div>
        </Card>
        <Card title="Invoice-level detection">
          <ul className="text-sm space-y-1.5">
            <li>Phantom-supplier invoices caught: <b className="num">{inv.phantom_caught}/{inv.phantom_invoices}</b> ({pct(inv.phantom_recall)}); genuine invoices wrongly flagged: <b>{inv.genuine_flagged_nomatch}</b></li>
            <li>Duplicate invoices caught: <b className="num">{inv.duplicates_caught}/{inv.duplicate_invoices}</b> ({pct(inv.duplicate_recall)}); false alarms: <b>{inv.duplicate_false_alarms}</b></li>
            <li>Altered-number copies caught: <b className="num">{inv.altered_number_caught}/{inv.altered_number_copies}</b></li>
          </ul>
          {r.ocr ? (
            <div className="mt-3 text-sm border-t border-line pt-2">
              <b>OCR ({r.ocr.extractor}, {r.ocr.images} images):</b> field accuracy {pct(r.ocr.field_accuracy, 1)}, fully automatic {pct(r.ocr.fully_automatic_rate)},
              wrong-but-confident {r.ocr.confident_errors} field(s); ~${r.ocr.cost_per_invoice_usd?.toFixed(4)} per invoice.
            </div>
          ) : <div className="mt-3 text-xs text-muted border-t border-line pt-2">OCR accuracy: run <code>python -m eval.ocr_eval</code> with an API key to add field-level results.</div>}
        </Card>
        <Card title="Known limitations">
          <ul className="text-xs text-muted space-y-1.5 list-disc pl-4">
            <li>Synthetic data: abuse patterns are ones we designed, so real-world precision/recall will be lower. Shadow-mode pilot needed.</li>
            <li>Lane thresholds were set on this same dataset – risk of over-fitting; re-calibrate on pilot data.</li>
            <li>Supplier cross-match needs invoice-level sales listings or e-invoicing; with only return totals it weakens.</li>
            <li>Perceptual image hash alone can’t separate re-photos from different invoices on one template – duplicates are confirmed with field matching.</li>
            <li>Low-intensity input-VAT inflation (&lt;10% gap) is the main source of missed abuse ({r.errors.false_negatives_by_scenario.abuse_unsupported ?? 0} claims).</li>
            <li>Legitimate claims sent to review are mostly one-document capital-asset checks or missing-records requests, by design.</li>
            <li>Response times measured on one laptop ({r.performance.environment}) – not a production benchmark.</li>
          </ul>
        </Card>
      </div>
      <Card title="Where each scenario lands">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-muted text-left"><tr><th className="py-1.5">Scenario</th><th className="text-right">Claims</th><th className="text-right">Abusive share</th><th className="text-right">Fast-track</th><th className="text-right">Review</th><th className="text-right">Audit</th></tr></thead>
            <tbody>{Object.entries(r.by_scenario).sort((a: any, b: any) => a[1].abusive - b[1].abusive).map(([k, v]: any) => (
              <tr key={k} className="border-t border-line num"><td className="py-1.5">{SCEN[k] ?? k}</td><td className="text-right">{v.claims}</td><td className="text-right">{pct(v.abusive)}</td>
                <td className="text-right text-fast">{pct(v.fast_track)}</td><td className="text-right text-review">{pct(v.review)}</td><td className="text-right text-audit">{pct(v.audit)}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
