# Pilot proposal & cost inputs (draft for the economist to own)

Numbers marked **[assumption]** are placeholders to validate with RSL.

## Pilot design
- **User group:** one Special Sectors refund team (4–6 officers), wholesale & retail FMCG refund claimants.
- **Period:** 3 months in **shadow mode**. Officers keep working the current process, and TaxGuard scores every claim in parallel. In month 3, fast-track decisions on low-risk claims go live with officer sign-off.
- **Business owner:** Deputy Commissioner, Special Sectors.

## Baseline & success measures
| Measure | Baseline (collect in month 0) | Target |
|---|---|---|
| Refund turnaround (days, median) | current process **[assumption: ~45]** | fast-track lane ≤ 5 days |
| Share of audited claims with a confirmed issue (hit rate) | current selection | ≥ 2× current |
| Legitimate claims slowed (sent to review, no adjustment) | – | ≤ 10% |
| Revenue protected (adjustments on flagged claims) | – | report M value |
| Officer agreement with recommendation | – | tracked via override log |

## Data needed from RSL (masked)
VAT returns and refund claims (24 months) · invoice schedules supporting input VAT · VAT registry (registration dates, status) · supplier sales listings or e-invoice data · related-party disclosures · annual financial statements · customs export data (to confirm zero-rated sales).

## Integration
1. **Months 0–3:** batch CSV export → `python -m api.app.seed` (nightly). No change to RSL systems.
2. **After the pilot:** read-only API from the RSL VAT system, plus a write-back of the recommendation and the officer's decision.

## Policy / agreements to explore
Invoice submission or e-invoicing requirement (makes the supplier cross-match exact) · data-sharing for related-party disclosures · exchange-of-information requests for group data on low-tax jurisdictions · retention policy for invoice images (**[assumption: 5 years, aligned with record-keeping rules]**).

## Cost inputs
| Item | Estimate |
|---|---|
| Hosting: one 4 vCPU / 16 GB VM (cloud or on-prem) + Postgres | ~USD 100–150 / month **[assumption]** |
| Invoice reading, Claude Opus 5.5 (default) | ≈ USD 0.02 per invoice (≈1.9k input + ~0.5k output tokens at $4 / $20 per M). **Measure with `eval/ocr_eval.py`** |
| Invoice reading, Claude Haiku 5.5 (budget option) | ≈ USD 0.0005 per invoice (same token profile at $0.10 / $0.50 per M) – validate accuracy first |
| Example: 100,000 invoices / year | ≈ USD 2,000 (Opus 5.5) or ≈ USD 50 (Haiku 5.5) |
| Offline fallback (Tesseract) | free; lower accuracy |
| Maintenance / development | **[assumption: 0.5 FTE developer during pilot]** |
| Training | half a day per officer; built-in reason codes reduce training need |

Context: the brief cites ~**M1bn** annual tax forgone (preliminary estimate). Recovering even 1% of that (M10m) is far more than the running cost.
