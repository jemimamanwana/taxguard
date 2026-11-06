"""Isolation Forest anomaly model over claim features, with plain-language explanations."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from .features import ANOMALY_FEATURES, anomaly_matrix


def fit_anomaly(C: pd.DataFrame) -> pd.DataFrame:
    X = anomaly_matrix(C)
    model = IsolationForest(n_estimators=300, contamination="auto", random_state=0)
    model.fit(X.values)
    raw = -model.score_samples(X.values)  # higher = more anomalous
    pct = pd.Series(raw, index=X.index).rank(pct=True)
    med = X.median()
    mad = (X - med).abs().median().replace(0, np.nan)
    std = X.std().replace(0, 1)
    scale = mad.fillna(std / 1.4826) * 1.4826
    Z = (X - med) / scale
    out = pd.DataFrame(index=X.index)
    out["anomaly_raw"] = raw
    out["anomaly_pct"] = pct
    tops = []
    for cid in X.index:
        z = Z.loc[cid].abs().sort_values(ascending=False)
        items = []
        for feat in z.index[:3]:
            if z[feat] < 1.5:
                continue
            v = X.loc[cid, feat]
            items.append({
                "feature": feat, "label": ANOMALY_FEATURES[feat], "value": round(float(v), 3),
                "typical": round(float(med[feat]), 3), "direction": "higher" if v > med[feat] else "lower",
                "z": round(float(Z.loc[cid, feat]), 2),
            })
        tops.append(items)
    out["top_features"] = tops
    return out
