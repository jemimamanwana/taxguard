"""Perceptual image hashing used to spot re-photographed invoices.

Pillow-only implementation:
  1. deskew  - try small rotations, keep the one that best aligns text rows
               (maximum variance of the horizontal ink projection)
  2. trim    - crop to the inked content box so borders / background don't matter
  3. hash    - difference hash over a grid of the content region

Limitation (documented in eval): invoices printed from the same supplier template look
alike, so the image hash is combined with field-level evidence (same supplier, date and
amounts) before a duplicate is asserted.
"""
from __future__ import annotations

from PIL import Image, ImageOps

HASH_W, HASH_H = 32, 48


def _ink(img: Image.Image, width: int = 360) -> Image.Image:
    g = ImageOps.autocontrast(img.convert("L"), cutoff=1)
    h = int(g.height * width / g.width)
    g = g.resize((width, h), Image.Resampling.BILINEAR)
    return g.point(lambda v: 255 if v < 110 else 0)  # ink = white


def _row_variance(bw: Image.Image) -> float:
    w, h = bw.size
    px = bw.load()
    sums = [sum(1 for x in range(0, w, 2) if px[x, y]) for y in range(h)]
    m = sum(sums) / h
    return sum((s - m) ** 2 for s in sums) / h


def deskew_angle(img: Image.Image) -> float:
    bw = _ink(img, 240)
    best, best_a = -1.0, 0.0
    for a10 in range(-50, 51, 5):
        a = a10 / 10
        v = _row_variance(bw.rotate(a, fillcolor=0))
        if v > best:
            best, best_a = v, a
    return best_a


def normalise(img: Image.Image) -> Image.Image:
    a = deskew_angle(img)
    g = ImageOps.autocontrast(img.convert("L"), cutoff=1)
    if a:
        g = g.rotate(a, fillcolor=255, resample=Image.Resampling.BILINEAR, expand=False)
    ink = g.point(lambda v: 255 if v < 110 else 0)
    box = ink.getbbox()
    return g.crop(box) if box else g


def dhash(img: Image.Image) -> str:
    g = normalise(img).resize((HASH_W + 1, HASH_H), Image.Resampling.LANCZOS)
    px = list(g.getdata())
    bits = []
    for y in range(HASH_H):
        row = px[y * (HASH_W + 1):(y + 1) * (HASH_W + 1)]
        bits.extend("1" if row[x] > row[x + 1] else "0" for x in range(HASH_W))
    n = int("".join(bits), 2)
    return f"{n:0{HASH_W * HASH_H // 4}x}"


def similarity(h1: str | None, h2: str | None) -> float:
    if not h1 or not h2 or len(h1) != len(h2):
        return 0.0
    diff = bin(int(h1, 16) ^ int(h2, 16)).count("1")
    return 1.0 - diff / (len(h1) * 4)


def hash_file(path) -> str:
    with Image.open(path) as im:
        return dhash(im)
