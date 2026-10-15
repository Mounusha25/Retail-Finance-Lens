"""Attribution helpers for the 'why the numbers moved' views."""
from __future__ import annotations

import math

import pandas as pd

TERMS = ("net_margin", "asset_turnover", "equity_multiplier")


def _log_mean(a: float, b: float) -> float:
    """Logarithmic mean L(a, b); the limit a when a == b."""
    return a if math.isclose(a, b, rel_tol=1e-12) else (a - b) / (math.log(a) - math.log(b))


def dupont_bridge(prior: dict | pd.Series, current: dict | pd.Series) -> dict[str, float] | None:
    """Attribute the change in ROE to net margin, asset turnover and the equity multiplier.

    Uses the logarithmic-mean Divisia decomposition, which is exact (the three contributions sum to the
    change in ROE with no residual) and symmetric. All terms and both ROE values must be positive.
    """
    values = [prior.get(k) for k in (*TERMS, "return_on_equity")] + [current.get(k) for k in (*TERMS, "return_on_equity")]
    if any(v is None or pd.isna(v) or float(v) <= 0 for v in values):
        return None
    roe0, roe1 = float(prior["return_on_equity"]), float(current["return_on_equity"])
    weight = _log_mean(roe1, roe0)
    contributions = {
        term: weight * math.log(float(current[term]) / float(prior[term])) for term in TERMS
    }
    contributions["change"] = roe1 - roe0
    return contributions


def dupont_bridge_series(company: pd.DataFrame) -> pd.DataFrame:
    """One row per fiscal year with each term's contribution to the change in ROE (decimal points)."""
    rows = []
    ordered = company.sort_values("period_end").reset_index(drop=True)
    for index in range(1, len(ordered)):
        bridge = dupont_bridge(ordered.iloc[index - 1], ordered.iloc[index])
        if bridge is None:
            continue
        rows.append({
            "period_end": ordered.iloc[index]["period_end"],
            "issuer_fiscal_year": ordered.iloc[index].get("issuer_fiscal_year"),
            "Net margin": bridge["net_margin"],
            "Asset turnover": bridge["asset_turnover"],
            "Leverage": bridge["equity_multiplier"],
            "Change in ROE": bridge["change"],
            "ROE": float(ordered.iloc[index]["return_on_equity"]),
        })
    return pd.DataFrame(rows)


def cash_flow_steps(row: pd.Series) -> list[tuple[str, float, str]] | None:
    """Net income -> operating cash flow, as waterfall steps. None when a required line is missing."""
    needed = ("net_income", "depreciation_amortization", "working_capital_cash_effect", "ocf_other_items", "operating_cash_flow")
    if any(pd.isna(row.get(k)) for k in needed):
        return None
    charges = row.get("restructuring_impairment_charges")
    charges = 0.0 if charges is None or pd.isna(charges) else float(charges)
    steps = [
        ("Net income", float(row["net_income"]), "absolute"),
        ("Depreciation & amortization", float(row["depreciation_amortization"]), "relative"),
    ]
    if charges:
        steps.append(("Impairment & restructuring", charges, "relative"))
    steps += [
        ("Working capital", float(row["working_capital_cash_effect"]), "relative"),
        ("Other (deferred tax, stock comp, other)", float(row["ocf_other_items"]), "relative"),
        ("Operating cash flow", float(row["operating_cash_flow"]), "total"),
    ]
    return steps
