"""Evaluation harness - TaxGuard vs an amount-based baseline on labelled synthetic data.

Run from repo root:   python -m eval.run_eval
Outputs:              eval/output/results.json, eval/output/*.png, eval/output/report.md

The baseline approximates manual / amount-based selection: "review every claim above M X".
For a fair comparison X is set so the baseline flags the SAME number of claims as the model.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

from api.app.config import DATA_DIR, EVAL_DIR
from api.app.db import engine

OUT = EVAL_DIR


def metrics(y: np.ndarray, p: np.ndarray) -> dict:
    tp = int(((y == 1) & (p == 1)).sum())
    fp = int(((y == 0) & (p == 1)).sum())
    fn = int(((y == 1) & (p == 0)).sum())
    tn = int(((y == 0) & (p == 0)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": round(prec, 3), "recall": round(rec, 3),
            "f1": round(f1, 3), "false_positive_rate": round(fpr, 3), "flagged": int(p.sum())}


def load() -> pd.DataFrame:
    c = pd.read_sql(text("select claim_id, tin, period, refund_claimed, score, lane, reasons from claims where source='batch'"), engine)
    rs = c["reasons"].map(lambda r: json.loads(r) if isinstance(r, str) else r)
    floors = rs.map(lambda d: {x["code"] for x in d.get("floors", [])})
    c["records_only"] = (c["lane"] == "review") & floors.map(lambda f: f == {"L03"})
    c = c.drop(columns=["reasons"])
    gt = pd.read_csv(DATA_DIR / "ground_truth.csv", dtype={"tin": str})
    df = c.merge(gt[["claim_id", "scenario", "abusive", "abuse_acts"]], on="claim_id", how="inner")
    return df


def invoice_eval() -> dict:
    inv = pd.read_sql(text("select invoice_id, checks, image_file from invoices"), engine)
    gt = pd.read_csv(DATA_DIR / "ground_truth_invoices.csv")
    inv = inv.merge(gt, on="invoice_id")
    fl = inv["checks"].map(lambda s: set(json.loads(s).get("flags", [])) if isinstance(s, str) else set())
    inv["nomatch"] = fl.map(lambda f: "NOMATCH" in f)
    inv["dup"] = fl.map(lambda f: "DUP" in f)
    ph = inv["truth"] == "phantom"
    du = inv["truth"] == "duplicate"
    return {
        "phantom_invoices": int(ph.sum()),
        "phantom_caught": int((ph & inv["nomatch"]).sum()),
        "phantom_recall": round(float((ph & inv["nomatch"]).sum() / max(ph.sum(), 1)), 3),
        "genuine_flagged_nomatch": int((~ph & inv["nomatch"]).sum()),
        "duplicate_invoices": int(du.sum()),
        "duplicates_caught": int((du & inv["dup"]).sum()),
        "duplicate_recall": round(float((du & inv["dup"]).sum() / max(du.sum(), 1)), 3),
        "duplicate_false_alarms": int((~du & inv["dup"]).sum()),
        "altered_number_copies": int(inv["altered_no"].sum()),
        "altered_number_caught": int((inv["altered_no"].astype(bool) & inv["dup"]).sum()),
    }


def performance(n: int = 25) -> dict:
    """Median / p95 API response time on this machine (not a production benchmark)."""
    import statistics
    import time

    from fastapi.testclient import TestClient

    from api.app.main import app

    c = TestClient(app)
    tok = c.post("/api/auth/login", json={"username": "auditor1", "password": "demo"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    cid = c.get("/api/claims?lane=audit", headers=h).json()["items"][0]["claim_id"]
    out = {}
    for name, url in [("queue", "/api/claims"), ("case_view", f"/api/claims/{cid}"), ("dashboard", "/api/dashboard/metrics")]:
        c.get(url, headers=h)  # warm-up
        ts = []
        for _ in range(n):
            t = time.perf_counter()
            c.get(url, headers=h)
            ts.append((time.perf_counter() - t) * 1000)
        ts.sort()
        out[name] = {"median_ms": round(statistics.median(ts)), "p95_ms": round(ts[int(0.95 * (len(ts) - 1))])}
    out["environment"] = "single local process, SQLite, developer laptop"
    return out


def explainability() -> dict:
    rows = pd.read_sql(text("select reasons from claims"), engine)["reasons"]
    fired = explained = gaps = 0
    for r in rows:
        d = json.loads(r) if isinstance(r, str) else r
        for x in d.get("reasons", []) + d.get("mitigations", []) + d.get("floors", []) + d.get("data_gaps", []):
            fired += 1
            explained += bool(x.get("detail")) and bool(x.get("code"))
        gaps += bool(d.get("data_gaps"))
    return {"flags_fired": fired, "flags_with_explanation": explained,
            "explained_share": round(explained / max(fired, 1), 4), "claims_with_data_gaps": gaps}


def charts(df, sweep, scen, res):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})

    # 1. model vs baseline
    fig, ax = plt.subplots(figsize=(7, 4))
    labels = ["Precision", "Recall", "F1", "False-positive rate\n(legit refunds slowed)"]
    m, b = res["model"], res["baseline_same_volume"]
    x = np.arange(len(labels))
    ax.bar(x - 0.2, [m["precision"], m["recall"], m["f1"], m["false_positive_rate"]], 0.4, label="TaxGuard", color="#1f5f8b")
    ax.bar(x + 0.2, [b["precision"], b["recall"], b["f1"], b["false_positive_rate"]], 0.4, label="Amount baseline", color="#c8a24a")
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 1)
    ax.legend(frameon=False)
    ax.set_title("Claim selection: model vs amount-based baseline (same review volume)")
    fig.tight_layout()
    fig.savefig(OUT / "model_vs_baseline.png", dpi=150)
    plt.close(fig)

    # 2. threshold sweep
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(sweep["threshold"], sweep["precision"], label="Precision", color="#1f5f8b")
    ax.plot(sweep["threshold"], sweep["recall"], label="Recall", color="#b5452f")
    ax.plot(sweep["threshold"], sweep["legit_fast_track_rate"], label="Legit refunds fast-tracked", color="#3c8d4f")
    ax.set_xlabel("Review threshold (score)")
    ax.set_ylim(0, 1.02)
    ax.legend(frameon=False)
    ax.set_title("Threshold sensitivity")
    fig.tight_layout()
    fig.savefig(OUT / "threshold_sensitivity.png", dpi=150)
    plt.close(fig)

    # 3. lanes by scenario
    fig, ax = plt.subplots(figsize=(8, 4.8))
    s = scen.sort_values("abusive")
    left = np.zeros(len(s))
    for lane, col in [("fast_track", "#3c8d4f"), ("review", "#e0a526"), ("audit", "#b5452f")]:
        ax.barh(s.index, s[lane], left=left, color=col, label=lane.replace("_", "-"))
        left += s[lane].values
    ax.set_xlabel("Share of claims")
    ax.legend(frameon=False, loc="lower right")
    ax.set_title("Where each scenario lands")
    fig.tight_layout()
    fig.savefig(OUT / "lanes_by_scenario.png", dpi=150)
    plt.close(fig)


def main():
    df = load()
    y = df["abusive"].values
    # Risk flag = review/audit for a RISK reason. Claims sent to review only because records are missing
    # (L03) are document requests, not abuse flags - reported separately below, and in the overall figure.
    flagged = ((df["lane"] != "fast_track") & ~df["records_only"]).astype(int).values
    any_review = (df["lane"] != "fast_track").astype(int).values
    audit = (df["lane"] == "audit").astype(int).values
    k = int(flagged.sum())
    thr = float(df["refund_claimed"].sort_values(ascending=False).iloc[k - 1]) if k else 0.0
    base = (df["refund_claimed"] >= thr).astype(int).values
    base_fixed = (df["refund_claimed"] >= 500_000).astype(int).values

    legit = df["abusive"] == 0
    res = {
        "dataset": {"claims": int(len(df)), "abusive_claims": int(y.sum()), "legit_claims": int((1 - y).sum()),
                    "taxpayers": int(df["tin"].nunique()), "periods": f"{df.period.min()} to {df.period.max()}",
                    "note": "Synthetic, seeded data with known ground truth. Not real taxpayer data."},
        "model": metrics(y, flagged),
        "model_audit_lane": metrics(y, audit),
        "model_incl_records_requests": metrics(y, any_review),
        "records_requested": {"claims": int(df["records_only"].sum()),
                              "abusive_among_them": int(df.loc[df["records_only"], "abusive"].sum())},
        "baseline_same_volume": {**metrics(y, base), "threshold": round(thr, 0)},
        "baseline_fixed_500k": metrics(y, base_fixed),
        "lanes": df["lane"].value_counts().to_dict(),
        "legit_fast_track_rate": round(float((df.loc[legit, "lane"] == "fast_track").mean()), 3),
        "legit_fast_track_rate_complete_records": round(float((df.loc[legit & ~df["records_only"], "lane"] == "fast_track").mean()), 3),
        "legit_value_fast_tracked": round(float(df.loc[legit & (df.lane == "fast_track"), "refund_claimed"].sum()), 0),
        "abusive_value_flagged_model": round(float(df.loc[(df.abusive == 1) & (flagged == 1), "refund_claimed"].sum()), 0),
        "abusive_value_flagged_baseline": round(float(df.loc[(df.abusive == 1) & (base == 1), "refund_claimed"].sum()), 0),
        "abusive_value_total": round(float(df.loc[df.abusive == 1, "refund_claimed"].sum()), 0),
        "invoices": invoice_eval(),
    }

    scen = pd.crosstab(df["scenario"], df["lane"], normalize="index").reindex(columns=["fast_track", "review", "audit"], fill_value=0)
    scen["claims"] = df.groupby("scenario").size()
    scen["abusive"] = df.groupby("scenario")["abusive"].mean()
    res["by_scenario"] = {s: {k2: (round(float(v), 3) if isinstance(v, float) else int(v)) for k2, v in row.items()}
                          for s, row in scen.iterrows()}

    sweep = []
    for t in range(5, 80, 5):
        p = (df["score"] >= t).astype(int).values
        m = metrics(y, p)
        sweep.append({"threshold": t, "precision": m["precision"], "recall": m["recall"],
                      "legit_fast_track_rate": round(1 - m["false_positive_rate"], 3)})
    sweep = pd.DataFrame(sweep)
    res["threshold_sweep"] = sweep.to_dict(orient="records")

    # errors - for the "honest limitations" section
    fn = df[(df.abusive == 1) & (flagged == 0)]
    fp = df[(df.abusive == 0) & (flagged == 1)]
    res["errors"] = {
        "false_negatives_by_scenario": fn["scenario"].value_counts().to_dict(),
        "false_positives_by_scenario": fp["scenario"].value_counts().to_dict(),
        "false_negative_examples": fn.head(5)[["claim_id", "scenario", "abuse_acts", "score"]].to_dict(orient="records"),
        "false_positive_examples": fp.sort_values("score", ascending=False).head(5)[["claim_id", "scenario", "score", "lane"]].to_dict(orient="records"),
    }
    res["explainability"] = explainability()
    res["performance"] = performance()
    ocr_file = OUT / "ocr_results.json"
    if ocr_file.exists():
        res["ocr"] = json.loads(ocr_file.read_text())

    OUT.mkdir(parents=True, exist_ok=True)
    charts(df, sweep, scen, res)
    (OUT / "results.json").write_text(json.dumps(res, indent=2, default=str))

    m, b = res["model"], res["baseline_same_volume"]
    print(f"claims={len(df)} abusive={int(y.sum())}")
    print(f"MODEL     flagged={m['flagged']} P={m['precision']} R={m['recall']} F1={m['f1']} FPR={m['false_positive_rate']}")
    print(f"BASELINE  flagged={b['flagged']} P={b['precision']} R={b['recall']} F1={b['f1']} FPR={b['false_positive_rate']}  (>= M{thr:,.0f})")
    print(f"AUDIT LANE P={res['model_audit_lane']['precision']} R={res['model_audit_lane']['recall']}")
    print("legit fast-track rate", res["legit_fast_track_rate"])
    print("invoices", res["invoices"])
    print(scen.round(2))
    print("FN by scenario", res["errors"]["false_negatives_by_scenario"])
    print("FP by scenario", res["errors"]["false_positives_by_scenario"])
    print("explainability", res["explainability"])
    print("performance", res["performance"])


if __name__ == "__main__":
    main()
