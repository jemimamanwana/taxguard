export const M = (x: number | null | undefined, digits = 0) =>
  x == null || isNaN(x) ? '—' : `M ${Number(x).toLocaleString('en-ZA', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`

export const Mshort = (x: number | null | undefined) => {
  if (x == null) return '—'
  const a = Math.abs(x)
  if (a >= 1e9) return `M ${(x / 1e9).toFixed(1)}bn`
  if (a >= 1e6) return `M ${(x / 1e6).toFixed(1)}m`
  if (a >= 1e3) return `M ${(x / 1e3).toFixed(0)}k`
  return `M ${x.toFixed(0)}`
}

export const pct = (x: number | null | undefined, d = 0) => (x == null ? '—' : `${(x * 100).toFixed(d)}%`)

export const LANE_LABEL: Record<string, string> = { fast_track: 'Fast-track', review: 'Officer review', audit: 'Audit' }

export const ROLE_LABEL: Record<string, string> = {
  refund_auditor: 'Refund auditor', risk_analyst: 'Risk analyst', special_sectors: 'Special Sectors auditor',
  admin: 'Administrator', taxpayer: 'Taxpayer',
}

export const RULE_SHORT: Record<string, string> = {
  R01: 'Persistent claimant', R02: 'Unsupported input VAT', R03: 'Supplier did not declare', R04: 'Duplicate invoice',
  R05: 'Reverse charge missing', R06: 'Ratio vs peers', R07: 'Refund spike', R08: 'Risky suppliers',
  R09: 'Low-tax RP charges', R10: 'Persistent losses', R11: 'Low margin / intra-group', R12: 'RP financing + losses', ANOM: 'Anomaly',
  D01: 'Financials missing', D02: 'Returns not filed', D03: 'Records disagree',
  M01: 'Exports', M02: 'Capital assets', M03: 'Clean history', M04: 'Seasonal',
}
