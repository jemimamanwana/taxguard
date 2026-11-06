from __future__ import annotations

import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..datastore import get_store
from ..db import get_db
from ..models import Claim, Decision, FlagReview, Invoice, Taxpayer, User
from ..security import DECISION_ROLES, OFFICER_ROLES, audit, mask_tin, require

router = APIRouter(prefix="/claims", tags=["claims"])
LANE_ORDER = {"audit": 0, "review": 1, "fast_track": 2}


def _reasons(c: Claim) -> dict:
    r = c.reasons
    if isinstance(r, str):
        r = json.loads(r)
    return r or {}


def claim_row(c: Claim, tp: Taxpayer | None, user: User) -> dict:
    r = _reasons(c)
    return {
        "claim_id": c.claim_id, "tin": mask_tin(c.tin, user, c.assigned_officer),
        "taxpayer": tp.name if tp else None, "sector": tp.sector if tp else None,
        "group_id": tp.group_id if tp else None, "period": c.period, "refund_claimed": round(c.refund_claimed, 2),
        "status": c.status, "score": c.score, "lane": c.lane, "assigned_officer": c.assigned_officer,
        "submitted_on": c.submitted_on, "source": c.source,
        "codes": [x["code"] for x in r.get("reasons", []) if x.get("points", 0) >= 1],
        "mitigations": [x["code"] for x in r.get("mitigations", [])],
        "summary": r.get("summary"),
    }


@router.get("")
def list_claims(lane: str | None = None, status: str | None = Query("pending"), sector: str | None = None,
                group_id: int | None = None, period: str | None = None, q: str | None = None, mine: bool = False,
                limit: int = 200, offset: int = 0, db: Session = Depends(get_db),
                user: User = Depends(require(*OFFICER_ROLES))):
    qry = db.query(Claim, Taxpayer).join(Taxpayer, Taxpayer.tin == Claim.tin)
    if status and status != "all":
        qry = qry.filter(Claim.status == status)
    if sector:
        qry = qry.filter(Taxpayer.sector == sector)
    if group_id:
        qry = qry.filter(Taxpayer.group_id == group_id)
    if period:
        qry = qry.filter(Claim.period == period)
    if q:
        qry = qry.filter(Taxpayer.name.ilike(f"%{q}%"))
    if mine:
        qry = qry.filter(Claim.assigned_officer == user.username)
    rows = qry.all()
    counts = {}
    for c, _ in rows:
        counts[c.lane] = counts.get(c.lane, 0) + 1
    if lane:
        rows = [x for x in rows if x[0].lane == lane]
    rows.sort(key=lambda x: (LANE_ORDER.get(x[0].lane, 3), -(x[0].score or 0), -x[0].refund_claimed))
    total = len(rows)
    page = rows[offset: offset + limit]
    return {"total": total, "lane_counts": counts, "items": [claim_row(c, tp, user) for c, tp in page]}


@router.get("/filters")
def filters(db: Session = Depends(get_db), user: User = Depends(require(*OFFICER_ROLES))):
    store = get_store()
    return {
        "sectors": sorted(store.taxpayers[~store.taxpayers.is_foreign.astype(bool)]["sector"].unique().tolist()),
        "periods": sorted(store.claims["period"].unique().tolist(), reverse=True),
        "groups": [{"group_id": int(g.group_id), "name": g.name} for g in store.groups.itertuples()],
    }


def build_case(c: Claim, db: Session, user: User) -> dict:
    store = get_store()
    tp = db.get(Taxpayer, c.tin)
    r = _reasons(c)
    rets = store.returns[store.returns.tin == c.tin].sort_values("period")
    invs = db.query(Invoice).filter(Invoice.claim_id == c.claim_id).order_by(Invoice.invoice_id).all()
    names = store.taxpayers["name"].to_dict()
    inv_rows = []
    for iv in invs:
        ch = iv.checks if isinstance(iv.checks, dict) else json.loads(iv.checks or "{}")
        inv_rows.append({
            "invoice_id": iv.invoice_id, "supplier_tin": mask_tin(iv.supplier_tin, user, c.assigned_officer),
            "supplier_name": names.get(iv.supplier_tin, "UNKNOWN"), "invoice_no": iv.invoice_no,
            "invoice_date": iv.invoice_date, "net": iv.net, "vat": iv.vat, "total": iv.total, "kind": iv.kind,
            "has_image": bool(iv.image_file), "flags": ch.get("flags", []), "messages": ch.get("messages", []),
            "listed_by_supplier": ch.get("listed_by_supplier"), "duplicate": ch.get("duplicate"),
            "extractor": iv.extractor,
        })
    fin = store.fin[store.fin.tin == c.tin].sort_values("year")
    decisions = db.query(Decision).filter(Decision.claim_id == c.claim_id).order_by(Decision.created_at).all()
    fr = {}
    for x in db.query(FlagReview).filter(FlagReview.claim_id == c.claim_id).order_by(FlagReview.created_at).all():
        fr[x.code] = {"status": x.status, "note": x.note, "username": x.username, "created_at": x.created_at}
    group = None
    if tp and tp.group_id:
        g = store.groups.loc[tp.group_id]
        group = {"group_id": int(tp.group_id), "name": g["name"]}
    return {
        "claim": {**claim_row(c, tp, user), "input_vat_claimed": c.input_vat_claimed, "scored_at": c.scored_at,
                  "model_version": c.model_version},
        "taxpayer": {"tin": mask_tin(c.tin, user, c.assigned_officer), "name": tp.name, "sector": tp.sector,
                     "registration_date": tp.registration_date, "size_band": tp.size_band, "town": tp.town,
                     "group": group},
        "explanation": r,
        "returns": rets[["period", "standard_sales", "zero_rated_sales", "output_vat", "input_vat", "capital_purchases",
                         "reverse_charge_vat", "net_vat", "refund_claimed"]].round(2).to_dict(orient="records"),
        "invoices": inv_rows,
        "financials": fin[["year", "turnover", "gross_margin", "net_profit", "losses_carried_forward"]].round(4).to_dict(orient="records"),
        "decisions": [{"username": d.username, "action": d.action, "comment": d.comment, "requested_docs": d.requested_docs,
                       "created_at": d.created_at, "followed_recommendation": d.followed_recommendation} for d in decisions],
        "flag_reviews": fr,
        "can_review_flags": user.role in DECISION_ROLES or user.role == "risk_analyst",
        "can_decide": user.role in DECISION_ROLES and c.status in ("pending", "docs_requested"),
        "tin_masked": mask_tin(c.tin, user, c.assigned_officer) != c.tin,
    }


def get_claim(db, claim_id) -> Claim:
    c = db.get(Claim, claim_id)
    if not c:
        raise HTTPException(404, "Claim not found")
    return c


@router.get("/{claim_id}")
def case_view(claim_id: int, db: Session = Depends(get_db), user: User = Depends(require(*OFFICER_ROLES))):
    c = get_claim(db, claim_id)
    audit(db, user, "view_case", f"claim:{claim_id}")
    return build_case(c, db, user)


@router.get("/{claim_id}/explanation")
def explanation(claim_id: int, db: Session = Depends(get_db), user: User = Depends(require(*OFFICER_ROLES))):
    c = get_claim(db, claim_id)
    audit(db, user, "view_explanation", f"claim:{claim_id}")
    return {"claim_id": claim_id, "score": c.score, "lane": c.lane, "model_version": c.model_version, **_reasons(c)}


@router.post("/{claim_id}/score")
def rescore(claim_id: int, db: Session = Depends(get_db), user: User = Depends(require(*OFFICER_ROLES))):
    from ..datastore import invalidate
    from ..seed import rescore_all

    get_claim(db, claim_id)
    invalidate()
    rescore_all(db, verbose=False)
    db.expire_all()
    c = get_claim(db, claim_id)
    audit(db, user, "score", f"claim:{claim_id}", f"score={c.score} lane={c.lane}")
    return {"claim_id": claim_id, "score": c.score, "lane": c.lane, **_reasons(c)}


class DecisionIn(BaseModel):
    action: str = Field(pattern="^(approve|request_documents|escalate)$")
    comment: str = Field(min_length=5, max_length=2000)
    requested_docs: str | None = None


class FlagIn(BaseModel):
    code: str = Field(pattern=r"^(R\d\d|ANOM|D\d\d)$")
    status: str = Field(pattern="^(reviewed|not_applicable|info_required)$")
    note: str = Field(min_length=5, max_length=1000)


@router.post("/{claim_id}/flags")
def review_flag(claim_id: int, body: FlagIn, db: Session = Depends(get_db),
                user: User = Depends(require("refund_auditor", "special_sectors", "risk_analyst", "admin"))):
    c = get_claim(db, claim_id)
    db.add(FlagReview(claim_id=claim_id, code=body.code, status=body.status, note=body.note.strip(),
                      username=user.username, created_at=datetime.utcnow()))
    audit(db, user, f"flag:{body.status}", f"claim:{claim_id}:{body.code}", body.note[:300], commit=False)
    db.commit()
    return build_case(c, db, user)


STATUS_FOR = {"approve": "approved", "request_documents": "docs_requested", "escalate": "escalated"}
MATCHES = {"approve": "fast_track", "request_documents": "review", "escalate": "audit"}


@router.post("/{claim_id}/decision")
def decide(claim_id: int, body: DecisionIn, db: Session = Depends(get_db), user: User = Depends(require(*DECISION_ROLES))):
    c = get_claim(db, claim_id)
    if c.status not in ("pending", "docs_requested"):
        raise HTTPException(409, f"Claim already {c.status}")
    if body.action == "request_documents" and not (body.requested_docs or "").strip():
        raise HTTPException(422, "List the documents being requested")
    d = Decision(claim_id=claim_id, username=user.username, action=body.action, comment=body.comment.strip(),
                 requested_docs=body.requested_docs, recommended_lane=c.lane,
                 followed_recommendation=MATCHES[body.action] == c.lane, created_at=datetime.utcnow())
    db.add(d)
    c.status = STATUS_FOR[body.action]
    c.decided_at = datetime.utcnow()
    audit(db, user, f"decision:{body.action}", f"claim:{claim_id}",
          f"recommended={c.lane}; followed={d.followed_recommendation}; comment={body.comment[:200]}", commit=False)
    db.commit()
    return build_case(c, db, user)


_ = date
