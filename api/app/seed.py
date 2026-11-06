"""Batch ingest: load the CSV extracts into the database, validate invoices, score claims.

This is also the pilot integration path: RSL exports CSVs -> `python -m api.app.seed`.
Ground-truth files are deliberately NOT loaded (they are for offline evaluation only).
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone

import pandas as pd

from .config import DATA_DIR, DEFAULT_SETTINGS, MODEL_VERSION
from .datastore import get_store, invalidate
from .db import Base, SessionLocal, engine

JSON_CAST = "::json" if engine.dialect.name == "postgresql" else ""
from .models import AuditLog, Claim, Setting, User
from .ocr.imagehash import hash_file
from .ocr.validate import InvoiceIndex, check_invoice
from .scoring.engine import score_all


def hash_pw(pw: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{pw}".encode()).hexdigest()


def load_settings(db) -> dict:
    s = db.get(Setting, "scoring")
    merged = json.loads(json.dumps(DEFAULT_SETTINGS))
    if s:
        merged.update({k: v for k, v in s.value.items() if k != "weights"})
        merged["weights"].update(s.value.get("weights", {}))
    return merged


def validate_all_invoices(db, verbose=True):
    """Run invoice checks over every stored invoice (batch mode)."""
    invalidate()
    store = get_store()
    claim_period = store.claims.set_index("claim_id")["period"].to_dict()
    idx = InvoiceIndex(store.invoices)
    updates = []
    for r in store.invoices.itertuples(index=False):
        inv = r._asdict()
        c = check_invoice(inv, store, idx, claim_period.get(r.claim_id), before_id=r.invoice_id)
        updates.append({"invoice_id": r.invoice_id, "checks": json.dumps(c, default=str)})
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TEMP TABLE IF NOT EXISTS _chk (invoice_id INTEGER PRIMARY KEY, checks TEXT)")
        conn.exec_driver_sql("DELETE FROM _chk")
        conn.execute(__import__("sqlalchemy").text("INSERT INTO _chk (invoice_id, checks) VALUES (:invoice_id, :checks)"), updates)
        conn.exec_driver_sql(f"UPDATE invoices SET checks = (SELECT checks{JSON_CAST} FROM _chk WHERE _chk.invoice_id = invoices.invoice_id)")
    if verbose:
        print(f"validated {len(updates)} invoices")
    invalidate()


def rescore_all(db, verbose=True) -> dict[int, dict]:
    settings = load_settings(db)
    store = get_store()
    t = time.time()
    _, results = score_all(store, settings)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = [{"claim_id": cid, "score": r["score"], "lane": r["lane"], "reasons": json.dumps(r)} for cid, r in results.items()]
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TEMP TABLE IF NOT EXISTS _sc (claim_id INTEGER PRIMARY KEY, score REAL, lane TEXT, reasons TEXT)")
        conn.exec_driver_sql("DELETE FROM _sc")
        conn.execute(__import__("sqlalchemy").text("INSERT INTO _sc VALUES (:claim_id, :score, :lane, :reasons)"), rows)
        conn.exec_driver_sql(
            "UPDATE claims SET score = (SELECT score FROM _sc WHERE _sc.claim_id = claims.claim_id), "
            "lane = (SELECT lane FROM _sc WHERE _sc.claim_id = claims.claim_id), "
            f"reasons = (SELECT reasons{JSON_CAST} FROM _sc WHERE _sc.claim_id = claims.claim_id)")
        conn.execute(__import__("sqlalchemy").text("UPDATE claims SET scored_at = :t, model_version = :v"),
                     {"t": now, "v": MODEL_VERSION})
    if verbose:
        lanes = pd.Series([r["lane"] for r in results.values()]).value_counts().to_dict()
        print(f"scored {len(results)} claims in {time.time() - t:.1f}s  lanes={lanes}")
    return results


USERS = [
    ("auditor1", "Palesa Mokoena", "refund_auditor", None),
    ("auditor2", "Thabo Letsie", "refund_auditor", None),
    ("analyst1", "Lerato Nthati", "risk_analyst", None),
    ("special1", "Mpho Ramakoae", "special_sectors", None),
    ("admin1", "System Administrator", "admin", None),
]


def main(images: bool = True):
    t0 = time.time()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    files = {
        "taxpayers": "taxpayers.csv", "groups": "groups.csv", "vat_returns": "vat_returns.csv",
        "claims": "claims.csv", "invoices": "invoices.csv", "supplier_listings": "supplier_listings.csv",
        "related_party_txns": "related_party_txns.csv", "financials": "financials.csv",
        "expat_engagements": "expat_engagements.csv",
    }
    str_cols = {"tin", "supplier_tin", "buyer_tin", "payer_tin", "payee_tin", "parent_tin", "sister_tin",
                "hub_tin", "engaging_tin", "paying_tin", "invoice_no"}
    for table, fname in files.items():
        df = pd.read_csv(DATA_DIR / fname, dtype={c: str for c in str_cols})
        if table == "taxpayers":
            df["group_id"] = df["group_id"].astype("Int64")
            df["is_foreign"] = df["is_foreign"].astype(bool)
            df["low_tax"] = df["low_tax"].astype(bool)
            df["role"] = df["role"].fillna("")
        if table == "invoices":
            df["image_hash"] = None
            if images:
                hashes = []
                for f in df["image_file"]:
                    p = DATA_DIR / "invoice_images" / str(f)
                    hashes.append(hash_file(p) if isinstance(f, str) and p.exists() else None)
                df["image_hash"] = hashes
            df["extractor"] = None
        if table == "claims":
            df["source"] = "batch"
        df.to_sql(table, engine, if_exists="append", index=False, chunksize=2000)
        print(f"loaded {table:<20} {len(df):>6}")

    db = SessionLocal()
    for u, name, role, tin in USERS:
        db.add(User(username=u, full_name=name, role=role, password_hash=hash_pw("demo", u), tin=tin))
    demo = json.loads((DATA_DIR / "demo_cases.json").read_text())
    for uname, key in [("maluti", "ordinary_fast_track"), ("senqu", "exception_capital"), ("thababosiu", "human_review_abuse")]:
        db.add(User(username=uname, full_name=f"Taxpayer portal ({uname})", role="taxpayer",
                    password_hash=hash_pw("demo", uname), tin=demo[key]))
    db.add(Setting(key="scoring", value=DEFAULT_SETTINGS))
    db.commit()

    # assign pending claims to the two refund auditors (demo cases -> auditor1)
    pend = db.query(Claim).filter(Claim.status == "pending").order_by(Claim.claim_id).all()
    demo_tins = set(demo.values())
    for i, c in enumerate(pend):
        c.assigned_officer = "auditor1" if (c.tin in demo_tins or i % 2 == 0) else "auditor2"
    db.add(AuditLog(username="system", role="system", action="batch_ingest", entity="all",
                    detail=f"Loaded CSV extracts from {DATA_DIR.name}"))
    db.commit()

    validate_all_invoices(db)
    rescore_all(db)
    db.close()
    print(f"seed complete in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main(images="--no-images" not in sys.argv)
