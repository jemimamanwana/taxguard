"""In-memory analytical view of the database (pandas), rebuilt on demand.

The scoring engine and the graph module read from here so a full re-score of every claim
takes seconds, not minutes. Call `invalidate()` after writes that affect scoring.
"""
from __future__ import annotations

import json
import threading

import pandas as pd
from sqlalchemy import text

from .db import engine

_lock = threading.Lock()
_store: "DataStore | None" = None


class DataStore:
    def __init__(self):
        q = lambda sql: pd.read_sql(text(sql), engine)  # noqa: E731
        self.taxpayers = q("select * from taxpayers").set_index("tin", drop=False)
        self.groups = q("select * from groups").set_index("group_id", drop=False)
        self.returns = q("select * from vat_returns")
        self.claims = q("select claim_id, tin, period, refund_claimed, input_vat_claimed, status, submitted_on, assigned_officer from claims")
        self.invoices = q("select invoice_id, claim_id, supplier_tin, buyer_tin, invoice_no, invoice_date, period_claimed, net, vat, total, kind, image_file, image_hash from invoices")
        self.listing = q("select supplier_tin, invoice_no, buyer_tin, invoice_date, period, vat from supplier_listings")
        self.rp = q("select * from related_party_txns")
        self.fin = q("select * from financials")
        self.expat = q("select * from expat_engagements")

        chk = q("select invoice_id, checks from invoices")
        rows = []
        for iid, raw in zip(chk.invoice_id, chk.checks):
            c = json.loads(raw) if isinstance(raw, str) else (raw or {})
            fl = set(c.get("flags", []))
            age = c.get("supplier_age_days")
            rows.append({
                "invoice_id": iid, "nomatch": "NOMATCH" in fl, "nolist": "NOLIST" in fl, "dup": "DUP" in fl,
                "dup_of": (c.get("duplicate") or {}).get("invoice_id"),
                "risky_supplier": ("PREREG" in fl or "UNREG" in fl or (age is not None and age < 365)
                                   or bool(c.get("supplier_low_declarer"))),
                "supplier_age_days": age,
            })
        self.invoice_checks = pd.DataFrame(rows, columns=["invoice_id", "nomatch", "nolist", "dup", "dup_of",
                                                          "risky_supplier", "supplier_age_days"])

        self.returns["total_sales"] = self.returns["standard_sales"] + self.returns["zero_rated_sales"]
        self.ret_idx = self.returns.set_index(["tin", "period"]).sort_index()
        self.listed = set(zip(self.listing.supplier_tin, self.listing.invoice_no))
        self.out_vat = self.returns.set_index(["tin", "period"])["output_vat"].to_dict()
        self.filed = set(self.out_vat.keys())


def get_store() -> DataStore:
    global _store
    with _lock:
        if _store is None:
            _store = DataStore()
        return _store


def invalidate():
    global _store
    with _lock:
        _store = None
