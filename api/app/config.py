import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("LL_DATA_DIR", ROOT / "data"))
UPLOAD_DIR = Path(os.getenv("LL_UPLOAD_DIR", ROOT / "data" / "uploads"))
EVAL_DIR = Path(os.getenv("LL_EVAL_DIR", ROOT / "eval" / "output"))

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(ROOT / 'data' / 'lekhetho.db').as_posix()}")
JWT_SECRET = os.getenv("LL_JWT_SECRET", "dev-only-secret-change-me")
JWT_TTL_MIN = int(os.getenv("LL_JWT_TTL_MIN", "720"))

# Invoice extraction
CLAUDE_MODEL = os.getenv("LL_CLAUDE_MODEL", "claude-opus-5-5")
OCR_CONFIDENCE_THRESHOLD = float(os.getenv("LL_OCR_CONF", "0.85"))

VAT_RATES = {"standard": 0.15, "zero": 0.0}  # confirm with economist
MODEL_VERSION = "taxguard-0.2"

DEFAULT_SETTINGS = {
    "lane_review_threshold": 15,
    "lane_audit_threshold": 35,
    "capital_verify_vat": 250_000,
    "r01_min_months": 8,
    "r02_gap_pct": 0.10,
    "r06_peer_z": 2.5,
    "r07_spike_z": 3.0,
    "r09_lowtax_pct": 0.05,
    "r10_loss_years": 4,
    "weights": {
        "R01": 12, "R02": 25, "R03": 35, "R04": 30, "R05": 15, "R06": 10,
        "R07": 10, "R08": 12, "R09": 20, "R10": 15, "R11": 20, "R12": 10, "ANOM": 15,
    },
}
