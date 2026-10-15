"""Transparent peer scoring: rank-based, so one outlier cannot dominate a pillar."""
from __future__ import annotations

import numpy as np
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


def pillar_table(peer: pd.DataFrame) -> pd.DataFrame:
    """Pillar scores (0-100) per ticker, before any weighting."""
    scored = score_peers(peer)
    return scored.set_index("ticker")[list(PILLARS)]


def _weighted(pillars: pd.DataFrame, weights: np.ndarray) -> pd.DataFrame:
    """Composite for many weight vectors at once; a missing pillar is dropped and weights renormalised."""
    values = pillars.to_numpy(dtype=float)                    # companies x pillars
    present = ~np.isnan(values)
    numerator = np.nan_to_num(values) @ weights.T              # companies x scenarios
    denominator = present.astype(float) @ weights.T
    with np.errstate(invalid="ignore", divide="ignore"):
        composite = np.where(denominator > 0, numerator / denominator, np.nan)
    return pd.DataFrame(composite, index=pillars.index)


def sensitivity(peer: pd.DataFrame, random_scenarios: int = 500, seed: int = 7) -> dict[str, pd.DataFrame]:
    """How stable is the ranking? Named scenarios plus random weightings.

    Returns 'named' (one row per scenario with the leader and its margin over the runner-up) and
    'summary' (per company: share of all scenarios led, best/worst rank, average rank).
    """
    pillars = pillar_table(peer)
    names = list(pillars.columns)
    k = len(names)
    scenarios: list[tuple[str, np.ndarray]] = [("Equal weights", np.ones(k))]
    for index, name in enumerate(names):
        emphasised = np.ones(k)
        emphasised[index] = 3.0
        scenarios.append((f"{name} weighted 3×", emphasised))
    for index, name in enumerate(names):
        dropped = np.ones(k)
        dropped[index] = 0.0
        if dropped.sum() > 0:
            scenarios.append((f"Without {name}", dropped))
    generator = np.random.default_rng(seed)
    random_weights = generator.dirichlet(np.ones(k), size=random_scenarios)
    all_weights = np.vstack([w for _, w in scenarios] + [random_weights])
    composites = _weighted(pillars, all_weights)

    ranks = composites.rank(axis=0, ascending=False, method="min")
    leaders = composites.idxmax(axis=0)
    named_rows = []
    for position, (label, _) in enumerate(scenarios):
        column = composites[position].dropna().sort_values(ascending=False)
        if column.empty:
            continue
        margin = float(column.iloc[0] - column.iloc[1]) if len(column) > 1 else float("nan")
        named_rows.append({
            "Scenario": label, "Leader": str(column.index[0]),
            "Runner-up": str(column.index[1]) if len(column) > 1 else "—", "Lead (points)": margin,
        })
    summary = pd.DataFrame({
        "Share of weightings led": leaders.value_counts(normalize=True).reindex(pillars.index).fillna(0.0),
        "Best rank": ranks.min(axis=1),
        "Worst rank": ranks.max(axis=1),
        "Average rank": ranks.mean(axis=1),
    }).sort_values("Share of weightings led", ascending=False)
    summary.index.name = "ticker"
    return {"named": pd.DataFrame(named_rows), "summary": summary.reset_index(), "scenarios": len(all_weights)}
