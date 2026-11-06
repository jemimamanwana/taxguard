from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routers.claims import router as claims
from .routers.invoices import router as invoices
from .routers.misc import admin, auth, dash, evalr, graph, portal

app = FastAPI(title="TaxGuard API", version="0.1",
              description="VAT refund triage & investigation - RSL Taxathon prototype (synthetic data only).")
app.add_middleware(GZipMiddleware, minimum_size=1000)  # weak-connection friendly
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth, claims, invoices, graph, dash, admin, portal, evalr):
    app.include_router(r, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True}


# Serve the built web app (web/dist) from the same origin when present.
DIST = Path(__file__).resolve().parents[2] / "web" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
