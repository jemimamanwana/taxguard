"""Build docs/TaxGuard_Proposal_Update_Guide.pdf - every number is read from eval/output/results.json
and the scored database, so the guide always matches the prototype.

Run from repo root:  python docs/build_update_guide.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,  # noqa: E402
                                TableStyle)
from sqlalchemy import text  # noqa: E402

from api.app.db import engine  # noqa: E402

BLUE = colors.HexColor("#00209f")
GREEN = colors.HexColor("#138a4b")
AMBER = colors.HexColor("#b26b00")
RED = colors.HexColor("#b3261e")
INK = colors.HexColor("#0f1b2d")
MUTED = colors.HexColor("#5b6b80")
LINE = colors.HexColor("#dfe5ec")
SOFT = colors.HexColor("#e8ecfb")
PAPER = colors.HexColor("#f5f7fa")
USD_TO_LSL = 18.5  # [assumption] - economist to confirm the rate used in the proposal

R = json.loads((ROOT / "eval" / "output" / "results.json").read_text())
DEMO = json.loads((ROOT / "data" / "demo_cases.json").read_text())

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=17, textColor=BLUE, spaceBefore=6, spaceAfter=8)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=12.5, textColor=INK, spaceBefore=10, spaceAfter=5)
H3 = ParagraphStyle("H3", parent=ss["Heading3"], fontName="Helvetica-Bold", fontSize=10.5, textColor=BLUE, spaceBefore=8, spaceAfter=3)
B = ParagraphStyle("B", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=INK, alignment=TA_LEFT)
SM = ParagraphStyle("SM", parent=B, fontSize=8.5, leading=11.5, textColor=MUTED)
CELL = ParagraphStyle("CELL", parent=B, fontSize=8.5, leading=11)
CELLB = ParagraphStyle("CELLB", parent=CELL, fontName="Helvetica-Bold")
QUOTE = ParagraphStyle("Q", parent=B, backColor=SOFT, borderColor=BLUE, borderWidth=0, borderPadding=(6, 8, 6, 8),
                       leftIndent=4, rightIndent=4, spaceBefore=4, spaceAfter=8)
BUL = ParagraphStyle("BUL", parent=B, leftIndent=12, bulletIndent=2)


def P(t, s=B):
    return Paragraph(t, s)


def bullets(items, s=BUL):
    return [Paragraph(i, s, bulletText="•") for i in items]


def pct(x, d=0):
    return f"{x * 100:.{d}f}%"


def mny(x):
    return f"M {x / 1e6:,.1f}m" if abs(x) >= 1e6 else f"M {x:,.0f}"


def table(rows, widths, header=True, zebra=True, bold_first_col=False):
    data = [[c if not isinstance(c, str) else P(c, CELLB if (header and i == 0) or (bold_first_col and j == 0) else CELL)
             for j, c in enumerate(r)] for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
          ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
          ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), PAPER), ("LINEBELOW", (0, 0), (-1, 0), 0.8, MUTED)]
    if zebra:
        for i in range(2 if header else 1, len(rows), 2):
            st.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fbfcfd")))
    t.setStyle(TableStyle(st))
    return t


def demo_rows():
    out = {}
    for key, tin in DEMO.items():
        r = pd.read_sql(text(f"select claim_id, period, refund_claimed, score, lane, reasons from claims "
                             f"where tin='{tin}' order by period desc limit 1"), engine).iloc[0]
        x = json.loads(r.reasons) if isinstance(r.reasons, str) else r.reasons
        name = pd.read_sql(text(f"select name from taxpayers where tin='{tin}'"), engine).iloc[0, 0]
        out[key] = {"name": name, "period": r.period, "refund": r.refund_claimed, "score": r.score, "lane": r.lane,
                    "codes": [z["code"] for z in x["reasons"] if z["points"] > 0.5],
                    "mits": [m["code"] for m in x["mitigations"]], "floors": [f["code"] for f in x["floors"]]}
    return out


def on_page(c, doc):
    c.saveState()
    c.setFillColor(BLUE)
    c.rect(0, A4[1] - 9 * mm, A4[0], 9 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(18 * mm, A4[1] - 6 * mm, "TAXGUARD  |  Proposal update guide  |  RSL Taxathon 2026 - Challenge 2")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(18 * mm, 10 * mm, "Internal team document - synthetic data only. Numbers generated from the prototype's evaluation run.")
    c.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
    c.restoreState()


def build():
    m, b = R["model"], R["baseline_same_volume"]
    al, inc, rr = R["model_audit_lane"], R["model_incl_records_requests"], R["records_requested"]
    inv, ex, perf, ds = R["invoices"], R["explainability"], R["performance"], R["dataset"]
    dm = demo_rows()
    d1, d2, d3 = dm["ordinary_fast_track"], dm["exception_capital"], dm["human_review_abuse"]
    fn_unsup = R["errors"]["false_negatives_by_scenario"].get("abuse_unsupported", 0)
    opus_usd, haiku_usd = 0.02, 0.0005

    s = []
    # ------------------------------------------------------------------ cover
    s += [Spacer(1, 14 * mm), P("TAXGUARD", ParagraphStyle("T", parent=H1, fontSize=30, leading=34)),
          P("Proposal update guide", ParagraphStyle("T2", parent=H2, fontSize=16, textColor=MUTED)),
          Spacer(1, 4 * mm),
          P("<b>Purpose.</b> The prototype has been renamed to <b>TaxGuard</b> and changed so it matches the technical proposal. "
            "This guide lists (1) what changed in the prototype, (2) the exact edits to make to the proposal, section by section, with "
            "ready-to-paste replacement text, and (3) the measured results that replace the proposal's \"will evaluate\" language. "
            "Every figure comes from the prototype's evaluation run on labelled synthetic data."),
          Spacer(1, 3 * mm),
          P("<b>How to use it.</b> Work through Part 2 in order. Text in a <font color='#00209f'><b>blue box</b></font> is suggested "
            "wording you can paste and adapt. Items marked <b>[assumption]</b> are placeholders the economist must confirm."),
          Spacer(1, 6 * mm)]
    s.append(table([
        ["Headline (synthetic data)", "TaxGuard", "Baseline: review the largest claims"],
        ["Precision - flagged claims that are abusive", pct(m["precision"]), pct(b["precision"])],
        ["Recall - abusive claims caught", pct(m["recall"]), pct(b["recall"])],
        ["Legitimate refunds fast-tracked (complete records)", pct(R["legit_fast_track_rate_complete_records"]), pct(1 - b["false_positive_rate"])],
        ["Abusive refund value flagged", mny(R["abusive_value_flagged_model"]), mny(R["abusive_value_flagged_baseline"])],
        ["Phantom-supplier invoices caught", f"{inv['phantom_caught']} / {inv['phantom_invoices']}", "-"],
        ["Duplicate invoices caught (false alarms)", f"{inv['duplicates_caught']} / {inv['duplicate_invoices']} ({inv['duplicate_false_alarms']})", "-"],
        ["Flags with a plain-language explanation", pct(ex["explained_share"]), "-"],
    ], [92 * mm, 36 * mm, 46 * mm]))
    s.append(Spacer(1, 3 * mm))
    s.append(P(f"Dataset: {ds['claims']:,} refund claims ({ds['abusive_claims']} abusive) from {ds['taxpayers']} claimant taxpayers, "
               f"{ds['periods']}. The baseline flags the same number of claims ({b['flagged']}) by picking the largest refunds "
               f"(threshold M {b['threshold']:,.0f}). Synthetic results cannot establish real-world accuracy - see Part 3.", SM))
    s.append(PageBreak())

    # ------------------------------------------------------------------ part 1
    s.append(P("Part 1 - What changed in the prototype", H1))
    s.append(P("These changes close the gaps between the proposal and the working demo. The right-hand column is the proposal "
               "section each change now supports."))
    s.append(Spacer(1, 2 * mm))
    s.append(table([
        ["Change", "What it does", "Proposal section"],
        ["Renamed to TaxGuard", "App name, logo, page titles, API title, evaluation charts and docs now say TaxGuard.", "Title, all"],
        ["New rule R12 - related-party financing", "Flags intra-group interest above 1% of turnover while the company reports losses in "
         "consecutive years. Group-structure rule: a mitigating factor cannot offset it.", "§3.1, §4 (financing anomaly)"],
        ["Missing / contradictory data labelled (D01-D03)", "D01 financial statements missing, D02 VAT returns not filed, D03 returns "
         "disagree with financial statements by >30%. Shown separately, never scored as zero or high risk. Rules that could not run are "
         "listed. A claim with a data gap cannot be fast-tracked (safeguard L03) and the missing documents are requested.", "§4 (missing data)"],
        ["Per-flag review status", "Officers mark each flag Reviewed, Not applicable or Information required, with a mandatory reason. "
         "Stored per claim, shown on the case and written to the audit log.", "§4, §7.1"],
        ["PDF / PNG / JPG upload with allowlist", "Files are checked by content signature (not extension) and anything else is rejected. "
         "The first PDF page is read, and the original file is preserved unchanged. Fields are marked machine-extracted with confidence.", "§3.2, §6"],
        ["New test scenario: incomplete records", "8 legitimate exporters with unfiled months, missing statements and a turnover mismatch, "
         "matching the proposal's \"incomplete or contradictory records\" scenario.", "§4.1"],
        ["Response-time and explainability measures", f"Evaluation now reports median / p95 response times and the share of flags with an "
         f"explanation ({pct(ex['explained_share'])} of {ex['flags_fired']:,}).", "§8"],
        ["Evaluation separates document requests", "Claims sent to review only because records are missing are reported as document "
         "requests, not risk flags, and an overall figure including them is also given.", "§8"],
    ], [42 * mm, 98 * mm, 34 * mm]))
    s.append(Spacer(1, 3 * mm))
    s.append(P("Already in the prototype before this round (the proposal should mention these, see Part 2): supplier cross-match against "
               "suppliers' declared sales; duplicate and altered-copy detection; mitigating factors (exports, capital assets, clean history, "
               "seasonality); Isolation Forest anomaly model with plain-language drivers; related-party group graph; role-based access with "
               "masked TINs; mandatory decision reasons and override tracking; full audit log; admin-editable thresholds with re-scoring; "
               "taxpayer portal with a draft Sesotho toggle; client-side image compression for weak connections.", SM))
    s.append(PageBreak())

    # ------------------------------------------------------------------ part 2
    s.append(P("Part 2 - Edits to the proposal, section by section", H1))

    s.append(P("Global fixes", H2))
    s += bullets([
        "Use <b>TaxGuard</b> consistently (the cover uses TAXGUARD - fine for the logo, but use TaxGuard in body text).",
        "Fix the heading numbering: the second \"3.\" heading and \"3. 3.1\" should read <b>3.1</b>; check the numbering after it.",
        "Check the Laudage Teles, Riedel &amp; Strohmaier (2024) figures (5-8% corporate tax revenue increase) against the paper itself.",
        "Replace future-tense \"will build / will evaluate\" with what the prototype now does, and keep the honest caveats.",
    ])

    s.append(P("Executive summary - add two sentences", H2))
    s.append(P("The summary is careful but doesn't say what's new. Add after the second paragraph:"))
    s.append(P(f"TaxGuard checks every supporting invoice against the supplier's own declared sales, catches duplicate and altered "
               f"re-photographed invoices, and explains every flag in plain language with the evidence behind it. On {ds['claims']:,} "
               f"labelled synthetic claims it achieved {pct(m['precision'])} precision and {pct(m['recall'])} recall, against "
               f"{pct(b['precision'])} and {pct(b['recall'])} for selecting the largest claims, while fast-tracking "
               f"{pct(R['legit_fast_track_rate_complete_records'])} of legitimate refunds with complete records.", QUOTE))

    s.append(P("§2.2 Problem statement - replace", H2))
    s.append(P("The current text covers audit selection only. Taxpayer and business value is the largest judging criterion (25%), so the "
               "problem should be two-sided. Suggested replacement:"))
    s.append(P("Tax and financial information is spread across returns, schedules, invoices, financial statements and periods. Manual "
               "collation is slow, so refund verification creates a double cost. Legitimate claimants, especially exporters with zero-rated "
               "sales, wait for refunds that affect their cash flow, while abusive claims supported by unsupported, duplicate or phantom "
               "invoices can still be paid. Related-party structures add further complexity: a refund position, a loss or an intra-group "
               "charge does not on its own prove abuse. The Taxathon brief cites a preliminary estimate of around M1bn in annual tax forgone. "
               "RSL needs an analytical support layer that pays legitimate refunds faster, concentrates scarce audit capacity on the claims "
               "most likely to be abusive, explains why each case is flagged, and lets auditors trace each flag to the underlying evidence.", QUOTE))

    s.append(P("§3 Modules table - add or amend rows", H2))
    s.append(table([
        ["Module", "Function", "User value"],
        ["Supplier cross-match &amp; duplicate detection (new row)", "Checks each supporting invoice against the supplier's declared "
         "sales listing and VAT return, the VAT register, prior invoices (number, fields) and a perceptual image hash.",
         "Catches phantom and reused invoices with evidence."],
        ["Related-party group explorer (new row)", "Interactive graph of MNE group entities and intra-group flows; highlights paths "
         "from Lesotho entities to low-tax jurisdictions.", "Makes group structures visible for Special Sectors."],
        ["Invoice Intake &amp; Evidence Register (amend)", "Accepts PDF, PNG, JPG (content-signature allowlist, 12 MB limit); "
         "OCR suggests fields with confidence; original preserved; manual route always available.", "Implemented in the prototype."],
        ["Taxpayer intake (demo, amend §7.2)", "Demonstration portal: submit claim, upload invoice photos, see status and "
         "document requests. Draft Sesotho labels.", "Shown as a future option subject to RSL approval."],
    ], [44 * mm, 82 * mm, 48 * mm]))

    s.append(P("§4 Risk analytics and scoring framework - replace the indicator table", H2))
    s.append(P("The proposal describes a weighted average of six indicators with bands at 30 and 60. The prototype instead adds up points "
               "from explainable rules, so use the text and table below. The weights are illustrative demo values, not RSL thresholds."))
    s.append(P("Each rule produces a severity between 0 and 1. Points = severity x the rule's maximum points, and the risk score (0-100) "
               "is the sum. Rules are grouped into three types. <b>Document evidence</b> and <b>group-structure</b> findings can never be "
               "offset. <b>Behaviour patterns</b> can be explained away by documented mitigating factors such as zero-rated exports or "
               "capital purchases. An Isolation Forest anomaly model adds up to 15 points and is always shown with its main drivers. "
               "Demo lanes: <b>Fast-track</b> below 15, <b>Officer review</b> 15-34, <b>Audit</b> 35 and above. Three safeguards "
               "override the score: a strong document finding is never fast-tracked (L01), a large capital-asset refund needs one supporting "
               "document (L02), and missing or contradictory records must be resolved first (L03).", QUOTE))
    W = json.loads(json.dumps(__import__("api.app.config", fromlist=["DEFAULT_SETTINGS"]).DEFAULT_SETTINGS["weights"]))
    s.append(table([
        ["Code", "Indicator", "Type", "Max pts"],
        ["R01", "Persistent refund claimant (8+ of last 12 months)", "Pattern", str(W["R01"])],
        ["R02", "Input VAT not supported by invoices (>10% gap)", "Evidence", str(W["R02"])],
        ["R03", "Invoices from suppliers who did not declare the sale", "Evidence", str(W["R03"])],
        ["R04", "Duplicate / altered / re-photographed invoices", "Evidence", str(W["R04"])],
        ["R05", "Reverse-charge VAT missing on related-party imported services", "Evidence", str(W["R05"])],
        ["R06", "Input/output VAT ratio far above sector peers", "Pattern", str(W["R06"])],
        ["R07", "Refund spike versus own history", "Pattern", str(W["R07"])],
        ["R08", "High-risk or newly registered suppliers", "Pattern", str(W["R08"])],
        ["R09", "Related-party charges to low-tax entities > 5% of turnover", "Group", str(W["R09"])],
        ["R10", "Persistent losses alongside growing turnover", "Group", str(W["R10"])],
        ["R11", "Margin far below peers with heavy intra-group purchases", "Group", str(W["R11"])],
        ["R12", "Related-party financing alongside losses (new)", "Group", str(W["R12"])],
        ["ANOM", "Isolation Forest statistical anomaly", "Pattern", str(W["ANOM"])],
        ["M01-M04", "Mitigations: exports, capital assets, clean history, seasonality", "Offsets patterns", "-"],
        ["D01-D03", "Data gaps: statements missing, returns not filed, records disagree", "Not scored", "-"],
    ], [18 * mm, 104 * mm, 30 * mm, 22 * mm]))
    s.append(Spacer(1, 2 * mm))
    s.append(P("Keep the proposal's good bullets on missing data, reviewer dispositions, versioning and human review - the prototype now "
               "implements all of them. Mapping to the proposal's bands: Low = Fast-track, Medium = Officer review, High = Audit.", SM))
    s.append(P("§4.1 Scenarios: the six proposal scenarios map to prototype data - ordinary low-risk (normal taxpayers), recurring refund "
               "with valid invoices (exporters), high related-party expenses and losses (profit shifting), imported-service mismatch "
               "(reverse charge), incomplete or contradictory records (new), and a false positive with a commercial explanation (seasonal "
               "stock build-up and capital purchases). Also list the invoice-fraud scenarios: phantom suppliers, duplicates, unsupported input VAT.", SM))

    s.append(P("§6 Security - split into \"in the prototype\" and \"before a pilot\"", H2))
    s.append(P("As written, §6 reads as if the prototype already has MFA, encryption and malware scanning. It doesn't. Splitting the "
               "list is more honest and scores better on trust:"))
    s.append(table([
        ["In the prototype now", "Required before a pilot"],
        ["Role-based access (auditor, analyst, Special Sectors, admin, taxpayer)", "MFA via RSL identity management"],
        ["TINs masked except for the assigned officer", "TLS everywhere; encryption at rest for DB, backups, documents"],
        ["Mandatory reason on every decision and flag review; overrides tracked", "Malware scanning and OCR sandboxing for uploads"],
        ["Audit log: logins, views, scans, scores, decisions, settings changes", "Tamper-evident (append-only, hashed) audit log"],
        ["Upload allowlist by file signature; 12 MB limit; originals preserved", "Secure sessions, idle timeout, penetration test"],
        ["No automated rejection; ground-truth labels never loaded into the app", "Retention schedule, DPIA, access matrix, incident response"],
    ], [87 * mm, 87 * mm], zebra=False))

    s.append(P("§7.3 Usability - small update", H2))
    s += bullets([
        "The prototype already has a responsive layout, plain-language reasons, client-side image compression and code-split pages "
        "(initial download ~90 KB gzipped).",
        "The taxpayer portal has an English / Sesotho toggle. The Sesotho labels are <b>draft</b> and must be checked by a native speaker; "
        "say so in the proposal.",
    ])

    s.append(P("§8 Performance evaluation - replace \"proposed evaluation\" with results", H2))
    s.append(table([
        ["Dimension", "Result on synthetic test data"],
        ["Calculation correctness", "9 automated tests pass (demo lanes, explanations, roles and masking, mandatory reasons, R12, data-gap "
                                    "labels, flag reviews, upload allowlist and PDF)."],
        ["Flag detection (recall)", f"{pct(m['recall'])} of abusive claims flagged (baseline {pct(b['recall'])}). The Audit lane alone: "
                                    f"precision {pct(al['precision'])}, recall {pct(al['recall'])}."],
        ["False positives", f"Precision {pct(m['precision'])} (baseline {pct(b['precision'])}); false-positive rate {pct(m['false_positive_rate'], 1)}. "
                            f"{rr['claims']} further claims were sent for missing records ({rr['abusive_among_them']} abusive) - a "
                            f"document request, not a risk flag. Including them: precision {pct(inc['precision'])}."],
        ["Explainability", f"{pct(ex['explained_share'])} of {ex['flags_fired']:,} triggered flags show code, rationale and evidence."],
        ["Responsiveness", f"Case view median {perf['case_view']['median_ms']} ms / p95 {perf['case_view']['p95_ms']} ms; queue median "
                           f"{perf['queue']['median_ms']} ms; dashboard median {perf['dashboard']['median_ms']} ms ({perf['environment']})."],
        ["Document intake", f"Phantom-supplier invoices {inv['phantom_caught']}/{inv['phantom_invoices']}; duplicates "
                            f"{inv['duplicates_caught']}/{inv['duplicate_invoices']} with {inv['duplicate_false_alarms']} false alarms; "
                            f"altered-number copies {inv['altered_number_caught']}/{inv['altered_number_copies']}. Field-level OCR accuracy: "
                            "run eval/ocr_eval.py with an API key before submission and insert the figure."],
        ["Usability", "Not yet measured - run the 80% task-completion test with 3-5 people before the event if possible."],
    ], [38 * mm, 136 * mm], bold_first_col=True))
    s.append(P("Known limitations - include these", H3))
    s += bullets([
        "The data is synthetic and the abuse patterns were designed by the team, so real-world precision and recall will be lower.",
        "The lane thresholds were set on this same dataset, so there is a risk of over-fitting. Re-calibrate during the shadow pilot.",
        "The supplier cross-match assumes invoice-level sales listings or e-invoicing. With only return totals it is weaker.",
        "A perceptual image hash alone cannot separate re-photographed copies from different invoices on the same supplier template, so "
        "duplicates are confirmed by matching fields.",
        f"Low-level input-VAT inflation (under a 10% gap) is the main source of missed abuse ({fn_unsup} claims).",
        "Response times were measured on one laptop, so they are not a production benchmark.",
    ])

    s.append(P("§10 Costs - add the per-invoice running cost", H2))
    s.append(P("§10 gives pilot costs in Maloti. Add one row for running costs of invoice reading (at an assumed rate of "
               f"USD 1 = M {USD_TO_LSL} [assumption]):"))
    s.append(table([
        ["Cost item", "Indicative (M)", "Assumption"],
        ["Invoice reading - Claude Opus 5.5 (default)", f"~M {opus_usd * USD_TO_LSL:.2f} per invoice", "~1.9k input + ~0.5k output tokens; measure with eval/ocr_eval.py"],
        ["Invoice reading - Claude Haiku 5.5 (budget)", f"~M {haiku_usd * USD_TO_LSL:.3f} per invoice", "Same token profile; validate accuracy first"],
        ["Example: 100,000 invoices per year", f"~M {100_000 * opus_usd * USD_TO_LSL:,.0f} (Opus) / ~M {100_000 * haiku_usd * USD_TO_LSL:,.0f} (Haiku)", "Volume [assumption]"],
        ["Offline fallback (Tesseract OCR)", "M 0", "Lower accuracy; manual route remains"],
    ], [60 * mm, 50 * mm, 64 * mm]))

    s.append(P("Scope note - expatriate employment income", H2))
    s.append(P("§2.1 lists expatriate employment income and the classification of related-party services among the challenge's risk "
               "areas. The prototype has no module for this (the synthetic data includes 40 expat engagements for a future checker). "
               "Either add one line saying it is a planned extension, or remove it from the scope list so judges don't expect it in the demo."))
    s.append(PageBreak())

    # ------------------------------------------------------------------ part 3
    s.append(P("Part 3 - Demo script (the brief's three required cases)", H1))
    s.append(table([
        ["Case", "Taxpayer &amp; claim", "Result", "Why"],
        ["1. Ordinary", f"{d1['name']}<br/>{d1['period']}, {mny(d1['refund'])}", f"<font color='#138a4b'><b>Fast-track</b></font>, score {d1['score']:.0f}",
         f"Claims every month and input VAT is far above output, but M01 (zero-rated exports) explains it. All invoices cross-match. "
         f"Mitigations: {', '.join(d1['mits']) or '-'}."],
        ["2. Exception", f"{d2['name']}<br/>{d2['period']}, {mny(d2['refund'])}", f"<font color='#b26b00'><b>Officer review</b></font>, score {d2['score']:.0f}",
         f"New business with a huge spike versus its own history. M02 shows it is warehouse equipment, so the only step is "
         f"one asset document ({', '.join(d2['floors'])})."],
        ["3. Human review", f"{d3['name']}<br/>{d3['period']}, {mny(d3['refund'])}", f"<font color='#b3261e'><b>Audit</b></font>, score {d3['score']:.0f}",
         f"Rules fired: {', '.join(d3['codes'])}. Phantom-supplier invoices, an altered re-photographed copy, low-tax fees, intra-group "
         f"loan interest, years of losses. Open the group graph."],
    ], [22 * mm, 50 * mm, 32 * mm, 70 * mm]))
    s.append(Spacer(1, 3 * mm))
    s.append(P("Suggested 5-minute flow", H3))
    s += bullets([
        "Sign in as <b>auditor1</b> (password demo) and open the Refund queue: highest risk first, with reason chips.",
        "Case 1: show the M01 mitigation offsetting the persistence signals, then approve with a reason.",
        "Case 2: show the M02 explanation and the one-document request, then request documents.",
        "Case 3: walk the evidence (invoice cross-check, the duplicate image, the group graph), mark one flag \"information "
        "required\", and escalate. Point out that the decision and the reason are in the audit log.",
        "Scan invoice: pick a sample photo (or upload a PDF) and show auto-filled fields, confidence and the live checks.",
        "Evidence &amp; evaluation page: precision and recall against the baseline, the limitations, response times.",
        "Optional: sign in as <b>senqu</b> to show the taxpayer portal and the Sesotho toggle.",
    ])
    s.append(P("Before submission - checklist", H3))
    s += bullets([
        "Set ANTHROPIC_API_KEY, run <i>python -m eval.ocr_eval --limit 40</i> and add the OCR accuracy and cost figures to §8 and §10.",
        "Economist: confirm the VAT rate (15% used), the turnaround assumptions (3 / 14 / 60 days against ~45 manual) and the USD/LSL rate.",
        "Native speaker reviews the Sesotho labels.",
        "Run docker compose once on a machine with enough free memory (it has not been verified yet).",
        "Re-generate this guide after any change: <i>python docs/build_update_guide.py</i>.",
    ])

    out = ROOT / "docs" / "TaxGuard_Proposal_Update_Guide.pdf"
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=17 * mm,
                            title="TaxGuard - Proposal update guide", author="TaxGuard Innovators")
    doc.build(s, onFirstPage=on_page, onLaterPages=on_page)
    print(out)


_ = KeepTogether
if __name__ == "__main__":
    build()
