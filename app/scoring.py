"""Transparent peer scoring: rank-based, so one outlier cannot dominate a pillar."""
from __future__ import annotations

import pandas as pd

# (column, higher_is_better)
PILLARS: dict[str, list[tuple[str, bool]]] = {
    "Growth": [("revenue_growth", True)],
    "Profitability": [("operating_margin", True), ("net_margin", True)],
    "Efficiency": [("inventory_turnover", True), ("cash_conversion_cycle", False)],
    "Cash": [("fcf_margin", True)],
    "Returns": [("roic", True)],
    "Balance sheet": [("net_debt_to_ebitda", False), ("interest_coverage", True)],
}
DEFAULT_WEIGHTS: dict[str, float] = {name: 20.0 for name in PILLARS}


def with_fcf_margin(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    revenue = frame["total_revenue"].where(frame["total_revenue"] > 0)
    frame["fcf_margin"] = frame["free_cash_flow"] / revenue
    return frame


def _rank_scores(values: pd.Series, higher_is_better: bool) -> pd.Series:
    """0-100 by rank (ties share the average). One valid value scores 50."""
    valid = values.dropna()
    scores = pd.Series(float("nan"), index=values.index)
    if len(valid) == 0:
        return scores
    if len(valid) == 1:
        scores.loc[valid.index] = 50.0
        return scores
    ranks = valid.rank(ascending=not higher_is_better, method="average")  # 1 = best
    scores.loc[valid.index] = (len(valid) - ranks) / (len(valid) - 1) * 100.0
    return scores


def score_peers(peer: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.DataFrame:
    """Return one row per ticker with metric scores, pillar scores, composite and rank.

    Pillars with no data for a company are excluded and the remaining weights renormalised,
    so a missing metric never counts as a zero.
    """
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    frame = with_fcf_margin(peer).set_index("ticker")
    out = pd.DataFrame(index=frame.index)
    for pillar, metrics in PILLARS.items():
        parts = []
        for column, higher in metrics:
            if column not in frame:
                continue
            score = _rank_scores(frame[column], higher)
            out[f"score:{column}"] = score
            parts.append(score)
        out[pillar] = pd.concat(parts, axis=1).mean(axis=1, skipna=True) if parts else float("nan")
    pillar_scores = out[list(PILLARS)]
    weight_row = pd.Series({p: float(weights[p]) for p in PILLARS})
    available = pillar_scores.notna() * weight_row
    totals = available.sum(axis=1).replace(0, float("nan"))
    out["Composite"] = (pillar_scores.fillna(0) * weight_row).sum(axis=1) / totals
    out["Rank"] = out["Composite"].rank(ascending=False, method="min")
    return out.reset_index().sort_values("Composite", ascending=False).reset_index(drop=True)


def pillar_leaders(scores: pd.DataFrame) -> dict[str, str]:
    leaders = {}
    for pillar in PILLARS:
        valid = scores.dropna(subset=[pillar])
        if not valid.empty:
            leaders[pillar] = str(valid.loc[valid[pillar].idxmax(), "ticker"])
    return leaders


def latest_and_prior(annual: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Latest and prior-year value of a metric per ticker, plus the change."""
    rows = []
    for ticker, group in annual.sort_values("period_end").groupby("ticker"):
        values = group[metric].tolist()
        latest = values[-1] if values else None
        prior = values[-2] if len(values) > 1 else None
        change = None if latest is None or prior is None or pd.isna(latest) or pd.isna(prior) else latest - prior
        rows.append({"ticker": ticker, "latest": latest, "prior": prior, "change": change, "history": values})
    return pd.DataFrame(rows)
