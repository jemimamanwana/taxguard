"""TaxGuard - synthetic dataset generator.

Produces a reproducible (seeded) dataset of FICTIONAL Lesotho taxpayers, MNE groups,
VAT returns, refund claims, supporting invoices, supplier sales listings, related-party
transactions and annual financials, plus ground-truth labels for evaluation.

Usage:  python -m data_gen.generate            (from repo root)
Output: ./data/*.csv, ./data/ground_truth.csv, ./data/invoice_images/*.jpg
"""
from __future__ import annotations

import csv
import json
import random
import shutil
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .common import (
    HIGH_TAX_JURISDICTIONS,
    LOW_TAX_JURISDICTIONS,
    PENDING_PERIODS,
    PERIODS,
    SECTORS,
    VAT_RATE,
    make_tin,
)

SEED = 2026
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data"

ABUSIVE = {
    "abuse_unsupported", "abuse_phantom", "abuse_duplicate",
    "abuse_reverse_charge", "abuse_profit_shift", "abuse_low_margin", "demo_abuse",
}

SCENARIO_COUNTS = {
    "phantom_supplier": 15,
    "normal": 332,
    "incomplete_records": 8,  # legit exporters with missing / contradictory records
    "exporter": 25,
    "capital_newbiz": 12,
    "seasonal": 20,
    "mne_armslength": 22,
    "abuse_unsupported": 12,
    "abuse_phantom": 12,
    "abuse_duplicate": 10,
    "abuse_reverse_charge": 9,
    "abuse_profit_shift": 10,
    "abuse_low_margin": 10,
}

# ---------------------------------------------------------------- names (fictional)
NAME_A = [
    "Khotso", "Lesedi", "Pula", "Tsepo", "Mohlomi", "Qiloane", "Senqu", "Mohokare", "Thabana",
    "Lebese", "Mokhele", "Nthabeleng", "Rethabile", "Tumelo", "Kananelo", "Lineo", "Mpho",
    "Boitumelo", "Litsoeneng", "Ha-Ntsi", "Sefikeng", "Moholobela", "Liphofung", "Tlali",
    "Phofu", "Leribe Hills", "Botha Valley", "Sekoti", "Mantsonyane", "Makhaleng", "Koma",
    "Ntlafatso", "Kopano", "Seliba", "Thota", "Letlapa", "Mafube", "Leqhoa", "Morija Ridge",
    "Bokamoso", "Tshepiso", "Hlokomelo", "Maletsunyane", "Semonkong Peak", "Mokorotlo",
]
NAME_B = {
    "Wholesale - FMCG": ["Wholesalers", "Cash & Carry", "Distributors", "Trading", "Bulk Supplies"],
    "Retail - FMCG": ["Supermarket", "Mini-Market", "Stores", "Retailers", "Fresh Market"],
    "Manufacturing - Textiles": ["Garments", "Textile Mills", "Apparel", "Knitwear", "Denim Works"],
    "Agro-processing": ["Mills", "Agri Foods", "Dairy", "Poultry", "Agro-Processors"],
    "Construction": ["Builders", "Civils", "Construction", "Contractors", "Projects"],
    "Transport & Logistics": ["Logistics", "Haulage", "Freight", "Transport", "Couriers"],
    "Mining services": ["Mining Services", "Drilling", "Plant Hire", "Mine Supplies", "Engineering"],
    "Professional services": ["Consulting", "Advisory", "Associates", "Partners", "Solutions"],
}
SUFFIX = ["(Pty) Ltd", "(Pty) Ltd", "(Pty) Ltd", "Ltd", "& Sons (Pty) Ltd"]
FOREIGN_A = ["Aurelian", "Borealis", "Cobalt Ridge", "Dunmore", "Everline", "Fairhaven", "Granite Bay",
             "Halcyon", "Ivory Coast-line", "Juniper", "Kestrel", "Larkspur", "Meridian", "Northwind",
             "Oakmont", "Pinnacle", "Quayside", "Redstone", "Silverleaf", "Tidewater", "Umber",
             "Vantage", "Westbrook", "Xenith", "Yarrow", "Zephyr", "Albion Crest", "Brightwater",
             "Castellan", "Driftwood"]
TOWNS = ["Maseru", "Maputsoe", "Teyateyaneng", "Mafeteng", "Mohale's Hoek", "Leribe", "Butha-Buthe",
         "Quthing", "Qacha's Nek", "Mokhotlong", "Thaba-Tseka", "Roma"]

SIZE_MONTHLY_SALES = {"small": (60_000, 400_000), "medium": (400_000, 3_000_000), "large": (3_000_000, 18_000_000)}
SECTOR_MARGIN = {
    "Wholesale - FMCG": (0.12, 0.20), "Retail - FMCG": (0.20, 0.30),
    "Manufacturing - Textiles": (0.18, 0.30), "Agro-processing": (0.18, 0.28),
    "Construction": (0.15, 0.25), "Transport & Logistics": (0.25, 0.40),
    "Mining services": (0.22, 0.35), "Professional services": (0.45, 0.65),
}
FMCG_ITEMS = ["Maize meal 12.5kg", "Sugar 2kg", "Cooking oil 2L", "Rice 10kg", "Tea bags 100s",
              "Long-life milk 1L x12", "Bath soap x48", "Washing powder 2kg", "Canned beans x24",
              "Bread flour 10kg", "Candles x50", "Paraffin 20L", "Matches x100", "Salt 1kg x20"]
EQUIP_ITEMS = ["Cold room unit", "Forklift 2.5t", "Pallet racking (bay)", "Industrial generator",
               "Delivery truck 8t", "Warehouse shelving", "Refrigerated display", "POS system"]
GENERAL_ITEMS = ["Packaging material", "Raw fabric roll", "Diesel 1000L", "Cement 50kg x100",
                 "Spare parts", "Steel sections", "Office supplies", "Maintenance service"]


@dataclass
class Entity:
    tin: str
    name: str
    sector: str
    reg_date: date
    size_band: str
    scenario: str
    town: str
    group_id: int | None = None
    is_foreign: bool = False
    jurisdiction: str = "Lesotho"
    low_tax: bool = False
    role: str = ""  # parent / sister / hub / subsidiary
    # simulation parameters
    base_sales: float = 0.0
    margin: float = 0.2
    growth: float = 0.05
    zero_share: float = 0.0
    intensity: float = 1.0
    suppliers: list[str] = field(default_factory=list)
    inv_prefix: str = ""


def period_month(p: str) -> int:
    return int(p[5:7])


def period_start(p: str) -> date:
    return date(int(p[:4]), int(p[5:7]), 1)


def period_end(p: str) -> date:
    s = period_start(p)
    nxt = date(s.year + (s.month == 12), (s.month % 12) + 1, 1)
    return nxt - timedelta(days=1)


class Generator:
    def __init__(self, seed: int = SEED):
        self.rng = random.Random(seed)
        self.entities: list[Entity] = []
        self.by_tin: dict[str, Entity] = {}
        self.groups: list[dict] = []
        self.returns: list[dict] = []
        self.claims: list[dict] = []
        self.invoices: list[dict] = []
        self.listing: list[dict] = []
        self.rp_txns: list[dict] = []
        self.financials: list[dict] = []
        self.truth: list[dict] = []
        self.expat: list[dict] = []
        self._tin_seq = 1000
        self._used_names: set[str] = set()
        self._inv_seq: dict[str, int] = {}
        self._invoice_id = 0

    # ------------------------------------------------------------- helpers
    def new_tin(self) -> str:
        self._tin_seq += self.rng.randint(1, 37)
        return make_tin(self._tin_seq)

    def unique_name(self, sector: str) -> str:
        for _ in range(500):
            n = f"{self.rng.choice(NAME_A)} {self.rng.choice(NAME_B[sector])} {self.rng.choice(SUFFIX)}"
            if n not in self._used_names:
                self._used_names.add(n)
                return n
        raise RuntimeError("name space exhausted")

    def prefix_for(self, name: str) -> str:
        letters = "".join(w[0] for w in name.replace("(", "").split() if w[0].isalpha())[:3].upper()
        p = letters
        i = 2
        while p in self._inv_seq:
            p = f"{letters}{i}"
            i += 1
        self._inv_seq[p] = self.rng.randint(100, 4000)
        return p

    def add(self, e: Entity) -> Entity:
        if not e.is_foreign:
            e.inv_prefix = self.prefix_for(e.name)
        self.entities.append(e)
        self.by_tin[e.tin] = e
        return e

    def make_local(self, scenario: str, sector: str | None = None, size: str | None = None,
                   reg: date | None = None, name: str | None = None) -> Entity:
        r = self.rng
        if sector is None:
            if scenario in ("exporter",):
                sector = r.choice(["Manufacturing - Textiles", "Agro-processing", "Manufacturing - Textiles"])
            elif scenario == "incomplete_records":
                sector = r.choice(["Manufacturing - Textiles", "Agro-processing"])
            elif scenario in ("phantom_supplier",):
                sector = "Wholesale - FMCG"
            else:
                sector = r.choices(SECTORS, weights=[24, 22, 10, 8, 10, 8, 6, 12])[0]
        if size is None:
            size = r.choices(["small", "medium", "large"], weights=[55, 35, 10])[0]
            if scenario.startswith("abuse") or scenario in ("mne_armslength", "exporter"):
                size = r.choices(["small", "medium", "large"], weights=[15, 55, 30])[0]
        if reg is None:
            if scenario == "phantom_supplier":
                reg = date(2024, 6, 1) + timedelta(days=r.randint(0, 600))
            elif scenario == "capital_newbiz":
                reg = date(2025, 11, 1) + timedelta(days=r.randint(0, 200))
            else:
                reg = date(r.randint(2004, 2022), r.randint(1, 12), r.randint(1, 28))
        lo, hi = SIZE_MONTHLY_SALES[size]
        e = Entity(
            tin=self.new_tin(), name=name or self.unique_name(sector), sector=sector, reg_date=reg,
            size_band=size, scenario=scenario, town=r.choice(TOWNS),
        )
        e.base_sales = r.uniform(lo, hi)
        e.margin = r.uniform(*SECTOR_MARGIN[sector])
        e.growth = r.uniform(-0.02, 0.12)
        if sector in ("Wholesale - FMCG", "Retail - FMCG"):
            e.zero_share = r.uniform(0.0, 0.08)  # some basic foodstuffs zero-rated
        if scenario == "exporter":
            e.zero_share = r.uniform(0.70, 0.95)
        e.intensity = r.uniform(0.6, 1.4)
        if scenario == "incomplete_records":
            e.zero_share = r.uniform(0.6, 0.8)
            e.skip = set(r.sample(PERIODS[-9:-1], 2))  # two unfiled months in 2026
        if scenario == "abuse_low_margin":
            e.margin = r.uniform(-0.08, 0.02)
        if scenario == "abuse_profit_shift":
            e.margin = r.uniform(0.04, 0.10)
            e.growth = r.uniform(0.08, 0.18)
        return self.add(e)

    # ------------------------------------------------------------- build
    def build_entities(self):
        r = self.rng
        for scen, n in SCENARIO_COUNTS.items():
            for _ in range(n):
                self.make_local(scen)

        # --- demo taxpayers (fixed, memorable)
        self.demo1 = self.make_local("demo_exporter", sector="Manufacturing - Textiles", size="large",
                                     reg=date(2009, 3, 14), name="Maluti Highlands Knitwear Exporters (Pty) Ltd")
        self.demo1.zero_share = 0.88
        self.demo1.margin = 0.24
        self.demo1.base_sales = 6_500_000
        self.demo1.growth = 0.06
        self.demo2 = self.make_local("demo_newbiz", sector="Wholesale - FMCG", size="medium",
                                     reg=date(2026, 3, 2), name="Senqu Valley FMCG Distributors (Pty) Ltd")
        self.demo2.base_sales = 1_400_000
        self.demo2.margin = 0.15
        self.demo3 = self.make_local("demo_abuse", sector="Retail - FMCG", size="large",
                                     reg=date(2015, 6, 1), name="Thaba-Bosiu Retail Holdings (Lesotho) (Pty) Ltd")
        self.demo3.base_sales = 7_800_000
        self.demo3.margin = 0.08
        self.demo3.growth = 0.11

        # --- MNE groups
        group_members = (
            [e for e in self.entities if e.scenario in ("mne_armslength", "abuse_profit_shift",
                                                          "abuse_low_margin", "abuse_reverse_charge")]
        )
        r.shuffle(group_members)
        n_groups = 30
        for gid in range(1, n_groups + 1):
            fname = FOREIGN_A[gid - 1]
            parent = self.add(Entity(
                tin=f"FX-{100000 + gid * 37}", name=f"{fname} Holdings plc", sector="Holding company",
                reg_date=date(1990 + gid % 20, 1, 1), size_band="large", scenario="foreign_parent",
                town="-", group_id=gid, is_foreign=True, jurisdiction=r.choice(HIGH_TAX_JURISDICTIONS),
                role="parent"))
            g = {"group_id": gid, "name": f"{fname} Group", "parent_tin": parent.tin,
                 "sister_tin": None, "hub_tin": None}
            if r.random() < 0.75:
                sister = self.add(Entity(
                    tin=f"FX-{200000 + gid * 41}", name=f"{fname} Services International Ltd",
                    sector="Group services", reg_date=date(2005 + gid % 15, 6, 1), size_band="medium",
                    scenario="foreign_sister", town="-", group_id=gid, is_foreign=True,
                    jurisdiction=r.choice(LOW_TAX_JURISDICTIONS), low_tax=True, role="sister"))
                g["sister_tin"] = sister.tin
            if r.random() < 0.5:
                hub = self.add(Entity(
                    tin=f"FX-{300000 + gid * 43}", name=f"{fname} Trading Hub Ltd", sector="Procurement hub",
                    reg_date=date(2008 + gid % 12, 9, 1), size_band="large", scenario="foreign_hub",
                    town="-", group_id=gid, is_foreign=True, jurisdiction=r.choice(LOW_TAX_JURISDICTIONS),
                    low_tax=True, role="hub"))
                g["hub_tin"] = hub.tin
            self.groups.append(g)

        # profit-shift / low-margin abusers need low-tax sister / hub
        for i, e in enumerate(group_members):
            gid = (i % n_groups) + 1
            g = self.groups[gid - 1]
            if e.scenario in ("abuse_profit_shift",) and not g["sister_tin"]:
                g = next(gg for gg in self.groups if gg["sister_tin"])
            if e.scenario == "abuse_low_margin" and not (g["hub_tin"] or g["sister_tin"]):
                g = next(gg for gg in self.groups if gg["hub_tin"])
            e.group_id = g["group_id"]
            e.role = "subsidiary"
        # demo3 group: dedicated, with low-tax sister
        g3 = next(gg for gg in self.groups if gg["sister_tin"] and gg["hub_tin"])
        self.demo3.group_id = g3["group_id"]
        self.demo3.role = "subsidiary"
        self.demo3_group = g3

        # --- supplier pools
        normals = [e for e in self.entities if e.scenario == "normal"]
        goods_suppliers = [e for e in normals if e.sector in ("Wholesale - FMCG", "Agro-processing",
                                                               "Manufacturing - Textiles", "Transport & Logistics")]
        equip_suppliers = [e for e in normals if e.sector in ("Construction", "Mining services",
                                                              "Wholesale - FMCG") and e.reg_date.year < 2020]
        self.equip_suppliers = sorted(equip_suppliers, key=lambda s: -s.base_sales)[:10]
        self.phantoms = [e for e in self.entities if e.scenario == "phantom_supplier"]
        goods_suppliers.sort(key=lambda s: -s.base_sales)
        for e in self.entities:
            if e.is_foreign or e.scenario == "phantom_supplier":
                continue
            # a supplier must be big enough to plausibly sell this volume to the buyer
            pool = [s for s in goods_suppliers if s.tin != e.tin and s.base_sales >= 0.9 * e.base_sales]
            if len(pool) < 8:
                pool = [s for s in goods_suppliers[:15] if s.tin != e.tin]
            e.suppliers = [s.tin for s in r.sample(pool, k=r.randint(3, 6))]

    # ------------------------------------------------------------- related party
    def rp_profile(self, e: Entity) -> dict:
        """Annual related-party charges as share of turnover, by type and payee."""
        r = self.rng
        if e.group_id is None:
            return {}
        g = self.groups[e.group_id - 1]
        prof: dict[tuple[str, str], float] = {}
        if e.scenario == "mne_armslength":
            prof[("management fee", g["parent_tin"])] = r.uniform(0.008, 0.02)
            prof[("royalty", g["parent_tin"])] = r.uniform(0.004, 0.012)
            prof[("goods", g["parent_tin"])] = r.uniform(0.10, 0.25)
            if g["sister_tin"] and r.random() < 0.5:
                prof[("service fee", g["sister_tin"])] = r.uniform(0.002, 0.006)
        elif e.scenario == "abuse_profit_shift":
            prof[("management fee", g["sister_tin"])] = r.uniform(0.06, 0.11)
            prof[("royalty", g["sister_tin"])] = r.uniform(0.03, 0.07)
            prof[("interest", g["sister_tin"])] = r.uniform(0.01, 0.03)
        elif e.scenario == "abuse_low_margin":
            payee = g["hub_tin"] or g["sister_tin"]
            prof[("goods", payee)] = r.uniform(0.60, 0.80)
            prof[("management fee", g["parent_tin"])] = r.uniform(0.005, 0.015)
        elif e.scenario == "abuse_reverse_charge":
            payee = g["sister_tin"] or g["parent_tin"]
            prof[("service fee", payee)] = r.uniform(0.03, 0.06)
            prof[("management fee", g["parent_tin"])] = r.uniform(0.01, 0.02)
        elif e.scenario == "demo_abuse":
            prof[("management fee", g["sister_tin"])] = 0.092
            prof[("royalty", g["sister_tin"])] = 0.061
            prof[("interest", g["sister_tin"])] = 0.018
            prof[("goods", g["hub_tin"])] = 0.42
        return prof

    # ------------------------------------------------------------- simulation
    def simulate(self):
        r = self.rng
        self.rp = {e.tin: self.rp_profile(e) for e in self.entities if not e.is_foreign}
        prior_invoices: dict[str, list[dict]] = {}

        for e in self.entities:
            if e.is_foreign:
                continue
            refund_months = 0
            for i, p in enumerate(PERIODS):
                if p in getattr(e, "skip", ()):
                    continue  # return not filed
                if period_end(p) < e.reg_date:
                    continue
                m = period_month(p)
                months_active = (period_start(p).year - e.reg_date.year) * 12 + period_start(p).month - e.reg_date.month
                if e.scenario == "phantom_supplier":
                    filed = r.random() < 0.6
                    if filed:
                        self.returns.append(self._ret(e, p, 0.0, r.uniform(0, 3000), r.uniform(0, 2000), 0, 0, 0, 0, 0))
                    continue

                sales = e.base_sales * (1 + e.growth) ** (i / 12) * r.uniform(0.9, 1.1)
                if e.sector in ("Wholesale - FMCG", "Retail - FMCG"):
                    sales *= {12: 1.55, 11: 1.15, 1: 0.8}.get(m, 1.0)
                if e.scenario in ("capital_newbiz", "demo_newbiz"):
                    ramp = min(1.0, 0.25 + 0.15 * max(months_active, 0))
                    sales *= ramp
                zero = sales * e.zero_share
                std_sales = sales - zero
                cogs = sales * (1 - e.margin)
                purchases = cogs
                # stock behaviour
                if e.scenario == "seasonal" or (e.scenario == "normal" and e.sector == "Wholesale - FMCG" and e.intensity > 1.25):
                    purchases *= {9: 1.9, 10: 2.1, 12: 0.55, 1: 0.6}.get(m, 1.0)
                elif r.random() < 0.06:
                    purchases *= r.uniform(1.6, 2.4)
                if e.scenario == "abuse_profit_shift" and r.random() < 0.45:
                    purchases *= r.uniform(1.3, 1.8)
                opex = sales * r.uniform(0.03, 0.07)
                capital = 0.0
                if e.scenario == "capital_newbiz" and months_active == 1:
                    capital = r.uniform(2_500_000, 9_000_000)
                if e.scenario == "demo_newbiz" and p == PERIODS[-1]:
                    capital = 9_240_000.0
                if e.scenario in ("normal", "mne_armslength", "exporter") and r.random() < 0.015:
                    capital = sales * r.uniform(0.5, 2.0)
                taxable_purch = purchases * r.uniform(0.82, 0.95) + opex

                # related party services (imported) for this month
                prof = self.rp.get(e.tin, {})
                services = sum(v for (t, _), v in prof.items() if t in ("management fee", "royalty", "service fee")) * sales
                rc_declared = services * VAT_RATE
                if e.scenario == "abuse_reverse_charge":
                    rc_declared = 0.0 if r.random() < 0.92 else services * VAT_RATE * 0.3
                # imported services declared value
                imp_declared = services if rc_declared > 0 else 0.0

                output_vat = std_sales * VAT_RATE
                input_actual = taxable_purch * VAT_RATE + capital * VAT_RATE
                # abuse levers on the claim
                inflate = 0.0
                if e.scenario == "abuse_unsupported":
                    inflate = input_actual * r.uniform(0.25, 0.9) * e.intensity
                if e.scenario in ("abuse_unsupported", "abuse_phantom", "abuse_duplicate", "demo_abuse"):
                    # push them into refund most months
                    force = (p != PERIODS[-7]) if e.scenario == "demo_abuse" else r.random() < 0.85
                    if output_vat - input_actual - inflate > 0 and force:
                        input_actual += (output_vat - input_actual) * r.uniform(1.05, 1.4)
                input_claimed = input_actual + inflate
                net = output_vat - input_claimed
                refund = max(0.0, -net)
                ret = self._ret(e, p, std_sales, zero, output_vat, input_claimed, capital, imp_declared,
                                rc_declared, refund)
                self.returns.append(ret)
                if refund <= 0:
                    continue
                refund_months += 1

                # ---- this is a refund claim: build supporting invoices
                claim_id = len(self.claims) + 1
                status = "pending" if p in PENDING_PERIODS else self.rng.choices(
                    ["approved", "approved", "approved", "adjusted"], weights=[80, 5, 5, 10])[0]
                if p not in PENDING_PERIODS and e.scenario in ABUSIVE and r.random() < 0.15:
                    status = "adjusted"
                self.claims.append({
                    "claim_id": claim_id, "tin": e.tin, "period": p, "refund_claimed": round(refund, 2),
                    "input_vat_claimed": round(input_claimed, 2), "submitted_on": (period_end(p) + timedelta(days=r.randint(5, 20))).isoformat(),
                    "status": status,
                })
                acts: list[str] = []
                invs: list[dict] = []
                # supported (genuine) input VAT split into invoices
                genuine_vat = input_actual - capital * VAT_RATE
                k = max(2, min(12, int(genuine_vat / 60_000) + r.randint(1, 3)))
                weights = [r.uniform(0.5, 1.5) for _ in range(k)]
                tw = sum(weights)
                for w in weights:
                    sup = self.by_tin[r.choice(e.suppliers)]
                    invs.append(self._invoice(sup, e, p, genuine_vat * w / tw, claim_id, kind="goods"))
                if capital > 0:
                    sup = r.choice(self.equip_suppliers)
                    nparts = 3 if capital > 3_000_000 else 1
                    cw = [r.uniform(0.6, 1.4) for _ in range(nparts)]
                    for w in cw:
                        invs.append(self._invoice(sup, e, p, capital * VAT_RATE * w / sum(cw), claim_id, kind="equipment"))
                # supplier listing noise for legit taxpayers (late filing)
                late_listing = (e.scenario not in ABUSIVE and not e.scenario.startswith("demo")
                                and r.random() < 0.06)
                for inv in invs:
                    if late_listing and r.random() < 0.3:
                        inv["_listed"] = False

                if e.scenario in ("abuse_unsupported",) and inflate > 0:
                    acts.append("input VAT claimed without invoices")
                if e.scenario in ("abuse_phantom",) or (e.scenario == "demo_abuse"):
                    share = r.uniform(0.15, 0.6) * (e.intensity if e.scenario != "demo_abuse" else 1.0)
                    if e.scenario == "demo_abuse" and p == PERIODS[-1]:
                        share = 0.38
                    live_phantoms = [x for x in self.phantoms if x.reg_date <= period_start(p)]
                    if live_phantoms and (r.random() < 0.85 or e.scenario == "demo_abuse"):
                        ph = r.choice(live_phantoms)
                        if e.scenario == "demo_abuse":
                            ph = min(live_phantoms, key=lambda x: x.reg_date)
                        phantom_vat = genuine_vat * share
                        n_ph = max(1, int(phantom_vat / 120_000))
                        pw = [r.uniform(0.6, 1.4) for _ in range(n_ph)]
                        for w in pw:
                            pinv = self._invoice(ph, e, p, phantom_vat * w / sum(pw), claim_id, kind="goods")
                            pinv["_listed"] = False
                            pinv["_truth"] = "phantom"
                            invs.append(pinv)
                        self.claims[-1]["input_vat_claimed"] = round(input_claimed + phantom_vat, 2)
                        self.claims[-1]["refund_claimed"] = round(refund + phantom_vat, 2)
                        acts.append("phantom supplier invoices")
                if e.scenario in ("abuse_duplicate", "demo_abuse") and prior_invoices.get(e.tin):
                    if r.random() < 0.75 or e.scenario == "demo_abuse":
                        pool = prior_invoices[e.tin]
                        ndup = 1 if e.scenario == "demo_abuse" else r.randint(1, 3)
                        dup_vat = 0.0
                        for src in r.sample(pool, k=min(ndup, len(pool))):
                            d = dict(src)
                            self._invoice_id += 1
                            d["invoice_id"] = self._invoice_id
                            d["claim_id"] = claim_id
                            d["period_claimed"] = p
                            d["_dup_of"] = src["invoice_id"]
                            d["_truth"] = "duplicate"
                            d["_listed"] = False  # listing row already exists for the original
                            if e.scenario == "demo_abuse":
                                # re-photographed copy with an edited invoice number
                                d["invoice_no"] = src["invoice_no"][:-1] + str((int(src["invoice_no"][-1]) + 3) % 10)
                                d["_altered_no"] = True
                            invs.append(d)
                            dup_vat += d["vat"]
                        self.claims[-1]["input_vat_claimed"] = round(self.claims[-1]["input_vat_claimed"] + dup_vat, 2)
                        self.claims[-1]["refund_claimed"] = round(self.claims[-1]["refund_claimed"] + dup_vat, 2)
                        acts.append("duplicate invoices")
                if e.scenario == "abuse_reverse_charge":
                    acts.append("reverse-charge VAT not declared on related-party imported services")
                if e.scenario == "abuse_profit_shift":
                    acts.append("profit shifting via related-party fees to low-tax entity")
                if e.scenario == "abuse_low_margin":
                    acts.append("transfer mispricing: intra-group purchases erode margin")
                if e.scenario == "demo_abuse":
                    acts.append("profit shifting via related-party fees to low-tax entity")

                self.invoices.extend(invs)
                prior_invoices.setdefault(e.tin, []).extend(
                    [iv for iv in invs if iv.get("_truth") is None])
                self.truth.append({
                    "claim_id": claim_id, "tin": e.tin, "period": p, "scenario": e.scenario,
                    "abusive": int(bool(acts)), "abuse_acts": "; ".join(acts),
                })

        # supplier sales listings (what suppliers actually declared, invoice-level)
        for inv in self.invoices:
            if inv.get("_listed", True):
                self.listing.append({
                    "supplier_tin": inv["supplier_tin"], "invoice_no": inv["invoice_no"],
                    "buyer_tin": inv["buyer_tin"], "invoice_date": inv["invoice_date"],
                    "period": inv["invoice_date"][:7], "vat": inv["vat"],
                })

    def _ret(self, e, p, std, zero, out, inp, cap, imp, rc, refund):
        return {
            "tin": e.tin, "period": p, "standard_sales": round(std, 2), "zero_rated_sales": round(zero, 2),
            "output_vat": round(out, 2), "input_vat": round(inp, 2), "capital_purchases": round(cap, 2),
            "imported_services": round(imp, 2), "reverse_charge_vat": round(rc, 2),
            "net_vat": round(out - inp, 2), "refund_claimed": round(refund, 2),
            "filed_on": (period_end(p) + timedelta(days=self.rng.randint(5, 20))).isoformat(),
        }

    def _invoice(self, sup: Entity, buyer: Entity, p: str, vat: float, claim_id: int, kind: str) -> dict:
        r = self.rng
        self._invoice_id += 1
        self._inv_seq[sup.inv_prefix] += r.randint(1, 9)
        start = period_start(p)
        d = start + timedelta(days=r.randint(0, (period_end(p) - start).days))
        vat = round(vat, 2)
        net = round(vat / VAT_RATE, 2)
        return {
            "invoice_id": self._invoice_id, "claim_id": claim_id, "supplier_tin": sup.tin,
            "buyer_tin": buyer.tin, "invoice_no": f"{sup.inv_prefix}-{self._inv_seq[sup.inv_prefix]:05d}",
            "invoice_date": d.isoformat(), "period_claimed": p, "net": net, "vat": vat,
            "total": round(net + vat, 2), "currency": "LSL", "kind": kind,
        }

    # ------------------------------------------------------------- financials & RP txns
    def build_financials(self):
        r = self.rng
        rets_by_tin: dict[str, list[dict]] = {}
        for rt in self.returns:
            rets_by_tin.setdefault(rt["tin"], []).append(rt)
        for e in self.entities:
            if e.is_foreign or e.scenario == "phantom_supplier":
                continue
            rets = rets_by_tin.get(e.tin, [])
            t2026 = sum(x["standard_sales"] + x["zero_rated_sales"] for x in rets if x["period"] >= "2025-11") or e.base_sales * 12
            losses_cf = 0.0
            opex_ratio = r.uniform(0.07, 0.14)
            if e.scenario in ("abuse_profit_shift", "demo_abuse"):
                opex_ratio = r.uniform(0.04, 0.06)
            for year in range(2021, 2027):
                if e.scenario == "incomplete_records" and year == 2026:
                    continue  # latest financial statements not submitted
                if year < e.reg_date.year:
                    continue
                turnover = t2026 / (1 + e.growth) ** (2026 - year) * r.uniform(0.95, 1.05)
                if e.reg_date.year == year:
                    turnover *= max(0.15, (12 - e.reg_date.month) / 12)
                if e.scenario == "incomplete_records" and year == 2025:
                    turnover *= 0.55  # contradicts turnover declared in VAT returns
                margin = e.margin + r.uniform(-0.02, 0.02)
                prof = self.rp.get(e.tin, {})
                rp_charges = sum(v for (t, _), v in prof.items() if t != "goods") * turnover
                gp = turnover * margin
                np_ = gp - turnover * opex_ratio - rp_charges
                if e.scenario == "normal" and r.random() < 0.08:
                    np_ = -abs(np_) * r.uniform(0.2, 0.8)
                if e.scenario in ("capital_newbiz", "demo_newbiz"):
                    np_ = -turnover * r.uniform(0.05, 0.2)
                losses_cf = max(0.0, losses_cf - np_) if np_ > 0 else losses_cf + (-np_)
                self.financials.append({
                    "tin": e.tin, "year": year, "turnover": round(turnover, 2), "gross_margin": round(margin, 4),
                    "gross_profit": round(gp, 2), "net_profit": round(np_, 2),
                    "losses_carried_forward": round(losses_cf, 2),
                })
                for (t, payee), share in prof.items():
                    amt = share * turnover * r.uniform(0.9, 1.1)
                    self.rp_txns.append({"payer_tin": e.tin, "payee_tin": payee, "year": year, "type": t,
                                         "amount": round(amt, 2)})

        # a few expat engagements (stretch module data)
        locals_ = [e for e in self.entities if e.group_id and not e.is_foreign]
        for i in range(40):
            e = r.choice(locals_)
            g = self.groups[e.group_id - 1]
            consult = r.random() < 0.4
            self.expat.append({
                "person_ref": f"EXP-{i + 1:03d}", "engaging_tin": e.tin,
                "paying_tin": g["sister_tin"] or g["parent_tin"] if consult else e.tin,
                "months": r.randint(3, 48), "reports_to_local_mgmt": int(r.random() < (0.85 if consult else 0.9)),
                "fixed_hours": int(r.random() < 0.8), "uses_company_tools": int(r.random() < 0.85),
                "declared_as": "consultancy" if consult else "employment",
            })

    # ------------------------------------------------------------- write
    def write(self):
        if OUT.exists():
            for f in OUT.glob("*.csv"):
                f.unlink()
        OUT.mkdir(parents=True, exist_ok=True)

        def dump(name, rows, cols):
            with open(OUT / name, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)

        tax_rows = [{
            "tin": e.tin, "name": e.name, "sector": e.sector, "registration_date": e.reg_date.isoformat(),
            "size_band": e.size_band, "group_id": e.group_id or "", "is_foreign": int(e.is_foreign),
            "jurisdiction": e.jurisdiction, "low_tax": int(e.low_tax), "role": e.role, "town": e.town,
        } for e in self.entities]
        dump("taxpayers.csv", tax_rows, list(tax_rows[0].keys()))
        dump("groups.csv", self.groups, ["group_id", "name", "parent_tin", "sister_tin", "hub_tin"])
        dump("vat_returns.csv", self.returns, list(self.returns[0].keys()))
        dump("claims.csv", self.claims, list(self.claims[0].keys()))
        inv_cols = ["invoice_id", "claim_id", "supplier_tin", "buyer_tin", "invoice_no", "invoice_date",
                    "period_claimed", "net", "vat", "total", "currency", "kind", "image_file"]
        dump("invoices.csv", self.invoices, inv_cols)
        dump("supplier_listings.csv", self.listing, list(self.listing[0].keys()))
        dump("related_party_txns.csv", self.rp_txns, ["payer_tin", "payee_tin", "year", "type", "amount"])
        dump("financials.csv", self.financials, list(self.financials[0].keys()))
        dump("expat_engagements.csv", self.expat, list(self.expat[0].keys()))
        # ground truth - for EVALUATION ONLY, never loaded into the officer-facing app
        dump("ground_truth.csv", self.truth, ["claim_id", "tin", "period", "scenario", "abusive", "abuse_acts"])
        inv_truth = [{"invoice_id": iv["invoice_id"], "truth": iv.get("_truth", "genuine"),
                      "dup_of": iv.get("_dup_of", ""), "altered_no": int(iv.get("_altered_no", False))}
                     for iv in self.invoices]
        dump("ground_truth_invoices.csv", inv_truth, ["invoice_id", "truth", "dup_of", "altered_no"])
        demo = {
            "ordinary_fast_track": self.demo1.tin,
            "exception_capital": self.demo2.tin,
            "human_review_abuse": self.demo3.tin,
        }
        (OUT / "demo_cases.json").write_text(json.dumps(demo, indent=2))

    def summary(self):
        n_abusive = sum(t["abusive"] for t in self.truth)
        print(f"taxpayers (local)   : {sum(not e.is_foreign for e in self.entities)}")
        print(f"foreign group cos   : {sum(e.is_foreign for e in self.entities)}")
        print(f"groups              : {len(self.groups)}")
        print(f"vat returns         : {len(self.returns)}")
        print(f"refund claims       : {len(self.claims)}  (abusive: {n_abusive})")
        print(f"invoices            : {len(self.invoices)}")
        print(f"supplier listings   : {len(self.listing)}")
        print(f"related-party txns  : {len(self.rp_txns)}")


def main():
    from .invoice_images import render_images

    gen = Generator()
    gen.build_entities()
    gen.simulate()
    gen.build_financials()
    img_dir = OUT / "invoice_images"
    if img_dir.exists():
        shutil.rmtree(img_dir)
    render_images(gen, img_dir)
    gen.write()
    gen.summary()


if __name__ == "__main__":
    main()
