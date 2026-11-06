"""Auth, graph, dashboard, admin (settings + audit log), taxpayer portal and evaluation endpoints."""
from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import DEFAULT_SETTINGS, EVAL_DIR
from ..datastore import get_store, invalidate
from ..db import get_db
from ..graph.analysis import entity_profile, group_graph, group_list
from ..models import AuditLog, Claim, Decision, Setting, Taxpayer, User
from ..security import OFFICER_ROLES, audit, create_token, current_user, mask_tin, require

# ------------------------------------------------------------------ auth
auth = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


@auth.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    from ..seed import hash_pw

    u = db.get(User, body.username.strip().lower())
    if not u or u.password_hash != hash_pw(body.password, u.username):
        audit(db, None, "login_failed", f"user:{body.username[:40]}")
        raise HTTPException(401, "Wrong username or password")
    audit(db, u, "login", f"user:{u.username}")
    return {"token": create_token(u), "user": {"username": u.username, "full_name": u.full_name, "role": u.role, "tin": u.tin}}


@auth.get("/me")
def me(user: User = Depends(current_user)):
    return {"username": user.username, "full_name": user.full_name, "role": user.role, "tin": user.tin}


@auth.get("/demo-users")
def demo_users(db: Session = Depends(get_db)):
    """Demo convenience only - lists mock accounts (password 'demo'). Remove for a pilot."""
    return [{"username": u.username, "full_name": u.full_name, "role": u.role} for u in db.query(User).all()]


# ------------------------------------------------------------------ graph
graph = APIRouter(prefix="/graph", tags=["graph"])


@graph.get("/groups")
def groups(user: User = Depends(require(*OFFICER_ROLES))):
    return group_list(get_store())


@graph.get("/groups/{gid}")
def group(gid: int, db: Session = Depends(get_db), user: User = Depends(require(*OFFICER_ROLES))):
    store = get_store()
    if gid not in store.groups.index:
        raise HTTPException(404, "Group not found")
    g = group_graph(store, gid)
    for n in g["nodes"]:
        n["label_tin"] = mask_tin(n["id"], user)
    audit(db, user, "view_group", f"group:{gid}")
    return g


@graph.get("/entity/{tin}")
def entity(tin: str, db: Session = Depends(get_db), user: User = Depends(require(*OFFICER_ROLES))):
    store = get_store()
    if tin not in store.taxpayers.index:
        raise HTTPException(404, "Unknown entity")
    p = entity_profile(store, tin)
    p["tin"] = mask_tin(tin, user)
    return p


# ------------------------------------------------------------------ dashboard
dash = APIRouter(prefix="/dashboard", tags=["dashboard"])


def at_risk_vat(r: dict) -> float:
    """Evidence-based estimate of VAT at risk on a claim (no ground truth used)."""
    tot = 0.0
    for x in r.get("reasons", []):
        e = x.get("evidence", {})
        if x["code"] == "R02":
            tot += max(0.0, e.get("input_vat_claimed", 0) - e.get("invoice_vat", 0))
        elif x["code"] == "R03":
            tot += e.get("nomatch_vat", 0)
        elif x["code"] == "R04":
            tot += e.get("duplicate_vat", 0)
    return tot


@dash.get("/metrics")
def metrics(db: Session = Depends(get_db), user: User = Depends(require(*OFFICER_ROLES))):
    rows = db.query(Claim).all()
    df = pd.DataFrame([{"claim_id": c.claim_id, "period": c.period, "lane": c.lane, "status": c.status,
                        "refund": c.refund_claimed, "score": c.score, "source": c.source,
                        "at_risk": at_risk_vat(c.reasons if isinstance(c.reasons, dict) else json.loads(c.reasons or "{}"))}
                       for c in rows])
    pend = df[df.status.isin(["pending", "docs_requested"])]
    by_period = df.groupby(["period", "lane"]).size().unstack(fill_value=0).reset_index().to_dict(orient="records")
    value_by_period = df.groupby(["period", "lane"])["refund"].sum().unstack(fill_value=0).round(0).reset_index().to_dict(orient="records")
    decisions = db.query(Decision).all()
    followed = sum(d.followed_recommendation for d in decisions)
    tp = {t.tin: t.sector for t in db.query(Taxpayer).all()}
    df["sector"] = [tp.get(c.tin) for c in rows]
    sector = df.groupby("sector").agg(claims=("claim_id", "size"), flagged=("lane", lambda s: int((s != "fast_track").sum())),
                                      at_risk=("at_risk", "sum")).round(0).reset_index().to_dict(orient="records")
    ft = df[df.lane == "fast_track"]
    return {
        "pending": {"claims": int(len(pend)), "value": round(float(pend.refund.sum())),
                    "by_lane": pend.groupby("lane").agg(n=("claim_id", "size"), value=("refund", "sum")).round(0).to_dict(orient="index")},
        "all_time": {"claims": int(len(df)), "fast_tracked": int(len(ft)), "fast_tracked_value": round(float(ft.refund.sum())),
                     "fast_track_share": round(len(ft) / max(len(df), 1), 3),
                     "value_under_review": round(float(df[df.lane != "fast_track"].refund.sum())),
                     "estimated_vat_protected": round(float(df[df.lane != "fast_track"].at_risk.sum()))},
        "turnaround_assumption_days": {"fast_track": 3, "review": 14, "audit": 60, "current_manual_average": 45},
        "decisions": {"count": len(decisions), "followed_recommendation": followed},
        "by_period": by_period, "value_by_period": value_by_period, "by_sector": sector,
    }


# ------------------------------------------------------------------ admin
admin = APIRouter(prefix="/admin", tags=["admin"])


@admin.get("/settings")
def get_settings(db: Session = Depends(get_db), user: User = Depends(require("admin", "risk_analyst"))):
    from ..seed import load_settings
    return {"settings": load_settings(db), "defaults": DEFAULT_SETTINGS}


class SettingsIn(BaseModel):
    settings: dict
    reason: str = Field(min_length=5)


@admin.put("/settings")
def put_settings(body: SettingsIn, db: Session = Depends(get_db), user: User = Depends(require("admin"))):
    from ..seed import load_settings, rescore_all
    cur = load_settings(db)
    allowed = set(DEFAULT_SETTINGS)
    new = {k: v for k, v in body.settings.items() if k in allowed}
    if "weights" in new:
        new["weights"] = {k: float(v) for k, v in new["weights"].items() if k in DEFAULT_SETTINGS["weights"]}
    merged = {**cur, **new, "weights": {**cur["weights"], **new.get("weights", {})}}
    if merged["lane_review_threshold"] >= merged["lane_audit_threshold"]:
        raise HTTPException(422, "Review threshold must be below audit threshold")
    s = db.get(Setting, "scoring")
    s.value = merged
    audit(db, user, "settings_change", "settings:scoring", f"{body.reason} | {json.dumps(new)[:500]}", commit=False)
    db.commit()
    invalidate()
    rescore_all(db, verbose=False)
    return {"settings": merged}


@admin.get("/audit-log")
def audit_log(limit: int = 300, username: str | None = None, db: Session = Depends(get_db),
              user: User = Depends(require("admin"))):
    q = db.query(AuditLog)
    if username:
        q = q.filter(AuditLog.username == username)
    rows = q.order_by(AuditLog.id.desc()).limit(limit).all()
    return [{"ts": r.ts, "username": r.username, "role": r.role, "action": r.action, "entity": r.entity, "detail": r.detail} for r in rows]


# ------------------------------------------------------------------ taxpayer portal
portal = APIRouter(prefix="/portal", tags=["portal"])

STATUS_TEXT = {
    "pending": "Received - being checked",
    "approved": "Approved - refund being paid",
    "adjusted": "Finalised with adjustments",
    "docs_requested": "Action needed - documents requested",
    "escalated": "Under detailed review",
}


@portal.get("/claims")
def my_claims(db: Session = Depends(get_db), user: User = Depends(require("taxpayer"))):
    tp = db.get(Taxpayer, user.tin)
    cs = db.query(Claim).filter(Claim.tin == user.tin).order_by(Claim.period.desc()).all()
    out = []
    for c in cs:
        req = db.query(Decision).filter(Decision.claim_id == c.claim_id, Decision.action == "request_documents").order_by(Decision.created_at.desc()).first()
        out.append({"claim_id": c.claim_id, "period": c.period, "refund_claimed": c.refund_claimed, "status": c.status,
                    "status_text": STATUS_TEXT.get(c.status, c.status), "submitted_on": c.submitted_on,
                    "documents_requested": req.requested_docs if req else None,
                    "message": req.comment if req else None})
    return {"taxpayer": {"tin": tp.tin, "name": tp.name, "sector": tp.sector}, "claims": out}


class ClaimIn(BaseModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    output_vat: float = Field(ge=0)
    input_vat: float = Field(ge=0)


@portal.post("/claims")
def submit_claim(body: ClaimIn, db: Session = Depends(get_db), user: User = Depends(require("taxpayer"))):
    refund = body.input_vat - body.output_vat
    if refund <= 0:
        raise HTTPException(422, "Input VAT must exceed output VAT for a refund claim")
    from sqlalchemy import func
    cid = (db.query(func.max(Claim.claim_id)).scalar() or 0) + 1
    c = Claim(claim_id=cid, tin=user.tin, period=body.period, refund_claimed=round(refund, 2),
              input_vat_claimed=body.input_vat, submitted_on=datetime.utcnow().date().isoformat(), status="pending",
              assigned_officer="auditor1", source="portal")
    db.add(c)
    audit(db, user, "portal_submit_claim", f"claim:{cid}", f"refund={refund:.2f}", commit=False)
    db.commit()
    return {"claim_id": cid, "status": c.status}


# ------------------------------------------------------------------ evaluation
evalr = APIRouter(prefix="/eval", tags=["evaluation"])


@evalr.get("/results")
def results(user: User = Depends(require(*OFFICER_ROLES))):
    f = EVAL_DIR / "results.json"
    if not f.exists():
        raise HTTPException(404, "Run `python -m eval.run_eval` first")
    return json.loads(f.read_text())


@evalr.get("/charts/{name}")
def chart(name: str, user: User = Depends(require(*OFFICER_ROLES))):
    if name not in ("model_vs_baseline.png", "threshold_sensitivity.png", "lanes_by_scenario.png"):
        raise HTTPException(404, "Unknown chart")
    return FileResponse(EVAL_DIR / name, media_type="image/png")
