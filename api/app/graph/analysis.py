"""Related-party graph: nodes/edges for an MNE group, with suspicious paths highlighted."""
from __future__ import annotations

import math

import networkx as nx
import pandas as pd

SERVICE = {"management fee", "royalty", "service fee", "interest"}


def _f(x, d=0.0):
    try:
        v = float(x)
        return d if math.isnan(v) else v
    except (TypeError, ValueError):
        return d


def entity_profile(store, tin: str, year: int | None = None) -> dict:
    tp = store.taxpayers.loc[tin]
    fin = store.fin[store.fin.tin == tin].sort_values("year")
    prof = {"tin": tin, "name": tp["name"], "jurisdiction": tp["jurisdiction"], "low_tax": bool(tp["low_tax"]),
            "is_foreign": bool(tp["is_foreign"]), "sector": tp["sector"], "role": tp["role"]}
    if fin.empty:
        return prof
    last = fin.iloc[-1] if year is None else fin[fin.year == year].iloc[-1]
    sector_margin = store.fin[(store.fin.year == last.year) & store.fin.tin.map(store.taxpayers["sector"]).eq(tp["sector"])]["gross_margin"].median()
    rp = store.rp[(store.rp.payer_tin == tin) & (store.rp.year == last.year)]
    low = rp["payee_tin"].map(store.taxpayers["low_tax"]).fillna(False).astype(bool)
    loss_years = 0
    for v in reversed(fin["net_profit"].tolist()):
        if v < 0:
            loss_years += 1
        else:
            break
    prof.update({
        "year": int(last.year), "turnover": round(_f(last.turnover)), "gross_margin": round(_f(last.gross_margin), 4),
        "sector_margin": round(_f(sector_margin), 4), "net_profit": round(_f(last.net_profit)),
        "losses_carried_forward": round(_f(last.losses_carried_forward)), "consecutive_loss_years": loss_years,
        "rp_charges": round(float(rp[rp.type != "goods"]["amount"].sum())),
        "rp_charges_pct": round(float(rp[rp.type != "goods"]["amount"].sum()) / max(_f(last.turnover), 1), 4),
        "rp_lowtax_pct": round(float(rp[(rp.type != "goods") & low]["amount"].sum()) / max(_f(last.turnover), 1), 4),
        "rp_goods_pct_of_purchases": round(float(rp[rp.type == "goods"]["amount"].sum()) / max(_f(last.turnover) * (1 - _f(last.gross_margin)), 1), 3),
        "history": fin[["year", "turnover", "gross_margin", "net_profit", "losses_carried_forward"]].round(2).to_dict(orient="records"),
    })
    return prof


def group_graph(store, gid: int, year: int = 2026) -> dict:
    tp = store.taxpayers
    members = tp[tp.group_id == gid]
    G = nx.DiGraph()
    for t in members.itertuples():
        G.add_node(t.tin, name=t.name, jurisdiction=t.jurisdiction, low_tax=bool(t.low_tax),
                   foreign=bool(t.is_foreign), role=t.role or "subsidiary")
    rp = store.rp[(store.rp.year == year) & store.rp.payer_tin.isin(members.tin)]
    agg = rp.groupby(["payer_tin", "payee_tin", "type"])["amount"].sum().reset_index()
    for e in agg.itertuples():
        if e.payer_tin not in G:
            continue
        if G.has_edge(e.payer_tin, e.payee_tin):
            G[e.payer_tin][e.payee_tin]["types"][e.type] = float(e.amount)
        else:
            G.add_edge(e.payer_tin, e.payee_tin, types={e.type: float(e.amount)})

    findings, hot_edges, hot_nodes = [], set(), set()
    profiles = {}
    for t in members[~members.is_foreign.astype(bool)].tin:
        p = entity_profile(store, t)
        profiles[t] = p
        if "turnover" not in p:
            continue
        lowtax_targets = [n for n in G.successors(t) if G.nodes[n]["low_tax"]]
        if p["rp_lowtax_pct"] > 0.05:
            for n in lowtax_targets:
                hot_edges.add((t, n))
            hot_nodes.add(t)
            findings.append({"code": "R09", "tin": t, "severity": "high" if p["rp_lowtax_pct"] > 0.1 else "medium",
                             "text": f"{p['name']} pays {p['rp_lowtax_pct']:.1%} of turnover in fees/royalties/interest to low-tax group entities."})
        if p["consecutive_loss_years"] >= 4 and p["history"][-1]["turnover"] > p["history"][0]["turnover"]:
            hot_nodes.add(t)
            findings.append({"code": "R10", "tin": t, "severity": "high",
                             "text": f"{p['name']} reported losses for {p['consecutive_loss_years']} consecutive years while turnover grew "
                                     f"(losses carried forward M {p['losses_carried_forward']:,.0f})."})
        if p["sector_margin"] - p["gross_margin"] > 0.08 and p["rp_goods_pct_of_purchases"] > 0.4:
            for n in G.successors(t):
                if "goods" in G[t][n]["types"]:
                    hot_edges.add((t, n))
            hot_nodes.add(t)
            findings.append({"code": "R11", "tin": t, "severity": "medium",
                             "text": f"{p['name']} margin {p['gross_margin']:.1%} vs sector {p['sector_margin']:.1%}, buying "
                                     f"{p['rp_goods_pct_of_purchases']:.0%} of purchases from group entities."})
    # suspicious paths: Lesotho entity -> ... -> low-tax entity (networkx, max 2 hops)
    paths = []
    for src in hot_nodes:
        for dst in [n for n in G if G.nodes[n]["low_tax"]]:
            for path in nx.all_simple_paths(G, src, dst, cutoff=2):
                paths.append(path)

    nodes = [{"id": n, **{k: v for k, v in d.items()}, "flagged": n in hot_nodes,
              "profile": profiles.get(n)} for n, d in G.nodes(data=True)]
    edges = [{"source": u, "target": v, "types": d["types"], "amount": round(sum(d["types"].values())),
              "suspicious": (u, v) in hot_edges} for u, v, d in G.edges(data=True)]
    g = store.groups.loc[gid]
    risk = "high" if any(f["severity"] == "high" for f in findings) else ("medium" if findings else "low")
    return {"group_id": int(gid), "name": g["name"], "year": year, "nodes": nodes, "edges": edges,
            "findings": findings, "suspicious_paths": paths, "risk": risk}


def group_list(store) -> list[dict]:
    out = []
    for gid in store.groups.index:
        gg = group_graph(store, int(gid))
        out.append({"group_id": int(gid), "name": gg["name"], "risk": gg["risk"],
                    "entities": len(gg["nodes"]), "lesotho_entities": sum(not n["foreign"] for n in gg["nodes"]),
                    "findings": len(gg["findings"]), "codes": sorted({f["code"] for f in gg["findings"]})})
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(out, key=lambda x: (order[x["risk"]], -x["findings"]))


_ = pd
