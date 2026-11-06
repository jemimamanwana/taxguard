"""Offline fallback extractor: Tesseract OCR + regex parsing.

Lower accuracy than the vision model but works with no internet connection. If Tesseract
is not installed, returns empty fields so the officer can type them (manual mode).
"""
from __future__ import annotations

import io
import re
import shutil

from PIL import Image, ImageOps

FIELDS_TEXT = ("supplier_name", "supplier_tin", "buyer_name", "buyer_tin", "invoice_number", "invoice_date", "currency")
FIELDS_NUM = ("net_amount", "vat_amount", "total_amount")


def _empty(conf=0.0):
    raw = {f: {"value": None, "confidence": conf} for f in FIELDS_TEXT + FIELDS_NUM}
    raw.update({"is_tax_invoice": False, "line_items": [], "legibility_notes": ""})
    return raw


def tesseract_available() -> bool:
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return shutil.which("tesseract") is not None


def _num(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return float(s.replace(",", "").replace(" ", ""))
    except ValueError:
        return None


def extract(image_bytes: bytes) -> dict:
    if not tesseract_available():
        raw = _empty()
        raw["legibility_notes"] = "No OCR engine available offline - please type the fields."
        return {"extractor": "manual", "raw": raw}
    import pytesseract

    with Image.open(io.BytesIO(image_bytes)) as im:
        g = ImageOps.autocontrast(im.convert("L"))
        data = pytesseract.image_to_data(g, output_type=pytesseract.Output.DICT)
        text = pytesseract.image_to_string(g)
    words = [w for w, c in zip(data["text"], data["conf"]) if w.strip() and float(c) >= 0]
    confs = [float(c) / 100 for w, c in zip(data["text"], data["conf"]) if w.strip() and float(c) >= 0]
    base_conf = round(min(0.8, (sum(confs) / len(confs)) if confs else 0.0), 2)
    raw = _empty()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    tins = re.findall(r"\b9\d{8}\b", text.replace(" ", ""))
    if tins:
        raw["supplier_tin"] = {"value": tins[0], "confidence": base_conf}
    if len(tins) > 1:
        raw["buyer_tin"] = {"value": tins[1], "confidence": base_conf}
    m = re.search(r"Invoice\s*No[:.]?\s*([A-Z0-9]+-\d+)", text, re.I)
    if m:
        raw["invoice_number"] = {"value": m.group(1), "confidence": base_conf}
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        raw["invoice_date"] = {"value": m.group(1), "confidence": base_conf}
    for key, pat in [("net_amount", r"Subtotal[^\d]*([\d,]+\.\d{2})"), ("vat_amount", r"VAT\s*@[^\d]*\d+%?\s*([\d,]+\.\d{2})"),
                     ("total_amount", r"TOTAL[^\d]*([\d,]+\.\d{2})")]:
        m = re.search(pat, text, re.I)
        if m:
            raw[key] = {"value": _num(m.group(1)), "confidence": base_conf}
    m = re.search(r"Bill to:\s*(.+)", text)
    if m:
        raw["buyer_name"] = {"value": m.group(1).strip(), "confidence": base_conf * 0.8}
    for ln in lines[:4]:
        if "(Pty)" in ln or "Ltd" in ln:
            raw["supplier_name"] = {"value": ln.split("|")[0].strip(), "confidence": base_conf * 0.8}
            break
    raw["currency"] = {"value": "LSL", "confidence": 0.6}
    raw["is_tax_invoice"] = "TAX INVOICE" in text.upper()
    raw["legibility_notes"] = f"Offline OCR (Tesseract), {len(words)} words read."
    return {"extractor": "tesseract", "raw": raw}
