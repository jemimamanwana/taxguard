"""Explainable risk rules (R01-R11) and mitigating factors (M01-M04).

Every rule returns a Reason with: code, plain-language title & detail, severity (0-1),
the bucket it belongs to, and the evidence values behind it.

Buckets:
  evidence - hard, document-level findings (R02-R05). Never offset by mitigations.
  group    - multinational / related-party structure (R09-R11). Never offset by mitigations.
  pattern  - behavioural signals (R01, R06-R08, anomaly). Mitigations can explain these away.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field


@dataclass
class Reason:
    code: str
    title: str
    detail: str
    severity: float
    bucket: str  # evidence / group / pattern / mitigation / floor
    points: float = 0.0
    evidence: dict = field(default_factory=dict)

    def to_dict(self):
        d = asdict(self)
        d["severity"] = round(self.severity, 3)
        d["points"] = round(self.points, 1)
        return d


def _m(x) -> str:
    return f"M {x:,.0f}"


def _f(x, default=0.0) -> float:
    try:
        v = float(x)
        return default if math.isnan(v) else v
    except (TypeError, ValueError):
        return default


def clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


RULE_TITLES = {
    "R01": "Persistent refund claimant",
    "R02": "Input VAT not supported by invoices",
    "R03": "Invoices from suppliers who did not declare the sale",
    "R04": "Duplicate / reused invoices",
    "R05": "Reverse-charge VAT missing on related-party imported services",
    "R06": "Input/output VAT ratio far above sector peers",
    "R07": "Refund spike versus own history",
    "R08": "High-risk or newly registered suppliers",
    "R09": "Large related-party charges to low-tax jurisdiction",
    "R10": "Persistent losses alongside growing turnover",
    "R11": "Margin far below peers with heavy intra-group purchases",
    "R12": "Related-party financing alongside losses",
    "M01": "Zero-rated export sales explain the refund",
    "M02": "Capital asset purchases explain a one-off refund",
    "M03": "Long clean compliance history",
    "M04": "Seasonal pattern matches prior year",
}


def risk_rules(f, s) -> list[Reason]:
    out: list[Reason] = []
    n12 = int(_f(f.refund_months_12))
    if n12 >= s["r01_min_months"]:
        out.append(Reason("R01", RULE_TITLES["R01"],
                          f"Claimed a refund in {n12} of the last {int(_f(f.months_12))} months.",
                          clamp((n12 - s["r01_min_months"] + 1) / 4), "pattern",
                          evidence={"refund_months_12": n12}))
    gap = _f(f.support_gap)
    if gap > s["r02_gap_pct"]:
        unsupported = _f(f.input_vat_claimed) - _f(f.inv_vat)
        out.append(Reason("R02", RULE_TITLES["R02"],
                          f"Input VAT claimed {_m(f.input_vat_claimed)} but supporting invoices total only "
                          f"{_m(f.inv_vat)} - {_m(unsupported)} ({gap:.0%}) has no invoice.",
                          clamp((gap - s["r02_gap_pct"]) / 0.35), "evidence",
                          evidence={"input_vat_claimed": round(_f(f.input_vat_claimed), 2),
                                    "invoice_vat": round(_f(f.inv_vat), 2), "gap_pct": round(gap, 3)}))
    nm, nl = _f(f.nomatch_share), _f(f.nolist_share)
    if nm > 0 or nl > 0.25:
        sev = clamp(nm / 0.25) + clamp((nl - 0.25) / 0.5) * 0.3
        parts = []
        if nm > 0:
            parts.append(f"{int(_f(f.nomatch_count))} invoice(s) worth {_m(f.vat_nomatch)} VAT ({nm:.0%}) come from "
                         f"suppliers whose own returns declared no matching output VAT")
        if nl > 0.25:
            parts.append(f"{nl:.0%} of invoice VAT not yet in active suppliers' sales listings")
        out.append(Reason("R03", RULE_TITLES["R03"], "; ".join(parts) + ".", clamp(sev), "evidence",
                          evidence={"nomatch_vat": round(_f(f.vat_nomatch), 2), "nomatch_share": round(nm, 3),
                                    "nolist_share": round(nl, 3)}))
    dc = int(_f(f.dup_count))
    if dc > 0:
        out.append(Reason("R04", RULE_TITLES["R04"],
                          f"{dc} invoice(s) worth {_m(f.vat_dup)} VAT were already claimed before "
                          f"(same invoice number, or an altered / re-photographed copy).",
                          clamp(0.6 + 0.2 * (dc - 1)), "evidence",
                          evidence={"duplicate_count": dc, "duplicate_vat": round(_f(f.vat_dup), 2)}))
    exp_rc = _f(f.rc_expected_12)
    ratio = _f(f.rc_declared_ratio, 1.0)
    if exp_rc > 10_000 and ratio < 0.5:
        out.append(Reason("R05", RULE_TITLES["R05"],
                          f"Related-party imported services imply about {_m(exp_rc)} reverse-charge VAT a year, "
                          f"but only {ratio:.0%} of that was declared in the last 12 returns.",
                          clamp(1 - ratio), "evidence",
                          evidence={"expected_reverse_charge": round(exp_rc, 2), "declared_ratio": round(ratio, 3)}))
    z = _f(f.io_peer_z)
    if z > s["r06_peer_z"]:
        ratio_io = (_f(f.in_12) + 1) / (_f(f.out_12) + 1)
        out.append(Reason("R06", RULE_TITLES["R06"],
                          f"12-month input VAT is {ratio_io:.1f}x output VAT - {z:.1f} robust standard deviations "
                          f"above {f.sector} peers.",
                          clamp((z - s["r06_peer_z"]) / 3), "pattern", evidence={"io_ratio": round(ratio_io, 2), "peer_z": round(z, 2)}))
    rz = _f(f.refund_z)
    if rz > s["r07_spike_z"]:
        pm = _f(f.prior_mean_pos)
        hist = (f"normally pays about {_m(-pm)} VAT a month" if pm < 0 else f"averaged a {_m(pm)} refund position")
        out.append(Reason("R07", RULE_TITLES["R07"],
                          f"This month's refund ({_m(-_f(f.net_vat))}) is {rz:.1f} standard deviations above normal - over "
                          f"the prior 12 months the taxpayer {hist}.",
                          clamp((rz - s["r07_spike_z"]) / 4), "pattern", evidence={"refund_z": round(rz, 2)}))
    rs = _f(f.risky_share)
    if rs > 0.10:
        out.append(Reason("R08", RULE_TITLES["R08"],
                          f"{rs:.0%} of invoice VAT comes from suppliers registered less than a year before the invoice, "
                          f"invoicing before registration, or declaring far less output VAT than they invoice.",
                          clamp(rs / 0.4), "pattern", evidence={"risky_supplier_share": round(rs, 3)}))
    lt = _f(f.rp_lowtax_share)
    if lt > s["r09_lowtax_pct"]:
        out.append(Reason("R09", RULE_TITLES["R09"],
                          f"Management fees, royalties and interest paid to low-tax group entities equal {lt:.1%} of "
                          f"turnover in {int(_f(f.fin_year))}.",
                          clamp((lt - s["r09_lowtax_pct"]) / 0.08), "group", evidence={"lowtax_share": round(lt, 4)}))
    lr = int(_f(f.loss_run))
    growth = _f(f.turnover_growth)
    if lr >= s["r10_loss_years"] and growth > 0:
        out.append(Reason("R10", RULE_TITLES["R10"],
                          f"Tax losses in {lr} consecutive years (losses carried forward {_m(f.losses_carried_forward)}) "
                          f"while turnover grew {growth:.0%}.",
                          clamp((lr - s["r10_loss_years"] + 1) / 3), "group",
                          evidence={"loss_years": lr, "turnover_growth": round(growth, 3)}))
    mg, gs = _f(f.margin_gap), _f(f.rp_goods_share)
    if mg > 0.08 and gs > 0.4:
        out.append(Reason("R11", RULE_TITLES["R11"],
                          f"Gross margin {_f(f.gross_margin):.1%} vs sector median {_f(f.sector_margin):.1%}, with "
                          f"{gs:.0%} of purchases bought from related parties.",
                          clamp((mg - 0.08) / 0.12 + 0.3), "group",
                          evidence={"gross_margin": round(_f(f.gross_margin), 4), "sector_margin": round(_f(f.sector_margin), 4),
                                    "rp_goods_share": round(gs, 3)}))
    ints = _f(f.rp_interest_share)
    if ints > 0.01 and lr >= 2:
        out.append(Reason("R12", RULE_TITLES["R12"],
                          f"Interest on intra-group loans equals {ints:.1%} of turnover in {int(_f(f.fin_year))} while the "
                          f"company reported losses for {lr} consecutive years - possible excessive related-party debt.",
                          clamp((ints - 0.01) / 0.02 + 0.3), "group",
                          evidence={"rp_interest_share": round(ints, 4), "loss_years": lr}))
    return out


DATA_GAP_RULES = "R09, R10, R11, R12"


def data_gaps(f) -> list[Reason]:
    """Missing or contradictory records. Shown explicitly - they neither lower nor raise the score."""
    out = []
    if not bool(f.has_fin):
        out.append(Reason("D01", "Financial statements missing",
                          f"No financial statements on file for {str(f.period)[:4]} - group-structure rules "
                          f"({DATA_GAP_RULES}) could not be evaluated.", 1.0, "data",
                          evidence={"rules_not_evaluated": DATA_GAP_RULES.split(", ")}))
    exp, got = int(_f(f.months_expected_12)), int(_f(f.months_filed_12))
    if exp and got < exp:
        miss = list(f.missing_periods) if isinstance(f.missing_periods, (list, tuple)) else []
        out.append(Reason("D02", "VAT returns not filed",
                          f"{exp - got} of the last {exp} monthly returns are missing ({', '.join(miss)}) - persistence and "
                          f"trend rules use incomplete history.", 1.0, "data", evidence={"missing_periods": miss}))
    mm = _f(f.turnover_mismatch, 0)
    if mm > 0.3:
        out.append(Reason("D03", "VAT returns and financial statements disagree",
                          f"Sales declared in VAT returns for {int(_f(f.turnover_mismatch_year))} differ from financial-statement "
                          f"turnover by {mm:.0%}.", 1.0, "data", evidence={"mismatch": round(mm, 3)}))
    return out


def mitigations(f, evidence_fired: bool) -> list[tuple[Reason, float, set[str]]]:
    """Return (reason, fraction of the targeted pattern points removed, codes targeted)."""
    out = []
    zs, zs12 = _f(f.zero_share), _f(f.zero_share_12)
    if zs >= 0.5 and zs12 >= 0.5:
        out.append((Reason("M01", RULE_TITLES["M01"],
                           f"{zs:.0%} of this month's sales are zero-rated exports, so output VAT is naturally low and "
                           f"a refund is expected.", 1.0, "mitigation", evidence={"zero_share": round(zs, 3)}),
                    1.0, {"R01", "R06", "R07", "ANOM"}))
    cs = _f(f.capital_share)
    if cs >= 0.4:
        out.append((Reason("M02", RULE_TITLES["M02"],
                           f"{cs:.0%} of input VAT ({_m(f.capital_vat)}) relates to capital asset purchases - consistent "
                           f"with a one-off investment refund.", 1.0, "mitigation", evidence={"capital_share": round(cs, 3)}),
                    1.0, {"R06", "R07", "ANOM"}))
    if _f(f.years_registered) >= 8 and not evidence_fired:
        out.append((Reason("M03", RULE_TITLES["M03"],
                           f"Registered {_f(f.years_registered):.0f} years with no document-level issues on this claim.",
                           1.0, "mitigation"), 0.3, {"R01", "R06", "R07", "R08", "ANOM"}))
    if int(_f(f.seasonal_hits)) >= 1 and int(_f(f.refund_months_12)) <= 5:
        out.append((Reason("M04", RULE_TITLES["M04"],
                           "A refund was also claimed in the same season last year and refunds are otherwise "
                           "infrequent - consistent with pre-festive stock build-up.", 1.0, "mitigation"),
                    0.8, {"R06", "R07", "ANOM"}))
    return out
