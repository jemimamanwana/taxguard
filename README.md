# TaxGuard

**VAT refund triage & investigation for Revenue Services Lesotho** · RSL Taxathon 2026 · Challenge #2 (multinational tax evasion & refund abuse)

> Prototype. **Synthetic data only.** No real taxpayer data, and no connection to any RSL system. All names are fictional.
> The system **recommends**. An officer always makes the decision.

Every VAT refund claim is scored into **Fast-track**, **Officer review** or **Audit**. Every flag comes with a reason code, a plain-language explanation and the evidence behind it. Invoices are read from photos and cross-matched with what suppliers actually declared. A related-party graph shows multinational structures and suspicious intra-group charges.

## Run it

### Option A – Docker (one command)
```bash
docker compose up --build          # http://localhost:8000
```
On first start this generates the dataset, loads it into Postgres, scores every claim and runs the evaluation. To use the Claude vision invoice reader, set `ANTHROPIC_API_KEY` in your shell first.

### Option B – local (SQLite, works offline)
```bash
python -m venv .venv && .venv/Scripts/activate      # (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
python -m data_gen.generate       # synthetic dataset + invoice images -> ./data
python -m api.app.seed            # load CSVs, validate invoices, score claims
python -m eval.run_eval           # metrics + charts -> ./eval/output
cd web && npm install && npm run build && cd ..
uvicorn api.app.main:app --port 8000                 # http://localhost:8000
```
For frontend development, run `npm run dev` in `web/` (http://localhost:5173, proxies `/api`).

**Demo accounts** (password `demo`): `auditor1` refund auditor · `analyst1` risk analyst · `special1` Special Sectors · `admin1` admin · taxpayer portal: `maluti`, `senqu`, `thababosiu`.

## Demo script (the three cases the brief requires)

| # | Case | Taxpayer | What happens |
|---|---|---|---|
| 1 | **Ordinary → Fast-track** | Maluti Highlands Knitwear Exporters | Refunds 12/12 months and input VAT 6× output, but **M01** (88% zero-rated exports) explains it. All invoices cross-match → score 0, recommend approval. |
| 2 | **Exception → one document** | Senqu Valley FMCG Distributors | New business, M1.35m refund, 88-σ spike vs. its own history. **M02** shows it is warehouse equipment (cold room, forklift, racking). Routed to Officer review only to request **one** asset invoice / delivery proof. |
| 3 | **Human review → Audit** | Thaba-Bosiu Retail Holdings | Score 100: refunds 11 of 12 months (R01), phantom-supplier invoices whose supplier declared ~M0 output VAT (R03), an **altered re-photographed copy** of an earlier invoice (R04), 17.7% of turnover in fees to a low-tax sister (R09), 6 loss years with growing turnover (R10), low margin with intra-group purchases (R11). Evidence pack + group graph. |

Suggested flow: sign in as `auditor1` → Queue → open each case → *Group explorer* for case 3 → *Scan invoice* (pick a sample photo) → *Evidence & evaluation*. Then sign in as `senqu` to show the taxpayer portal (English / Sesotho).

## How scoring works (`api/app/scoring/`)

Hybrid rules + anomaly model. Each rule returns a severity (0–1) × weight = points. Points add up to a 0–100 score.

| Bucket | Codes | Can a mitigation offset it? |
|---|---|---|
| Document evidence | R02 unsupported input VAT · R03 supplier did not declare · R04 duplicate · R05 reverse charge missing | **Never** |
| Group structure | R09 low-tax RP charges · R10 persistent losses + growth · R11 low margin + intra-group purchases · R12 related-party financing + losses | **Never** |
| Data gaps (not scored) | D01 financial statements missing · D02 returns not filed · D03 returns disagree with financial statements | Shown explicitly, never treated as zero or high risk |
| Behaviour pattern | R01 persistent claimant · R06 ratio vs peers · R07 spike · R08 risky suppliers · ANOM Isolation Forest | Yes: M01 exports, M02 capital, M03 clean history, M04 seasonal |

Lanes: score < 15 Fast-track, 15–35 Officer review, ≥ 35 Audit (admin-configurable). Two safeguards override the score: a strong document finding can never be fast-tracked (L01), and a large capital-asset refund gets a one-document check (L02), and missing or contradictory records must be resolved first (L03). Officers can mark each flag reviewed / not applicable / information required, with a reason. Changing a threshold re-scores everything and is written to the audit log.

## Evidence (`eval/`)

`python -m eval.run_eval` compares the model with an amount-based baseline that flags the **same number** of claims (the largest ones). On the seeded data:

| | TaxGuard | "Flag the biggest claims" |
|---|---|---|
| Precision | **0.93** | 0.38 |
| Recall | **0.94** | 0.39 |
| Legit refunds fast-tracked (complete records) | **96%** | 66% |
| Phantom-supplier invoices caught | 571/571 | – |
| Flags with a plain-language explanation | 100% | – |
| Duplicate invoices caught (incl. 22 altered copies) | 295/295, 0 false alarms | – |

A further 176 claims (none abusive) are sent to review only to request missing records. They are reported as document requests, not risk flags; counting them, precision is 0.78.

`python -m eval.ocr_eval --limit 40` measures field-level extraction accuracy and cost per invoice (needs an API key).
**Limitations** (also shown in the app): the data is synthetic and its abuse patterns are ones we designed, the thresholds were tuned on the same data, the supplier cross-match assumes invoice-level sales listings, and a perceptual image hash alone cannot tell re-photographed copies from different invoices on the same supplier template.

## Trust & compliance
Role-based access · TINs masked except for the assigned officer · a mandatory reason on every decision · overrides of the recommendation recorded · every view, scan, score, decision and settings change in the audit log · no automated rejections · ground-truth labels are never loaded into the app.

## Repo
```
data_gen/   synthetic dataset + Pillow invoice-image renderer (seeded, reproducible)
api/app/    FastAPI: models, scoring/, ocr/ (Claude vision + Tesseract fallback + validation), graph/, routers/
web/        React + Vite + TS + Tailwind: Queue, CaseView, Graph, Dashboard, ScanInvoice, Evaluation, Admin, Portal
eval/       evaluation harness + OCR accuracy script
docs/       pilot proposal & cost inputs; TaxGuard_Proposal_Update_Guide.pdf (python docs/build_update_guide.py)
```
Pilot integration path: RSL exports CSVs in the same shape as `data/*.csv` → `python -m api.app.seed`.
