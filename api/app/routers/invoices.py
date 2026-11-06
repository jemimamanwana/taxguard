from __future__ import annotations

import io
import json
import re
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import DATA_DIR, UPLOAD_DIR
from ..datastore import get_store, invalidate
from ..db import get_db
from ..models import Claim, Invoice, User
from ..ocr import claude_extractor, tesseract_extractor
from ..ocr.pipeline import build_result, extract_fields
from ..security import audit, current_user, require

router = APIRouter(prefix="/invoices", tags=["invoices"])
SCAN_ROLES = ("refund_auditor", "special_sectors", "risk_analyst", "admin", "taxpayer")
IMG_DIR = DATA_DIR / "invoice_images"
MAX_BYTES = 12 * 1024 * 1024
ALLOWED = {b"\xff\xd8\xff": "jpg", b"\x89PNG": "png", b"%PDF": "pdf"}  # magic-byte allowlist (not file extension)


def sniff(data: bytes) -> str:
    for magic, kind in ALLOWED.items():
        if data.startswith(magic):
            return kind
    raise HTTPException(415, "Only JPG, PNG or PDF invoices are accepted")


def pdf_first_page(data: bytes) -> bytes:
    import pypdfium2 as pdfium

    try:
        doc = pdfium.PdfDocument(data)
        if len(doc) < 1:
            raise ValueError("empty PDF")
        img = doc[0].render(scale=150 / 72).to_pil().convert("RGB")
    except Exception as e:  # malformed / encrypted PDF
        raise HTTPException(422, f"Could not read PDF: {e}")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def _claim_for(db, claim_id, user) -> Claim | None:
    if claim_id is None:
        return None
    c = db.get(Claim, claim_id)
    if not c:
        raise HTTPException(404, "Claim not found")
    if user.role == "taxpayer" and c.tin != user.tin:
        raise HTTPException(403, "Not your claim")
    return c


@router.get("/extractors")
def extractors(user: User = Depends(current_user)):
    return {"claude": claude_extractor.available(), "tesseract": tesseract_extractor.tesseract_available()}


@router.post("/scan")
async def scan(file: UploadFile = File(...), claim_id: int | None = Form(None), prefer: str = Form("auto"),
               db: Session = Depends(get_db), user: User = Depends(require(*SCAN_ROLES))):
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File too large (max 12 MB)")
    kind = sniff(data)
    c = _claim_for(db, claim_id, user)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    upload_id = uuid.uuid4().hex
    (UPLOAD_DIR / f"{upload_id}.original.{kind}").write_bytes(data)  # original preserved unchanged
    if kind == "pdf":
        data = pdf_first_page(data)
    (UPLOAD_DIR / f"{upload_id}.jpg").write_bytes(data)
    extraction = extract_fields(data, prefer=prefer)
    (UPLOAD_DIR / f"{upload_id}.json").write_text(json.dumps(extraction, default=str), encoding="utf-8")
    store = get_store()
    res = build_result(extraction, data, store, claim_period=c.period if c else None,
                       buyer_tin_hint=c.tin if c else (user.tin if user.role == "taxpayer" else None))
    res["upload_id"] = upload_id
    res["file_type"] = kind
    audit(db, user, "invoice_scan", f"upload:{upload_id}",
          f"type={kind} extractor={res['extractor']} flags={res['checks']['flags']} claim={claim_id}")
    return res


class ConfirmIn(BaseModel):
    upload_id: str
    claim_id: int
    fields: dict  # officer/taxpayer confirmed values, keyed by extraction field name


@router.post("/confirm")
def confirm(body: ConfirmIn, db: Session = Depends(get_db), user: User = Depends(require(*SCAN_ROLES))):
    if not re.fullmatch(r"[0-9a-f]{32}", body.upload_id):
        raise HTTPException(400, "Bad upload id")
    c = _claim_for(db, body.claim_id, user)
    img = UPLOAD_DIR / f"{body.upload_id}.jpg"
    meta = UPLOAD_DIR / f"{body.upload_id}.json"
    if not img.exists() or not meta.exists():
        raise HTTPException(404, "Upload not found")
    data = img.read_bytes()
    extraction = json.loads(meta.read_text(encoding="utf-8"))
    store = get_store()
    res = build_result(extraction, data, store, claim_period=c.period, buyer_tin_hint=c.tin, overrides=body.fields)
    f = {k: v["value"] for k, v in res["fields"].items()}

    def num(x):
        try:
            return round(float(x), 2)
        except (TypeError, ValueError):
            return 0.0

    new_id = (db.query(func.max(Invoice.invoice_id)).scalar() or 0) + 1
    inv = Invoice(
        invoice_id=new_id, claim_id=c.claim_id, supplier_tin=str(f["supplier_tin"] or ""), buyer_tin=str(f["buyer_tin"] or c.tin),
        invoice_no=str(f["invoice_number"] or ""), invoice_date=str(f["invoice_date"] or ""), period_claimed=c.period,
        net=num(f["net_amount"]), vat=num(f["vat_amount"]), total=num(f["total_amount"]), currency="LSL", kind="goods",
        image_file=f"upload:{body.upload_id}.jpg", image_hash=res["image_hash"], extractor=res["extractor"],
        extraction={k: {"value": v["value"], "confidence": v["confidence"], "source": v["source"]} for k, v in res["fields"].items()},
        checks=res["checks"],
    )
    db.add(inv)
    audit(db, user, "invoice_attach", f"claim:{c.claim_id}",
          f"invoice={new_id} officer_edits={[k for k, v in res['fields'].items() if v['source'] == 'officer']}", commit=False)
    db.commit()
    from ..seed import rescore_all
    invalidate()
    rescore_all(db, verbose=False)
    db.refresh(c)
    return {"invoice_id": new_id, "checks": res["checks"], "claim": {"claim_id": c.claim_id, "score": c.score, "lane": c.lane}}


@router.get("/samples")
def samples(db: Session = Depends(get_db), user: User = Depends(require(*SCAN_ROLES))):
    demo = json.loads((DATA_DIR / "demo_cases.json").read_text())
    names = {"ordinary_fast_track": "Exporter claim", "exception_capital": "New distributor claim",
             "human_review_abuse": "Retail group claim"}
    out = []
    for key, tin in demo.items():
        if user.role == "taxpayer" and tin != user.tin:
            continue
        c = db.query(Claim).filter(Claim.tin == tin).order_by(Claim.period.desc()).first()
        invs = db.query(Invoice).filter(Invoice.claim_id == c.claim_id, Invoice.image_file.isnot(None)).all()
        for i, iv in enumerate(invs):
            if iv.image_file.startswith("upload:"):
                continue
            out.append({"file": iv.image_file, "label": f"{names[key]} - page {i + 1}", "claim_id": c.claim_id})
    if user.role != "taxpayer":
        extra = db.query(Invoice).filter(Invoice.image_file.isnot(None)).order_by(Invoice.invoice_id).limit(400).all()
        for iv in extra[::40]:
            if not iv.image_file.startswith("upload:"):
                out.append({"file": iv.image_file, "label": f"Random stored invoice #{iv.invoice_id}", "claim_id": iv.claim_id})
    return out


@router.get("/image/{name}")
def image(name: str, db: Session = Depends(get_db), user: User = Depends(require(*SCAN_ROLES))):
    if not re.fullmatch(r"(INV-\d{6}\.jpg|upload:[0-9a-f]{32}\.jpg)", name):
        raise HTTPException(400, "Bad image name")
    if user.role == "taxpayer":
        iv = db.query(Invoice).filter(Invoice.image_file == name).first()
        if not iv or iv.buyer_tin != user.tin:
            raise HTTPException(403, "Not your document")
    p = UPLOAD_DIR / name.split(":", 1)[1] if name.startswith("upload:") else IMG_DIR / name
    if not p.exists():
        raise HTTPException(404, "Image not found")
    audit(db, user, "view_invoice_image", name)
    return FileResponse(p, media_type="image/jpeg")


@router.get("/{invoice_id}/image")
def invoice_image(invoice_id: int, db: Session = Depends(get_db), user: User = Depends(require(*SCAN_ROLES))):
    iv = db.get(Invoice, invoice_id)
    if not iv or not iv.image_file:
        raise HTTPException(404, "No image")
    return image(iv.image_file, db, user)
