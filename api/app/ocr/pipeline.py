"""Smart invoice capture pipeline: extract -> normalise -> hash -> validate -> auto-fill decision."""
from __future__ import annotations

import io

from PIL import Image

from ..config import OCR_CONFIDENCE_THRESHOLD
from . import claude_extractor, tesseract_extractor
from .imagehash import dhash
from .validate import InvoiceIndex, check_invoice

FIELD_MAP = {  # extraction field -> invoice column
    "supplier_name": "supplier_name", "supplier_tin": "supplier_tin", "buyer_name": "buyer_name",
    "buyer_tin": "buyer_tin", "invoice_number": "invoice_no", "invoice_date": "invoice_date",
    "currency": "currency", "net_amount": "net", "vat_amount": "vat", "total_amount": "total",
}
REQUIRED = ["supplier_tin", "invoice_number", "invoice_date", "net_amount", "vat_amount", "total_amount"]


def extract_fields(image_bytes: bytes, prefer: str = "auto") -> dict:
    errors = []
    if prefer in ("auto", "claude"):
        try:
            return claude_extractor.extract(image_bytes)
        except claude_extractor.ExtractorUnavailable as e:
            errors.append(str(e))
    res = tesseract_extractor.extract(image_bytes)
    res["fallback_reason"] = "; ".join(errors) or None
    return res


def _clean_tin(v):
    return None if v is None else "".join(ch for ch in str(v) if ch.isdigit()) or None


def build_result(extraction: dict, image_bytes: bytes, store, claim_period: str | None = None,
                 buyer_tin_hint: str | None = None, overrides: dict | None = None) -> dict:
    raw = extraction["raw"]
    fields = {}
    for k in FIELD_MAP:
        f = raw.get(k) or {"value": None, "confidence": 0.0}
        val = f.get("value")
        if k.endswith("_tin"):
            val = _clean_tin(val)
        fields[k] = {"value": val, "confidence": round(float(f.get("confidence") or 0), 2), "source": "extracted"}
    if overrides:
        for k, v in overrides.items():
            if k in fields and v not in (None, ""):
                fields[k] = {"value": v, "confidence": 1.0, "source": "officer"}
    if buyer_tin_hint and not fields["buyer_tin"]["value"]:
        fields["buyer_tin"] = {"value": buyer_tin_hint, "confidence": 1.0, "source": "claim"}

    for k, f in fields.items():
        f["needs_review"] = f["source"] == "extracted" and (f["value"] in (None, "") or f["confidence"] < OCR_CONFIDENCE_THRESHOLD)

    with Image.open(io.BytesIO(image_bytes)) as im:
        h = dhash(im)
    inv = {FIELD_MAP[k]: f["value"] for k, f in fields.items()}
    for n in ("net", "vat", "total"):
        try:
            inv[n] = float(inv[n]) if inv[n] is not None else 0.0
        except (TypeError, ValueError):
            inv[n] = 0.0
    inv["image_hash"] = h
    inv["invoice_id"] = None
    index = InvoiceIndex(store.invoices)
    checks = check_invoice(inv, store, index, claim_period)
    if inv.get("supplier_tin") in store.taxpayers.index:
        reg_name = store.taxpayers.loc[inv["supplier_tin"], "name"]
        ext_name = (fields["supplier_name"]["value"] or "").lower()
        checks["supplier_name_matches_registry"] = bool(ext_name) and (reg_name.lower()[:12] in ext_name or ext_name[:12] in reg_name.lower())
        checks["registry_name"] = reg_name
    n_req = len(REQUIRED)
    auto = sum(1 for k in REQUIRED if not fields[k]["needs_review"])
    return {
        "extractor": extraction["extractor"],
        "fallback_reason": extraction.get("fallback_reason"),
        "latency_s": extraction.get("latency_s"),
        "usage": extraction.get("usage"),
        "fields": fields,
        "line_items": raw.get("line_items", []),
        "is_tax_invoice": raw.get("is_tax_invoice"),
        "legibility_notes": raw.get("legibility_notes"),
        "image_hash": h,
        "checks": checks,
        "autofill": {"required_fields": n_req, "auto_filled": auto, "needs_review": n_req - auto,
                     "fully_automatic": auto == n_req, "threshold": OCR_CONFIDENCE_THRESHOLD},
    }
