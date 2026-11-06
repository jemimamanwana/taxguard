"""Primary invoice extractor: Claude vision with a strict structured-output schema.

Returns every field with a confidence in [0, 1]. Raises ExtractorUnavailable when no
credentials are configured or the call fails, so the pipeline can fall back offline.
"""
from __future__ import annotations

import base64
import io
import os
import time

from PIL import Image
from pydantic import BaseModel, Field

from ..config import CLAUDE_MODEL


class ExtractorUnavailable(Exception):
    pass


class TextField(BaseModel):
    value: str | None = Field(description="Exact value as printed, or null if not present/legible")
    confidence: float = Field(description="0.0-1.0 confidence the value is read correctly")


class NumberField(BaseModel):
    value: float | None = Field(description="Numeric amount without currency symbols or thousands separators")
    confidence: float


class LineItem(BaseModel):
    description: str
    quantity: float | None
    unit_price: float | None
    amount: float | None


class InvoiceExtraction(BaseModel):
    is_tax_invoice: bool
    supplier_name: TextField
    supplier_tin: TextField
    buyer_name: TextField
    buyer_tin: TextField
    invoice_number: TextField
    invoice_date: TextField = Field(description="ISO format YYYY-MM-DD")
    currency: TextField = Field(description="ISO currency code, e.g. LSL for Maloti")
    net_amount: NumberField = Field(description="Subtotal excluding VAT")
    vat_amount: NumberField
    total_amount: NumberField
    line_items: list[LineItem]
    legibility_notes: str = Field(description="Short note on image quality issues, empty if none")


SYSTEM = (
    "You extract fields from photographed or scanned tax invoices for a revenue authority's VAT refund "
    "verification. Read only what is printed - never infer or invent a value. If a field is missing, cut off "
    "or illegible, return null with low confidence. Confidence must reflect legibility: clearly printed "
    "values ~0.95+, blurred or partly obscured values below 0.7. TINs are 9 digits. Amounts are in Maloti (M / LSL)."
)


def _prepare(image_bytes: bytes) -> tuple[str, str]:
    """Downscale to <=1568px long side (keeps cost low on weak connections) and re-encode JPEG."""
    with Image.open(io.BytesIO(image_bytes)) as im:
        im = im.convert("RGB")
        scale = 1568 / max(im.size)
        if scale < 1:
            im = im.resize((int(im.width * scale), int(im.height * scale)))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
    return base64.standard_b64encode(buf.getvalue()).decode(), "image/jpeg"


def available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))


def extract(image_bytes: bytes) -> dict:
    if not available():
        raise ExtractorUnavailable("No Anthropic credentials configured")
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover
        raise ExtractorUnavailable(str(e))

    data, media = _prepare(image_bytes)
    client = anthropic.Anthropic()
    t = time.time()
    try:
        resp = client.messages.parse(
            model=CLAUDE_MODEL,
            max_tokens=4000,
            system=SYSTEM,
            output_config={"effort": "low"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}},
                    {"type": "text", "text": "Extract the invoice fields."},
                ],
            }],
            output_format=InvoiceExtraction,
        )
    except anthropic.AuthenticationError as e:
        raise ExtractorUnavailable(f"Authentication failed: {e.message}")
    except anthropic.RateLimitError as e:
        raise ExtractorUnavailable(f"Rate limited: {e.message}")
    except anthropic.APIStatusError as e:
        raise ExtractorUnavailable(f"API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        raise ExtractorUnavailable("Could not reach the Claude API (offline?)")

    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise ExtractorUnavailable(f"No structured output (stop_reason={resp.stop_reason})")
    out = resp.parsed_output.model_dump()
    return {
        "extractor": f"claude:{CLAUDE_MODEL}",
        "latency_s": round(time.time() - t, 2),
        "usage": {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens},
        "raw": out,
    }
