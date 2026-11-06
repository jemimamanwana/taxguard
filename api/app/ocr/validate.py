"""Invoice validation: arithmetic, TIN, registry, duplicates, supplier cross-match, dates.

Used both for (a) batch checks over every stored invoice and (b) a freshly scanned invoice.
Every check returns a machine flag *and* a plain-language message for the officer.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from ..config import VAT_RATES
from .imagehash import similarity

IMAGE_DUP_SIM = 0.995  # near-identical image = same photo re-uploaded
IMAGE_CORROBORATE_SIM = 0.85  # supports a field-level near-duplicate


def tin_check_digit(body: str) -> int:
    weights = [9, 8, 7, 6, 5, 4, 3, 2]
    return (11 - sum(int(d) * w for d, w in zip(body, weights)) % 11) % 10


def tin_is_valid(tin: str | None) -> bool:
    t = (tin or "").replace(" ", "")
    return len(t) == 9 and t.isdigit() and t[0] == "9" and int(t[-1]) == tin_check_digit(t[:8])


def _d(s: str | None) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


class InvoiceIndex:
    """Lookup structures for duplicate detection."""

    def __init__(self, invoices: pd.DataFrame):
        inv = invoices.sort_values("invoice_id")
        self.by_no: dict[tuple, list[int]] = {}
        self.by_fields: dict[tuple, list[int]] = {}
        self.hash_by_supplier: dict[str, list[tuple[int, str]]] = {}
        self.rows = inv.set_index("invoice_id", drop=False)
        for r in inv.itertuples(index=False):
            self.by_no.setdefault((r.supplier_tin, str(r.invoice_no).upper()), []).append(r.invoice_id)
            self.by_fields.setdefault((r.supplier_tin, str(r.invoice_date), round(float(r.total))), []).append(r.invoice_id)
            if isinstance(r.image_hash, str) and r.image_hash:
                self.hash_by_supplier.setdefault(r.supplier_tin, []).append((r.invoice_id, r.image_hash))

    def find_duplicate(self, inv: dict, before_id: int | None = None) -> dict | None:
        """Return the earliest *other* invoice this one duplicates, with the evidence."""
        def earlier(ids):
            ids = [i for i in ids if i != inv.get("invoice_id") and (before_id is None or i < before_id)]
            return min(ids) if ids else None

        sup = inv.get("supplier_tin")
        hit = earlier(self.by_no.get((sup, str(inv.get("invoice_no", "")).upper()), []))
        if hit:
            return {"invoice_id": int(hit), "type": "exact",
                    "message": f"Invoice number {inv.get('invoice_no')} from this supplier was already claimed (invoice #{hit})."}
        hit = earlier(self.by_fields.get((sup, str(inv.get("invoice_date")), round(float(inv.get("total") or 0))), []))
        if hit:
            other = self.rows.loc[hit]
            sim = similarity(inv.get("image_hash"), other.image_hash if isinstance(other.image_hash, str) else None)
            msg = (f"Same supplier, date and total as invoice #{hit} ({other.invoice_no}) but a different invoice "
                   f"number ({inv.get('invoice_no')}) - possible altered copy.")
            if sim >= IMAGE_CORROBORATE_SIM:
                msg += f" Image similarity {sim:.0%} supports a re-photographed copy."
            return {"invoice_id": int(hit), "type": "near", "image_similarity": round(sim, 3), "message": msg}
        h = inv.get("image_hash")
        if h:
            for oid, oh in self.hash_by_supplier.get(sup, []):
                if oid == inv.get("invoice_id") or (before_id is not None and oid >= before_id):
                    continue
                sim = similarity(h, oh)
                if sim >= IMAGE_DUP_SIM:
                    return {"invoice_id": int(oid), "type": "image", "image_similarity": round(sim, 3),
                            "message": f"Image is {sim:.1%} identical to stored invoice #{oid} - same document re-uploaded."}
        return None


def check_invoice(inv: dict, store, index: InvoiceIndex, claim_period: str | None = None,
                  before_id: int | None = None) -> dict:
    """Run every validation on one invoice. `inv` uses the invoice column names."""
    out: dict = {"flags": [], "messages": []}

    def flag(code, msg):
        out["flags"].append(code)
        out["messages"].append(msg)

    net, vat, total = (float(inv.get(k) or 0) for k in ("net", "vat", "total"))
    out["arithmetic_ok"] = abs(net + vat - total) <= max(1.0, 0.002 * total)
    if not out["arithmetic_ok"]:
        flag("ARITH", f"Net + VAT (M {net + vat:,.2f}) does not equal total (M {total:,.2f}).")
    rate = vat / net if net else 0
    out["vat_rate"] = round(rate, 4)
    out["vat_rate_ok"] = any(abs(rate - r) < 0.005 for r in VAT_RATES.values())
    if not out["vat_rate_ok"]:
        flag("RATE", f"VAT is {rate:.1%} of net - not an applicable VAT rate.")

    sup, buyer = inv.get("supplier_tin"), inv.get("buyer_tin")
    out["supplier_tin_valid"] = tin_is_valid(sup)
    out["buyer_tin_valid"] = tin_is_valid(buyer)
    if not out["supplier_tin_valid"]:
        flag("TIN", f"Supplier TIN '{sup}' fails the TIN format/check-digit test.")
    tp = store.taxpayers
    out["supplier_registered"] = bool(sup in tp.index)
    inv_date = _d(inv.get("invoice_date"))
    if not out["supplier_registered"]:
        flag("UNREG", "Supplier TIN is not on the VAT register.")
        out["supplier_age_days"] = None
    else:
        reg = _d(tp.loc[sup, "registration_date"])
        age = (inv_date - reg).days if (inv_date and reg) else None
        out["supplier_age_days"] = age
        out["supplier_name"] = tp.loc[sup, "name"]
        if age is not None and age < 0:
            flag("PREREG", "Invoice is dated before the supplier was registered for VAT.")

    period = str(inv.get("invoice_date", ""))[:7]
    listed = (sup, str(inv.get("invoice_no"))) in store.listed
    out["listed_by_supplier"] = listed
    sup_out = store.out_vat.get((sup, period))
    out["supplier_output_vat"] = None if sup_out is None else round(float(sup_out), 2)
    out["supplier_filed"] = (sup, period) in store.filed
    # "low declarer": supplier's own declared output VAT can't cover even this one invoice
    out["supplier_low_declarer"] = (sup_out is None) or (float(sup_out) < 0.5 * vat)
    if not listed:
        if out["supplier_low_declarer"]:
            decl = "filed no return" if sup_out is None else f"declared only M {float(sup_out):,.2f} output VAT"
            flag("NOMATCH", f"Not in supplier's sales listing, and supplier {decl} for {period} "
                            f"while this invoice alone carries M {vat:,.2f} VAT.")
        else:
            flag("NOLIST", f"Not yet in supplier's sales listing for {period} (supplier is an active filer - may be late filing).")

    dup = index.find_duplicate(inv, before_id=before_id)
    out["duplicate"] = dup
    if dup:
        flag("DUP", dup["message"])

    if claim_period:
        out["date_in_period"] = period <= claim_period
        if inv_date and period > claim_period:
            flag("DATE", f"Invoice dated {inv_date} is after the claim period {claim_period}.")
    out["ok"] = not out["flags"] or out["flags"] == ["NOLIST"]
    return out
