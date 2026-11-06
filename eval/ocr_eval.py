"""OCR / extraction accuracy on the generated invoice images (ground truth = invoices.csv).

Usage:  python -m eval.ocr_eval --limit 60        (needs ANTHROPIC_API_KEY for the Claude extractor)
Writes: eval/output/ocr_results.json  (picked up by run_eval and the Evaluation page)

Each image costs one API call - check --limit before running.
"""
from __future__ import annotations

import argparse
import json
import random

import pandas as pd

from api.app.config import CLAUDE_MODEL, DATA_DIR, EVAL_DIR, OCR_CONFIDENCE_THRESHOLD
from api.app.ocr.pipeline import REQUIRED, extract_fields

# USD per million tokens (input, output) - from the Claude API pricing table, update if it changes
PRICES = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50)}

TRUTH_COL = {"supplier_tin": "supplier_tin", "buyer_tin": "buyer_tin", "invoice_number": "invoice_no",
             "invoice_date": "invoice_date", "net_amount": "net", "vat_amount": "vat", "total_amount": "total"}


def same(field, got, want) -> bool:
    if got is None:
        return False
    if field.endswith("_amount"):
        try:
            return abs(float(got) - float(want)) <= 0.01
        except (TypeError, ValueError):
            return False
    g = "".join(str(got).split()).upper()
    return g == "".join(str(want).split()).upper()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--prefer", default="auto")
    a = ap.parse_args()
    inv = pd.read_csv(DATA_DIR / "invoices.csv", dtype={"supplier_tin": str, "buyer_tin": str, "invoice_no": str})
    inv = inv[inv.image_file.notna()]
    rows = inv.sample(n=min(a.limit, len(inv)), random_state=random.Random(3).randint(0, 999))
    per_field = {f: [0, 0] for f in TRUTH_COL}
    auto_ok = confident_err = n = 0
    tok_in = tok_out = 0
    extractor = None
    for r in rows.itertuples():
        data = (DATA_DIR / "invoice_images" / r.image_file).read_bytes()
        res = extract_fields(data, prefer=a.prefer)
        extractor = res["extractor"]
        raw = res["raw"]
        if res.get("usage"):
            tok_in += res["usage"]["input_tokens"]
            tok_out += res["usage"]["output_tokens"]
        n += 1
        all_auto = True
        for f, col in TRUTH_COL.items():
            fv = raw.get(f) or {}
            ok = same(f, fv.get("value"), getattr(r, col))
            per_field[f][0] += ok
            per_field[f][1] += 1
            conf_ok = (fv.get("confidence") or 0) >= OCR_CONFIDENCE_THRESHOLD
            if conf_ok and not ok:
                confident_err += 1
            if f in REQUIRED and not (ok and conf_ok):
                all_auto = False
        auto_ok += all_auto
        print(f"{n:>3} {r.image_file} {extractor} auto={all_auto}")
    total_ok = sum(v[0] for v in per_field.values())
    total = sum(v[1] for v in per_field.values())
    pin, pout = PRICES.get(CLAUDE_MODEL, (0, 0))
    cost = (tok_in * pin + tok_out * pout) / 1e6 / max(n, 1) if extractor and extractor.startswith("claude") else 0.0
    out = {
        "extractor": extractor, "images": n, "field_accuracy": round(total_ok / max(total, 1), 4),
        "per_field_accuracy": {f: round(v[0] / max(v[1], 1), 3) for f, v in per_field.items()},
        "fully_automatic_rate": round(auto_ok / max(n, 1), 3), "confident_errors": confident_err,
        "confidence_threshold": OCR_CONFIDENCE_THRESHOLD, "avg_input_tokens": round(tok_in / max(n, 1)),
        "avg_output_tokens": round(tok_out / max(n, 1)), "cost_per_invoice_usd": round(cost, 5),
    }
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (EVAL_DIR / "ocr_results.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
