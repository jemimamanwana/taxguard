"""Core tests. Run after seeding:  python -m pytest api/tests -q"""
import json

from fastapi.testclient import TestClient

from api.app.config import DATA_DIR
from api.app.main import app
from api.app.ocr.validate import tin_is_valid
from data_gen.common import make_tin

c = TestClient(app)
DEMO = json.loads((DATA_DIR / "demo_cases.json").read_text())


def token(u):
    return {"Authorization": "Bearer " + c.post("/api/auth/login", json={"username": u, "password": "demo"}).json()["token"]}


def latest_claim(h, tin):
    items = c.get("/api/claims?status=all&limit=5000", headers=h).json()["items"]
    mine = [i for i in items if i["claim_id"] and i["taxpayer"] and i["tin"] == tin]
    return max(mine, key=lambda x: x["period"])


def test_tin_check_digit():
    assert tin_is_valid(make_tin(1234))
    t = make_tin(1234)
    assert not tin_is_valid(t[:-1] + str((int(t[-1]) + 1) % 10))


def test_demo_lanes():
    h = token("auditor1")  # assigned officer -> unmasked TINs
    assert latest_claim(h, DEMO["ordinary_fast_track"])["lane"] == "fast_track"
    ex = latest_claim(h, DEMO["exception_capital"])
    assert ex["lane"] == "review" and "M02" in ex["mitigations"]
    ab = latest_claim(h, DEMO["human_review_abuse"])
    assert ab["lane"] == "audit" and {"R03", "R04", "R09", "R10"} <= set(ab["codes"])


def test_every_flag_is_explained():
    h = token("auditor1")
    cid = c.get("/api/claims?lane=audit", headers=h).json()["items"][0]["claim_id"]
    ex = c.get(f"/api/claims/{cid}/explanation", headers=h).json()
    assert ex["reasons"] and all(r["detail"] and r["code"] for r in ex["reasons"])


def test_roles_and_masking():
    a = token("analyst1")
    row = c.get("/api/claims", headers=a).json()["items"][0]
    assert "•" in row["tin"]
    r = c.post(f"/api/claims/{row['claim_id']}/decision", headers=a, json={"action": "approve", "comment": "looks fine"})
    assert r.status_code == 403
    assert c.get("/api/admin/audit-log", headers=a).status_code == 403


def test_decision_requires_comment():
    h = token("auditor1")
    cid = c.get("/api/claims?lane=fast_track", headers=h).json()["items"][0]["claim_id"]
    assert c.post(f"/api/claims/{cid}/decision", headers=h, json={"action": "approve", "comment": ""}).status_code == 422


def test_r12_and_group_rules_on_demo_abuse():
    h = token("auditor1")
    ab = latest_claim(h, DEMO["human_review_abuse"])
    assert "R12" in ab["codes"]


def test_missing_records_are_labelled_not_scored():
    import pandas as pd
    gt = pd.read_csv(DATA_DIR / "ground_truth.csv")
    cid = int(gt[gt.scenario == "incomplete_records"].sort_values("period").iloc[-1].claim_id)
    ex = c.get(f"/api/claims/{cid}/explanation", headers=token("auditor1")).json()
    codes = {g["code"] for g in ex["data_gaps"]}
    assert codes & {"D01", "D02", "D03"}
    assert ex["lane"] != "fast_track" and any(f["code"] == "L03" for f in ex["floors"])


def test_flag_disposition_is_recorded():
    h = token("auditor1")
    cid = c.get("/api/claims?lane=audit", headers=h).json()["items"][0]["claim_id"]
    code = c.get(f"/api/claims/{cid}/explanation", headers=h).json()["reasons"][0]["code"]
    r = c.post(f"/api/claims/{cid}/flags", headers=h, json={"code": code, "status": "info_required", "note": "Asked supplier for delivery notes"})
    assert r.status_code == 200 and r.json()["flag_reviews"][code]["status"] == "info_required"


def test_upload_allowlist_and_pdf():
    import io

    from PIL import Image
    h = token("auditor1")
    assert c.post("/api/invoices/scan", headers=h, files={"file": ("x.exe", b"MZ\x90\x00junk", "application/octet-stream")}).status_code == 415
    img = Image.open(next((DATA_DIR / "invoice_images").glob("*.jpg"))).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "PDF")
    r = c.post("/api/invoices/scan", headers=h, files={"file": ("inv.pdf", buf.getvalue(), "application/pdf")})
    assert r.status_code == 200 and r.json()["file_type"] == "pdf"
