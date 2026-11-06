"""Hybrid scoring engine: rules + anomaly model -> score, lane, reasons, recommended action.

The engine RECOMMENDS. A human officer always makes the final decision.
"""
from __future__ import annotations

import pandas as pd

from .anomaly import fit_anomaly
from .features import build_features
from .rules import Reason, _f, _m, data_gaps, mitigations, risk_rules

LANES = ("fast_track", "review", "audit")
LANE_LABEL = {"fast_track": "Fast-track", "review": "Officer review", "audit": "Audit"}


def _anomaly_reason(a, w) -> Reason | None:
    pct = float(a["anomaly_pct"])
    sev = max(0.0, min(1.0, (pct - 0.90) / 0.10))
    if sev <= 0:
        return None
    feats = a["top_features"]
    if feats:
        bits = [f"{t['label'].lower()} is {t['direction']} than typical ({t['value']:g} vs {t['typical']:g})" for t in feats]
        detail = "Unusual compared with all claims: " + "; ".join(bits) + "."
    else:
        detail = "Unusual combination of claim characteristics compared with all other claims."
    return Reason("ANOM", "Statistical anomaly (Isolation Forest)", detail, sev, "pattern",
                  evidence={"percentile": round(pct, 3), "top_features": feats})


def score_one(f, a, settings: dict) -> dict:
    W = settings["weights"]
    reasons = risk_rules(f, settings)
    an = _anomaly_reason(a, W["ANOM"])
    if an:
        reasons.append(an)
    for r in reasons:
        r.points = W.get(r.code, 10) * r.severity
    evidence_fired = any(r.bucket == "evidence" and r.severity >= 0.2 for r in reasons)

    mit_out: list[Reason] = []
    for m, frac, targets in mitigations(f, evidence_fired):
        removed = 0.0
        for r in reasons:
            if r.code in targets and r.points > 0:
                cut = r.points * frac
                r.points -= cut
                removed += cut
        if removed > 0 or m.code in ("M01", "M02"):
            m.points = -removed
            mit_out.append(m)

    score = max(0.0, min(100.0, sum(r.points for r in reasons)))
    lane = "fast_track"
    if score >= settings["lane_audit_threshold"]:
        lane = "audit"
    elif score >= settings["lane_review_threshold"]:
        lane = "review"

    floors: list[Reason] = []
    if lane == "fast_track" and any(r.bucket == "evidence" and r.severity >= 0.5 for r in reasons):
        lane = "review"
        floors.append(Reason("L01", "Document finding needs an officer",
                             "A document-level finding cannot be fast-tracked, whatever the total score.",
                             1.0, "floor"))
    cap_vat = _f(f.capital_vat)
    if any(m.code == "M02" for m in mit_out) and cap_vat >= settings["capital_verify_vat"] and lane == "fast_track":
        lane = "review"
        floors.append(Reason("L02", "Verify capital asset (one document)",
                             f"Capital-asset VAT of {_m(cap_vat)} explains the refund. Confirm the asset exists with "
                             f"one supporting document before payment.", 1.0, "floor"))

    gaps = data_gaps(f)
    if gaps and lane == "fast_track":
        lane = "review"
        floors.append(Reason("L03", "Records incomplete",
                             "Missing or contradictory records must be resolved before a fast-track payment.", 1.0, "floor"))

    actions, docs = recommend(lane, reasons, mit_out, floors, f)
    for g in gaps:
        docs.append({"D01": "Latest audited financial statements",
                     "D02": "Outstanding VAT returns for: " + ", ".join(g.evidence.get("missing_periods", [])),
                     "D03": "Reconciliation of VAT-return sales to financial-statement turnover"}[g.code])
    risk = sorted([r for r in reasons if r.points > 0.05 or r.code.startswith("R")], key=lambda r: -r.points)
    return {
        "score": round(score, 1),
        "lane": lane,
        "lane_label": LANE_LABEL[lane],
        "reasons": [r.to_dict() for r in risk],
        "mitigations": [m.to_dict() for m in mit_out],
        "floors": [x.to_dict() for x in floors],
        "data_gaps": [g.to_dict() for g in gaps],
        "anomaly": {"percentile": round(float(a["anomaly_pct"]), 3), "top_features": a["top_features"]},
        "recommended_actions": actions,
        "requested_documents": docs,
        "summary": summarise(lane, risk, mit_out, f),
    }


def recommend(lane, reasons, mits, floors, f):
    codes = {r.code for r in reasons if r.points > 0.5}
    actions, docs = [], []
    if lane == "fast_track":
        actions.append("Recommend approval - supporting invoices reconcile with supplier declarations.")
    if "R02" in codes:
        docs.append("Tax invoices supporting the unsupported input VAT amount")
        actions.append("Disallow input VAT without a valid tax invoice unless documents are provided.")
    if "R03" in codes:
        actions.append("Verify the flagged purchases directly with the supplier(s); consider a supplier visit.")
        docs.append("Proof of payment and delivery notes for invoices from the flagged supplier(s)")
    if "R04" in codes:
        actions.append("Disallow duplicate invoice(s) and record the reuse on the taxpayer's compliance history.")
    if "R05" in codes:
        docs.append("Reverse-charge VAT computation for imported services from related parties")
    if codes & {"R09", "R10", "R11", "R12"}:
        actions.append("Refer the group structure to Special Sectors for a transfer-pricing review.")
        docs.append("Transfer-pricing documentation / intra-group agreements")
    if any(x.code == "L02" for x in floors):
        docs.append("ONE document: capital asset purchase invoice with proof of delivery / installation")
        actions.append("Approve once asset existence is confirmed - the refund is otherwise consistent.")
    if lane == "audit":
        actions.insert(0, "Escalate to Special Sectors audit with the evidence pack.")
    elif lane == "review" and not actions:
        actions.append("Officer to check the flagged items below before approval.")
    return actions, docs


def summarise(lane, risk, mits, f) -> str:
    top = [r for r in risk if r.points >= 1][:3]
    if lane == "fast_track":
        s = "Low risk. "
        if mits:
            s += "The refund is explained by: " + "; ".join(m.title.lower() for m in mits) + ". "
        return s + "Invoices reconcile with supplier declarations."
    s = ("High risk. " if lane == "audit" else "Medium risk. ")
    if top:
        s += "Main concerns: " + "; ".join(r.title.lower() for r in top) + ". "
    if mits:
        s += "Partly explained by: " + "; ".join(m.title.lower() for m in mits) + "."
    return s.strip()


def score_all(store, settings: dict) -> tuple[pd.DataFrame, dict[int, dict]]:
    C = build_features(store)
    A = fit_anomaly(C)
    results = {}
    for cid in C.index:
        results[int(cid)] = score_one(C.loc[cid], A.loc[cid], settings)
    return C, results
