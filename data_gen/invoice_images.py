"""Render synthetic tax-invoice images with Pillow so the OCR pipeline can be demoed.

A share of images are degraded (blur, rotation, dim lighting, JPEG artefacts) to mimic
phone photos. Duplicate invoices are rendered as a *re-photographed* copy of the original.
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from .common import PERIODS, VAT_RATE

FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/calibri.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf",
]
BOLD_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/calibrib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]
TEMPLATE_COLOURS = [(18, 70, 120), (120, 30, 40), (20, 100, 60), (70, 60, 20), (60, 30, 110)]


def _font(size: int, bold: bool = False):
    for p in BOLD_CANDIDATES if bold else FONT_CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def line_items(inv: dict, kind: str, rng: random.Random) -> list[tuple[str, int, float, float]]:
    from .generate import EQUIP_ITEMS, FMCG_ITEMS, GENERAL_ITEMS

    pool = EQUIP_ITEMS if kind == "equipment" else (FMCG_ITEMS if rng.random() < 0.7 else GENERAL_ITEMS)
    n = rng.randint(1, 3) if kind == "equipment" else rng.randint(2, 5)
    names = rng.sample(pool, k=min(n, len(pool)))
    net = round(inv["net"], 2)
    shares = [rng.uniform(0.5, 1.5) for _ in names]
    s = sum(shares)
    lines, used = [], 0.0
    for i, nm in enumerate(names):
        if i == len(names) - 1:
            amt = round(net - used, 2)
            lines.append((nm, 1, amt, amt))
        else:
            target = net * shares[i] / s
            qty = max(1, int(target / rng.uniform(80, 900))) if kind != "equipment" else 1
            unit = round(target / qty, 2)
            amt = round(unit * qty, 2)
            used += amt
            lines.append((nm, qty, unit, amt))
    return lines


def money(x: float) -> str:
    return f"M {x:,.2f}"


def render_invoice(inv: dict, supplier, buyer, path: Path, rng: random.Random,
                   template: int, degrade: str | None) -> None:
    W, H = 1240, 1754  # A4 @150dpi
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    col = TEMPLATE_COLOURS[template % len(TEMPLATE_COLOURS)]
    f_title, f_big, f_med, f_sm = _font(56, True), _font(34, True), _font(28), _font(24)

    if template % 3 == 0:
        d.rectangle([0, 0, W, 170], fill=col)
        d.text((60, 45), supplier.name, font=f_big, fill="white")
        d.text((60, 100), f"{supplier.town}, Lesotho  |  VAT TIN: {supplier.tin}", font=f_sm, fill="white")
        y = 220
        d.text((60, y), "TAX INVOICE", font=f_title, fill=col)
    elif template % 3 == 1:
        d.text((60, 60), "TAX INVOICE", font=f_title, fill=col)
        d.text((W - 620, 60), supplier.name, font=f_med, fill="black")
        d.text((W - 620, 100), f"VAT Reg / TIN: {supplier.tin}", font=f_sm, fill="black")
        d.text((W - 620, 132), f"{supplier.town}, Lesotho", font=f_sm, fill="black")
        d.line([60, 190, W - 60, 190], fill=col, width=4)
        y = 160
    else:
        d.rectangle([40, 40, W - 40, H - 40], outline=col, width=3)
        d.text((80, 80), supplier.name.upper(), font=f_big, fill=col)
        d.text((80, 130), f"TIN {supplier.tin}  -  {supplier.town}", font=f_sm, fill="black")
        d.text((80, 200), "TAX INVOICE", font=f_title, fill="black")
        y = 220

    y += 100
    d.text((60, y), f"Invoice No:  {inv['invoice_no']}", font=f_med, fill="black")
    d.text((700, y), f"Date:  {inv['invoice_date']}", font=f_med, fill="black")
    y += 60
    d.text((60, y), "Bill to:", font=f_med, fill=col)
    d.text((200, y), buyer.name, font=f_med, fill="black")
    y += 40
    d.text((200, y), f"Buyer TIN: {buyer.tin}", font=f_sm, fill="black")
    y += 80

    d.rectangle([60, y, W - 60, y + 50], fill=(235, 235, 235))
    for x, label in [(75, "Description"), (680, "Qty"), (800, "Unit price"), (1010, "Amount")]:
        d.text((x, y + 10), label, font=f_sm, fill="black")
    y += 70
    for nm, qty, unit, amt in line_items(inv, inv.get("kind", "goods"), rng):
        d.text((75, y), nm, font=f_sm, fill="black")
        d.text((680, y), str(qty), font=f_sm, fill="black")
        d.text((800, y), f"{unit:,.2f}", font=f_sm, fill="black")
        d.text((1010, y), f"{amt:,.2f}", font=f_sm, fill="black")
        y += 46
    y += 30
    d.line([700, y, W - 60, y], fill="black", width=2)
    y += 20
    for label, val, bold in [("Subtotal (excl. VAT)", inv["net"], False),
                             (f"VAT @ {int(VAT_RATE * 100)}%", inv["vat"], False),
                             ("TOTAL (LSL)", inv["total"], True)]:
        d.text((700, y), label, font=_font(28, bold), fill="black")
        d.text((1010, y), f"{val:,.2f}", font=_font(28, bold), fill="black")
        y += 50
    d.text((60, H - 160), "Thank you for your business. All amounts in Maloti (LSL).", font=f_sm, fill=(90, 90, 90))
    d.text((60, H - 120), "SYNTHETIC DOCUMENT - generated for the RSL Taxathon prototype. Not a real invoice.",
           font=_font(20), fill=(150, 150, 150))

    # ------------- degradation to mimic phone capture
    if degrade == "blur":
        img = img.filter(ImageFilter.GaussianBlur(radius=rng.uniform(1.2, 2.2)))
    elif degrade == "rotate":
        img = img.rotate(rng.uniform(-4, 4), expand=True, fillcolor=(205, 200, 190))
    elif degrade == "dim":
        img = ImageEnhance.Brightness(img).enhance(rng.uniform(0.6, 0.75))
        img = ImageEnhance.Contrast(img).enhance(0.8)
    elif degrade == "photo":  # re-photographed copy
        img = img.rotate(rng.uniform(-2.5, 2.5), expand=True, fillcolor=(190, 185, 175))
        img = ImageEnhance.Brightness(img).enhance(rng.uniform(0.8, 0.95))
        img = img.filter(ImageFilter.GaussianBlur(radius=0.8))
    img = img.resize((img.width * 3 // 4, img.height * 3 // 4))
    img.save(path, "JPEG", quality=rng.randint(68, 85))


def render_images(gen, out_dir: Path, sample_size: int = 260) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    by_id = {iv["invoice_id"]: iv for iv in gen.invoices}
    latest = PERIODS[-1]
    demo_tins = {gen.demo1.tin, gen.demo2.tin, gen.demo3.tin}

    chosen: list[dict] = [iv for iv in gen.invoices if iv["buyer_tin"] in demo_tins and iv["period_claimed"] == latest]
    others = [iv for iv in gen.invoices if iv not in chosen]
    special = [iv for iv in others if iv.get("_truth")]
    chosen += rng.sample(special, k=min(60, len(special)))
    rest = [iv for iv in others if not iv.get("_truth")]
    chosen += rng.sample(rest, k=min(sample_size - 60, len(rest)))
    # make sure every chosen duplicate has its original rendered first
    for iv in list(chosen):
        if iv.get("_dup_of") and by_id[iv["_dup_of"]] not in chosen:
            chosen.insert(0, by_id[iv["_dup_of"]])
    seen = set()
    ordered = []
    for iv in chosen:
        if iv["invoice_id"] not in seen:
            seen.add(iv["invoice_id"])
            ordered.append(iv)

    tmpl_of: dict[str, int] = {}
    for iv in sorted(ordered, key=lambda x: bool(x.get("_dup_of"))):
        sup = gen.by_tin[iv["supplier_tin"]]
        buyer = gen.by_tin[iv["buyer_tin"]]
        tmpl = tmpl_of.setdefault(sup.tin, rng.randint(0, 14))
        if iv.get("_dup_of"):
            degrade = "photo"
            seed = by_id[iv["_dup_of"]]["invoice_id"]  # same line items as the original
        else:
            degrade = rng.choices([None, "blur", "rotate", "dim"], weights=[60, 14, 14, 12])[0]
            seed = iv["invoice_id"]
        fname = f"INV-{iv['invoice_id']:06d}.jpg"
        render_invoice(iv, sup, buyer, out_dir / fname, random.Random(seed), tmpl, degrade)
        iv["image_file"] = fname
        iv["_degrade"] = degrade or "clean"
    print(f"invoice images      : {len(ordered)} -> {out_dir}")
