"""Shared constants and helpers for the synthetic data generator.

ALL ENTITIES PRODUCED BY THIS PACKAGE ARE FICTIONAL. No real taxpayer data is used.
"""
from __future__ import annotations

VAT_RATE = 0.15  # Standard rate - CONFIRM current Lesotho VAT rates with the economist.

# 24 monthly periods: 2024-11 .. 2026-10
PERIODS: list[str] = []
_y, _m = 2024, 11
for _ in range(24):
    PERIODS.append(f"{_y}-{_m:02d}")
    _m += 1
    if _m == 13:
        _y, _m = _y + 1, 1

PENDING_PERIODS = PERIODS[-3:]  # claims still awaiting a decision

SECTORS = [
    "Wholesale - FMCG",
    "Retail - FMCG",
    "Manufacturing - Textiles",
    "Agro-processing",
    "Construction",
    "Transport & Logistics",
    "Mining services",
    "Professional services",
]

LOW_TAX_JURISDICTIONS = ["Jurisdiction A (low-tax)", "Jurisdiction D (low-tax)"]
HIGH_TAX_JURISDICTIONS = ["Jurisdiction B", "Jurisdiction C", "Jurisdiction E"]


def tin_check_digit(body: str) -> int:
    weights = [9, 8, 7, 6, 5, 4, 3, 2]
    r = sum(int(d) * w for d, w in zip(body, weights)) % 11
    return (11 - r) % 10


def make_tin(n: int) -> str:
    """Fictional 9-digit TIN: '9' + 7-digit serial + check digit."""
    body = f"9{n:07d}"
    return body + str(tin_check_digit(body))


def tin_is_valid(tin: str) -> bool:
    tin = (tin or "").strip().replace(" ", "")
    if len(tin) != 9 or not tin.isdigit() or tin[0] != "9":
        return False
    return int(tin[-1]) == tin_check_digit(tin[:8])
