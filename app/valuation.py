"""Illustrative driver-based forecast and discounted-cash-flow valuation.

Everything here is assumption-driven. Defaults are derived from each company's own history, but the output is a
scenario analysis, not a price target: the application holds no market prices or share counts.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

YEARS = 10
SCENARIOS = {
    #            growth shift (pp, year 1)   margin multiplier
    "Bear": (-0.020, 0.85),
    "Base": (0.0, 1.00),
    "Bull": (0.015, 1.10),
}


@dataclass(frozen=True)
class Assumptions:
    start_revenue: float
    growth_path: tuple[float, ...]
    operating_margin_path: tuple[float, ...]
    tax_rate: float
    da_pct_revenue: float
    capex_pct_revenue: float
    nwc_pct_revenue: float
    wacc: float
    terminal_growth: float
    terminal_ronic: float

    def __post_init__(self) -> None:
        if len(self.growth_path) != len(self.operating_margin_path) or not self.growth_path:
            raise ValueError("growth and margin paths must be non-empty and the same length")


def clip(value: float, low: float, high: float) -> float:
    return float(min(max(value, low), high))


def fade(start: float, end: float, years: int = YEARS) -> tuple[float, ...]:
    """Linear path from `start` in year 1 to `end` in the final year."""
    if years == 1:
        return (end,)
    return tuple(start + (end - start) * t / (years - 1) for t in range(years))


def project(a: Assumptions) -> pd.DataFrame:
    """Five-year projection of revenue, NOPAT and unlevered free cash flow."""
    rows = []
    revenue = a.start_revenue
    for year in range(1, len(a.growth_path) + 1):
        previous = revenue
        revenue = previous * (1 + a.growth_path[year - 1])
        ebit = revenue * a.operating_margin_path[year - 1]
        nopat = ebit * (1 - a.tax_rate)
        da = revenue * a.da_pct_revenue
        capex = revenue * a.capex_pct_revenue
        delta_nwc = a.nwc_pct_revenue * (revenue - previous)
        rows.append({
            "year": year, "revenue": revenue, "growth": a.growth_path[year - 1],
            "operating_margin": a.operating_margin_path[year - 1], "ebit": ebit, "nopat": nopat,
            "da": da, "capex": capex, "delta_nwc": delta_nwc,
            "fcf": nopat + da - capex - delta_nwc,
        })
    return pd.DataFrame(rows)


def dcf(a: Assumptions, net_debt: float = 0.0) -> dict:
    """Enterprise and equity value.

    Terminal value uses the value-driver form NOPAT(T+1) x (1 - g / RONIC) / (WACC - g), so growth in perpetuity
    must be funded by reinvestment earning RONIC. With RONIC equal to WACC, growth adds no value.
    """
    if a.wacc <= a.terminal_growth:
        raise ValueError("WACC must exceed terminal growth")
    if a.terminal_ronic <= 0:
        raise ValueError("terminal return on new capital must be positive")
    table = project(a)
    discount = (1 + a.wacc) ** table["year"].to_numpy()
    pv_explicit = float((table["fcf"].to_numpy() / discount).sum())
    last = table.iloc[-1]
    nopat_next = last["revenue"] * (1 + a.terminal_growth) * last["operating_margin"] * (1 - a.tax_rate)
    terminal_value = nopat_next * (1 - a.terminal_growth / a.terminal_ronic) / (a.wacc - a.terminal_growth)
    pv_terminal = float(terminal_value / (1 + a.wacc) ** len(table))
    enterprise = pv_explicit + pv_terminal
    return {
        "projection": table,
        "pv_explicit": pv_explicit,
        "terminal_value": float(terminal_value),
        "pv_terminal": pv_terminal,
        "enterprise_value": enterprise,
        "terminal_share": pv_terminal / enterprise if enterprise else float("nan"),
        "net_debt": net_debt,
        "equity_value": enterprise - net_debt,
    }


def default_ronic(wacc: float, roic: float | None) -> float:
    """Return on new capital in perpetuity: halfway between WACC and the company's own ROIC, capped at 2x WACC.

    A durable advantage lets new capital earn more than the cost of capital, but returns on new capital are expected
    to fade, so the company's current ROIC is only partly credited. With no ROIC the default is WACC (growth adds no value).
    """
    if roic is None or pd.isna(roic):
        return wacc
    return clip((wacc + float(roic)) / 2, wacc, 2 * wacc)


def base_assumptions(
    inputs: dict, wacc: float, terminal_growth: float, terminal_ronic: float | None = None, years: int = YEARS
) -> Assumptions:
    """Derive default assumptions from a company's own history.

    `inputs` needs: total_revenue, revenue_growth, cagr_3y, adjusted_operating_margin, effective_tax_rate,
    da_pct_revenue, capex_pct_revenue, nwc_pct_revenue (the last two from multi-year or latest-year averages).
    """
    growth_signals = [v for v in (inputs.get("revenue_growth"), inputs.get("cagr_3y")) if v is not None and not pd.isna(v)]
    if not growth_signals:
        raise ValueError("no revenue growth history to anchor the forecast")
    first_year_growth = clip(float(np.mean(growth_signals)), -0.02, 0.12)
    tax = inputs.get("effective_tax_rate")
    tax = 0.24 if tax is None or pd.isna(tax) else clip(float(tax), 0.18, 0.30)
    margin = float(inputs["adjusted_operating_margin"])
    return Assumptions(
        start_revenue=float(inputs["total_revenue"]),
        growth_path=fade(first_year_growth, terminal_growth, years),
        operating_margin_path=(margin,) * years,
        tax_rate=tax,
        da_pct_revenue=float(inputs["da_pct_revenue"]),
        capex_pct_revenue=float(inputs["capex_pct_revenue"]),
        nwc_pct_revenue=float(inputs.get("nwc_pct_revenue") or 0.0),
        wacc=wacc,
        terminal_growth=terminal_growth,
        terminal_ronic=default_ronic(wacc, inputs.get("roic")) if terminal_ronic is None else terminal_ronic,
    )


def apply_scenario(a: Assumptions, scenario: str) -> Assumptions:
    growth_shift, margin_multiplier = SCENARIOS[scenario]
    first_year = a.growth_path[0] + growth_shift
    return replace(
        a,
        growth_path=fade(first_year, a.terminal_growth, len(a.growth_path)),
        operating_margin_path=tuple(m * margin_multiplier for m in a.operating_margin_path),
    )


def implied_growth_shift(a: Assumptions, target_enterprise_value: float, net_debt: float = 0.0) -> float | None:
    """Reverse DCF: the uniform change in near-term growth (percentage points, fading to terminal growth)
    that makes the model's enterprise value equal a target. None when the target is outside what growth alone
    can reach within [-5, +25] points."""
    def value(shift: float) -> float:
        variant = replace(a, growth_path=fade(a.growth_path[0] + shift, a.terminal_growth, len(a.growth_path)))
        return dcf(variant, net_debt)["enterprise_value"]

    low, high = -0.05, 0.25
    if not (value(low) <= target_enterprise_value <= value(high)):
        return None
    for _ in range(80):
        mid = (low + high) / 2
        if value(mid) < target_enterprise_value:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def sensitivity_grid(a: Assumptions, net_debt: float, waccs: list[float], growths: list[float]) -> pd.DataFrame:
    """Enterprise value for each WACC (rows) and terminal growth (columns); invalid pairs are NaN."""
    grid = {}
    for g in growths:
        column = []
        for w in waccs:
            try:
                variant = replace(a, wacc=w, terminal_growth=g, terminal_ronic=w if a.terminal_ronic == a.wacc else a.terminal_ronic,
                                  growth_path=fade(a.growth_path[0], g, len(a.growth_path)))
                column.append(dcf(variant, net_debt)["enterprise_value"])
            except ValueError:
                column.append(float("nan"))
        grid[g] = column
    return pd.DataFrame(grid, index=waccs)


def inputs_from_history(ltm_row: pd.Series, annual_company: pd.DataFrame) -> dict:
    """Assemble the default-assumption inputs from the LTM row and the company's fiscal-year history."""
    annual = annual_company.sort_values("period_end")
    latest = annual.iloc[-1]
    revenue = float(ltm_row["total_revenue"])
    cagr = None
    if len(annual) >= 4 and annual.iloc[-4]["total_revenue"] and annual.iloc[-4]["total_revenue"] > 0:
        cagr = float((annual.iloc[-1]["total_revenue"] / annual.iloc[-4]["total_revenue"]) ** (1 / 3) - 1)
    window = annual.tail(3)
    capex_pct = (window["capital_expenditures"] / window["total_revenue"]).dropna()
    da = ltm_row.get("depreciation_amortization")
    nwc_parts = [latest.get("inventory"), latest.get("accounts_receivable_net_current"), latest.get("accounts_payable_current")]
    inventory, receivables, payables = (0.0 if v is None or pd.isna(v) else float(v) for v in nwc_parts)
    return {
        "total_revenue": revenue,
        "revenue_growth": ltm_row.get("revenue_growth"),
        "cagr_3y": cagr,
        "adjusted_operating_margin": ltm_row.get("adjusted_operating_margin"),
        "effective_tax_rate": ltm_row.get("effective_tax_rate"),
        "da_pct_revenue": float(da) / revenue if da is not None and not pd.isna(da) and revenue else None,
        "capex_pct_revenue": float(capex_pct.mean()) if not capex_pct.empty else None,
        "nwc_pct_revenue": (inventory + receivables - payables) / float(latest["total_revenue"])
        if latest.get("total_revenue") else 0.0,
        "roic": ltm_row.get("roic"),
        "ltm_ebitda": ltm_row.get("ebitda"),
        "ltm_net_income": ltm_row.get("net_income"),
        "net_debt": ltm_row.get("net_debt"),
    }
