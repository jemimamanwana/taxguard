"""Feature engineering for refund claims (one row per claim)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import VAT_RATES

VAT = VAT_RATES["standard"]
SERVICE_TYPES = {"management fee", "royalty", "service fee"}


def _robust_z(x: pd.Series, groups: pd.Series) -> pd.Series:
    med = x.groupby(groups).transform("median")
    mad = (x - med).abs().groupby(groups).transform("median") * 1.4826
    return (x - med) / mad.clip(lower=0.05)


def invoice_frame(store) -> pd.DataFrame:
    inv = store.invoices.copy()
    checks = store.invoice_checks
    inv = inv.merge(checks, on="invoice_id", how="left")
    for c in ("nomatch", "nolist", "dup", "risky_supplier"):
        inv[c] = inv[c].fillna(False).astype(bool)
    return inv


def build_features(store) -> pd.DataFrame:
    R = store.returns.sort_values(["tin", "period"]).copy()
    R["refund_flag"] = (R["refund_claimed"] > 0).astype(int)
    R["refund_pos"] = -R["net_vat"]
    g = R.groupby("tin", group_keys=False)
    R["refund_months_12"] = g["refund_flag"].transform(lambda s: s.rolling(12, min_periods=1).sum())
    R["months_12"] = g["refund_flag"].transform(lambda s: s.rolling(12, min_periods=1).count())
    R["in_12"] = g["input_vat"].transform(lambda s: s.rolling(12, min_periods=1).sum())
    R["out_12"] = g["output_vat"].transform(lambda s: s.rolling(12, min_periods=1).sum())
    R["sales_12"] = g["total_sales"].transform(lambda s: s.rolling(12, min_periods=1).sum())
    R["zero_12"] = g["zero_rated_sales"].transform(lambda s: s.rolling(12, min_periods=1).sum())
    R["rc_12"] = g["reverse_charge_vat"].transform(lambda s: s.rolling(12, min_periods=1).sum())
    prior_mean = g["refund_pos"].transform(lambda s: s.shift(1).rolling(12, min_periods=4).mean())
    prior_std = g["refund_pos"].transform(lambda s: s.shift(1).rolling(12, min_periods=4).std())
    floor = np.maximum(prior_mean.abs() * 0.25, 10_000)
    R["refund_z"] = (R["refund_pos"] - prior_mean) / np.maximum(prior_std.fillna(0), floor)
    R["prior_mean_pos"] = prior_mean
    # seasonal: refund in the same calendar month (+/-1) one year earlier
    R["month"] = R["period"].str[5:7].astype(int)
    R["year"] = R["period"].str[:4].astype(int)
    key = R.set_index(["tin", "period"])["refund_flag"].to_dict()

    def last_year_refund(row):
        y, m = row.year - 1, row.month
        hits = 0
        for dm in (-1, 0, 1):
            mm = m + dm
            yy = y + (mm < 1) - (mm > 12)
            mm = (mm - 1) % 12 + 1
            hits += key.get((row.tin, f"{yy}-{mm:02d}"), 0)
        return hits

    tp = store.taxpayers
    R = R.merge(tp[["tin", "sector", "registration_date", "group_id"]].reset_index(drop=True), on="tin", how="left")
    R["io_log"] = np.log((R["in_12"] + 1) / (R["out_12"] + 1))
    R["io_peer_z"] = _robust_z(R["io_log"], R["sector"] + "|" + R["period"])

    C = store.claims.merge(R, on=["tin", "period"], how="left", suffixes=("", "_ret"))
    C["seasonal_hits"] = C.apply(last_year_refund, axis=1)
    C["zero_share"] = (C["zero_rated_sales"] / C["total_sales"].replace(0, np.nan)).fillna(0)
    C["zero_share_12"] = (C["zero_12"] / C["sales_12"].replace(0, np.nan)).fillna(0)
    C["capital_vat"] = C["capital_purchases"] * VAT
    C["capital_share"] = (C["capital_vat"] / C["input_vat_claimed"].replace(0, np.nan)).fillna(0)
    C["refund_to_sales"] = C["refund_claimed"] / (C["total_sales"] + 1)
    reg = pd.to_datetime(C["registration_date"])
    C["years_registered"] = (pd.to_datetime(C["period"] + "-28") - reg).dt.days / 365.25

    # ---- invoice evidence
    inv = invoice_frame(store)
    inv["vat_nomatch"] = inv["vat"] * inv["nomatch"]
    inv["vat_nolist"] = inv["vat"] * inv["nolist"]
    inv["vat_dup"] = inv["vat"] * inv["dup"]
    inv["vat_risky"] = inv["vat"] * inv["risky_supplier"]
    agg = inv.groupby("claim_id").agg(
        inv_count=("invoice_id", "size"), inv_vat=("vat", "sum"), vat_nomatch=("vat_nomatch", "sum"),
        vat_nolist=("vat_nolist", "sum"), vat_dup=("vat_dup", "sum"), dup_count=("dup", "sum"),
        nomatch_count=("nomatch", "sum"), vat_risky=("vat_risky", "sum"),
    )
    C = C.merge(agg, left_on="claim_id", right_index=True, how="left")
    for c in agg.columns:
        C[c] = C[c].fillna(0)
    C["support_gap"] = ((C["input_vat_claimed"] - C["inv_vat"]) / C["input_vat_claimed"].replace(0, np.nan)).clip(lower=0).fillna(0)
    denom = C["inv_vat"].replace(0, np.nan)
    C["nomatch_share"] = (C["vat_nomatch"] / denom).fillna(0)
    C["nolist_share"] = (C["vat_nolist"] / denom).fillna(0)
    C["risky_share"] = (C["vat_risky"] / denom).fillna(0)

    # ---- group / related-party / financial features (by tin & year)
    fin = store.fin.sort_values(["tin", "year"]).copy()
    fin["loss"] = (fin["net_profit"] < 0).astype(int)

    def loss_run(s):
        out, run = [], 0
        for v in s:
            run = run + 1 if v else 0
            out.append(run)
        return out

    fin["loss_run"] = fin.groupby("tin")["loss"].transform(lambda s: pd.Series(loss_run(s), index=s.index))
    first_turn = fin.groupby("tin")["turnover"].transform("first")
    fin["turnover_growth"] = fin["turnover"] / first_turn.replace(0, np.nan) - 1
    sector = tp["sector"]
    fin["sector"] = fin["tin"].map(sector)
    fin["sector_margin"] = fin.groupby(["sector", "year"])["gross_margin"].transform("median")

    rp = store.rp.copy()
    rp["payee_low_tax"] = rp["payee_tin"].map(tp["low_tax"]).fillna(False).astype(bool)
    rp["service"] = rp["type"].isin(SERVICE_TYPES)
    lowtax_nongoods = rp[(rp["type"] != "goods") & rp["payee_low_tax"]].groupby(["payer_tin", "year"])["amount"].sum()
    services = rp[rp["service"]].groupby(["payer_tin", "year"])["amount"].sum()
    goods = rp[rp["type"] == "goods"].groupby(["payer_tin", "year"])["amount"].sum()
    interest = rp[rp["type"] == "interest"].groupby(["payer_tin", "year"])["amount"].sum()
    fin = fin.set_index(["tin", "year"])
    fin["rp_lowtax"] = lowtax_nongoods.reindex(fin.index).fillna(0)
    fin["rp_services"] = services.reindex(fin.index).fillna(0)
    fin["rp_goods"] = goods.reindex(fin.index).fillna(0)
    fin["rp_interest"] = interest.reindex(fin.index).fillna(0)
    fin = fin.reset_index()
    fin["rp_lowtax_share"] = fin["rp_lowtax"] / fin["turnover"].replace(0, np.nan)
    purchases = fin["turnover"] * (1 - fin["gross_margin"]).clip(lower=0.05)
    fin["rp_goods_share"] = fin["rp_goods"] / purchases
    fin["rp_interest_share"] = fin["rp_interest"] / fin["turnover"].replace(0, np.nan)
    # contradiction check: calendar-year sales in VAT returns vs financial-statement turnover
    full = R.groupby(["tin", "year"]).agg(ret_sales=("total_sales", "sum"), ret_months=("period", "size"))
    fin = fin.merge(full, left_on=["tin", "year"], right_index=True, how="left")
    ok = fin["ret_months"] == 12
    fin["turnover_mismatch"] = np.where(ok, (fin["ret_sales"] - fin["turnover"]).abs() / fin["ret_sales"].replace(0, np.nan), np.nan)
    worst = fin.groupby("tin")["turnover_mismatch"].max()
    worst_year = fin.loc[fin["turnover_mismatch"].fillna(-1).groupby(fin["tin"]).idxmax()].set_index("tin")["year"]
    fin_cols = ["tin", "year", "turnover", "gross_margin", "net_profit", "losses_carried_forward", "loss_run",
                "turnover_growth", "sector_margin", "rp_lowtax_share", "rp_goods_share", "rp_services", "rp_interest_share"]
    C = C.merge(fin[fin_cols].rename(columns={"year": "fin_year"}), left_on=["tin", "year"],
                right_on=["tin", "fin_year"], how="left")
    C["rc_expected_12"] = C["rp_services"].fillna(0) * VAT * C["months_12"].clip(upper=12) / 12
    C["rc_declared_ratio"] = (C["rc_12"] / C["rc_expected_12"].replace(0, np.nan)).fillna(1.0)
    C["margin_gap"] = (C["sector_margin"] - C["gross_margin"]).fillna(0)
    # ---- data completeness (labelled explicitly, never silently scored)
    C["has_fin"] = C["fin_year"].notna()
    C["turnover_mismatch"] = C["tin"].map(worst)
    C["turnover_mismatch_year"] = C["tin"].map(worst_year)
    filed = set(zip(store.returns.tin, store.returns.period))
    allp = sorted(store.returns["period"].unique())
    pos = {pp: i for i, pp in enumerate(allp)}

    def filing(row):
        i = pos.get(row.period)
        if i is None:
            return 0, 0, []
        window = allp[max(0, i - 11): i + 1]
        reg = str(row.registration_date)[:7]
        exp = [w for w in window if w >= reg]
        missing = [w for w in exp if (row.tin, w) not in filed]
        return len(exp) - len(missing), len(exp), missing

    fl = C.apply(filing, axis=1, result_type="expand")
    C["months_filed_12"], C["months_expected_12"], C["missing_periods"] = fl[0], fl[1], fl[2]
    return C.set_index("claim_id", drop=False)


ANOMALY_FEATURES = {
    "refund_to_sales": "Refund relative to the month's sales",
    "io_peer_z": "Input/output VAT ratio vs sector peers (robust z)",
    "refund_months_12": "Refund months in last 12",
    "refund_z": "Refund vs own history (z-score)",
    "zero_share": "Share of zero-rated sales",
    "capital_share": "Share of input VAT on capital assets",
    "log_refund": "Size of refund (log)",
}


def anomaly_matrix(C: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame(index=C.index)
    X["refund_to_sales"] = C["refund_to_sales"].clip(upper=5)
    X["io_peer_z"] = C["io_peer_z"].clip(-10, 10)
    X["refund_months_12"] = C["refund_months_12"]
    X["refund_z"] = C["refund_z"].fillna(0).clip(-10, 20)
    X["zero_share"] = C["zero_share"]
    X["capital_share"] = C["capital_share"]
    X["log_refund"] = np.log1p(C["refund_claimed"])
    return X.fillna(0)
