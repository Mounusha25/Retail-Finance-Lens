from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data import latest_periods, load_or_stop
from app.ui import (
    CHART_CONFIG, COMPANY_COLORS, COMPANY_ORDER, TONES, brand_theme, format_value, kpi_grid, page_setup, section,
    style_figure,
)
from app.valuation import (
    SCENARIOS, YEARS, apply_scenario, base_assumptions, dcf, default_ronic, fade, implied_growth_shift,
    inputs_from_history, sensitivity_grid,
)


page_setup(
    "Forecast & Valuation",
    kicker="Forward view · illustrative",
    description=(
        "A driver-based ten-year forecast and discounted-cash-flow valuation with bear, base and bull cases. "
        "Every assumption is visible and adjustable."
    ),
)
st.warning(
    "**Illustrative scenario analysis, not a price target or investment advice.** The application holds no market prices or "
    "share counts. Defaults are derived from each company's own filings; the cost of capital and terminal assumptions are "
    "judgements you can change. Terminal value is a large share of the result, so treat the output as a range of what the "
    "assumptions imply."
)

annual = latest_periods(load_or_stop("annual"), 6).sort_values(["ticker", "period_end"])
ltm = load_or_stop("ltm").set_index("ticker")
tickers = [t for t in COMPANY_ORDER if t in ltm.index and bool(ltm.loc[t, "is_complete"])]
if not tickers:
    st.info("Trailing-twelve-month data are not complete for any company.")
    st.stop()

controls_left, controls_right = st.columns([1, 2])
with controls_left:
    ticker = st.selectbox("Company", tickers)
    scenario = st.radio("Scenario", list(SCENARIOS), index=1, horizontal=True)
with controls_right:
    wacc = st.slider("Cost of capital (WACC)", 5.0, 11.0, 7.5, 0.25, format="%.2f%%") / 100
    terminal_growth = st.slider("Terminal growth", 0.0, 4.0, 2.5, 0.25, format="%.2f%%") / 100
brand_theme(ticker)

if wacc <= terminal_growth + 0.01:
    st.error("Cost of capital must exceed terminal growth by at least one point for a meaningful value.")
    st.stop()

company_annual = annual[annual["ticker"] == ticker]
try:
    inputs = inputs_from_history(ltm.loc[ticker], company_annual)
    needed = ["total_revenue", "adjusted_operating_margin", "da_pct_revenue", "capex_pct_revenue"]
    missing = [k for k in needed if inputs.get(k) is None or pd.isna(inputs[k])]
    if missing:
        st.info(f"Cannot build a forecast: missing {', '.join(missing)}.")
        st.stop()
    default_return = default_ronic(wacc, inputs.get("roic"))
except Exception as exc:  # defensive: surfaces a clear message instead of a stack trace
    st.error(f"Could not derive assumptions: {exc}")
    st.stop()

with st.expander("Adjust operating assumptions", expanded=False):
    c1, c2, c3 = st.columns(3)
    first_growth = c1.number_input(
        "Year-1 growth (%)", value=round(base_assumptions(inputs, wacc, terminal_growth).growth_path[0] * 100, 1), step=0.5,
        help="Default: average of trailing-twelve-month growth and three-year CAGR, capped at 12%.",
    ) / 100
    margin = c2.number_input(
        "Operating margin (%)", value=round(float(inputs["adjusted_operating_margin"]) * 100, 2), step=0.1,
        help="Default: trailing-twelve-month operating margin before tagged restructuring and impairment charges.",
    ) / 100
    ronic = c3.number_input(
        "Return on new capital in perpetuity (%)", value=round(default_return * 100, 1), step=0.5,
        help="Default: halfway between WACC and the company's ROIC, capped at twice WACC. At WACC, growth adds no value.",
    ) / 100

base = base_assumptions(inputs, wacc, terminal_growth, terminal_ronic=ronic)
base = replace(
    base,
    growth_path=fade(first_growth, terminal_growth, YEARS),
    operating_margin_path=(margin,) * YEARS,
)
chosen = apply_scenario(base, scenario)
net_debt = float(inputs["net_debt"]) if inputs.get("net_debt") is not None and not pd.isna(inputs["net_debt"]) else 0.0
result = dcf(chosen, net_debt)
ebitda = float(inputs["ltm_ebitda"]) if inputs.get("ltm_ebitda") is not None and not pd.isna(inputs["ltm_ebitda"]) else None
net_income = float(inputs["ltm_net_income"]) if inputs.get("ltm_net_income") is not None and not pd.isna(inputs["ltm_net_income"]) else None

kpi_grid([
    {"label": f"Enterprise value · {scenario}", "value": f"${result['enterprise_value'] / 1e9:,.0f}B",
     "detail": f"Present value of {YEARS} years of free cash flow plus terminal value", "tone": "good"},
    {"label": "Equity value", "value": f"${result['equity_value'] / 1e9:,.0f}B",
     "detail": f"After {'net cash of' if net_debt < 0 else 'net debt of'} ${abs(net_debt) / 1e9:,.1f}B", "tone": "blue"},
    {"label": "Implied EV / EBITDA", "value": f"{result['enterprise_value'] / ebitda:,.1f}×" if ebitda else "N/A",
     "detail": "Value as a multiple of trailing-twelve-month EBITDA", "tone": "watch"},
    {"label": "Terminal value share", "value": f"{result['terminal_share']:.0%}",
     "detail": "Share of enterprise value beyond the explicit forecast", "tone": "red" if result["terminal_share"] > 0.8 else "good"},
])

# ---- projection ------------------------------------------------------------------------------------
section("The forecast", "Revenue, operating profit and unlevered free cash flow under the selected scenario.", "Projection")
projection = result["projection"]
left_plot, right_plot = st.columns(2)
with left_plot:
    revenue_fig = go.Figure(go.Bar(x=projection["year"], y=projection["revenue"] / 1e9, marker_color=TONES["muted"],
                                   name="Revenue"))
    revenue_fig.update_layout(title=dict(text="Revenue (USD billions)", font=dict(size=13)), xaxis_title="Forecast year",
                              showlegend=False)
    st.plotly_chart(style_figure(revenue_fig, height=320), width="stretch", config=CHART_CONFIG)
with right_plot:
    fcf_fig = go.Figure(go.Bar(x=projection["year"], y=projection["fcf"] / 1e9, marker_color=COMPANY_COLORS[ticker],
                               name="Free cash flow"))
    fcf_fig.update_layout(title=dict(text="Unlevered free cash flow (USD billions)", font=dict(size=13)),
                          xaxis_title="Forecast year", showlegend=False)
    st.plotly_chart(style_figure(fcf_fig, height=320), width="stretch", config=CHART_CONFIG)
st.caption("Separate scales are shown as separate charts so that the two measures are not visually correlated by axis choice.")

shown = projection.copy()
for column in ("revenue", "ebit", "nopat", "da", "capex", "delta_nwc", "fcf"):
    shown[column] = shown[column] / 1e9
st.dataframe(
    shown, hide_index=True, width="stretch",
    column_config={
        "year": "Year", "revenue": st.column_config.NumberColumn("Revenue ($B)", format="%.1f"),
        "growth": st.column_config.NumberColumn("Growth", format="percent"),
        "operating_margin": st.column_config.NumberColumn("Op. margin", format="percent"),
        "ebit": st.column_config.NumberColumn("EBIT ($B)", format="%.1f"),
        "nopat": st.column_config.NumberColumn("NOPAT ($B)", format="%.1f"),
        "da": st.column_config.NumberColumn("D&A ($B)", format="%.1f"),
        "capex": st.column_config.NumberColumn("Capex ($B)", format="%.1f"),
        "delta_nwc": st.column_config.NumberColumn("ΔWorking cap. ($B)", format="%.2f"),
        "fcf": st.column_config.NumberColumn("Free cash flow ($B)", format="%.1f"),
    },
)

# ---- value bridge ----------------------------------------------------------------------------------
section("From cash flows to equity value", "Present value of the forecast and terminal value, less net debt.", "Valuation bridge")
bridge = go.Figure(go.Waterfall(
    x=["PV of forecast cash flow", "PV of terminal value", "Enterprise value", "Net debt (−) / net cash (+)", "Equity value"],
    y=[result["pv_explicit"] / 1e9, result["pv_terminal"] / 1e9, 0, -net_debt / 1e9, 0],
    measure=["relative", "relative", "total", "relative", "total"],
    text=[f"${result['pv_explicit'] / 1e9:,.0f}B", f"${result['pv_terminal'] / 1e9:,.0f}B",
          f"${result['enterprise_value'] / 1e9:,.0f}B", f"${-net_debt / 1e9:,.1f}B", f"${result['equity_value'] / 1e9:,.0f}B"],
    textposition="outside", connector={"line": {"color": "#383835", "width": 1}},
    increasing={"marker": {"color": COMPANY_COLORS[ticker]}}, decreasing={"marker": {"color": "#898781"}},
    totals={"marker": {"color": TONES["primary"]}},
))
bridge.update_layout(showlegend=False, yaxis_title="USD billions", xaxis_title="")
bridge.update_yaxes(range=[0, max(result["equity_value"], result["enterprise_value"]) / 1e9 * 1.15])
st.plotly_chart(style_figure(bridge, height=360), width="stretch", config=CHART_CONFIG)
st.caption(
    "Operating lease expense is already deducted in operating profit, so lease liabilities are not subtracted again. "
    "Net debt is debt less cash; short-term investments are not netted."
)

# ---- sensitivity -----------------------------------------------------------------------------------
section("How sensitive is it?", "Implied EV / EBITDA across cost of capital and terminal growth, for the selected scenario.", "Sensitivity")
waccs = [round(wacc + step, 4) for step in (-0.01, -0.005, 0.0, 0.005, 0.01)]
growths = [round(terminal_growth + step, 4) for step in (-0.01, -0.005, 0.0, 0.005, 0.01)]
growths = [g for g in growths if g >= 0]
grid = sensitivity_grid(chosen, net_debt, waccs, growths)
if ebitda:
    multiple = grid / ebitda
    heat = go.Figure(go.Heatmap(
        z=multiple.to_numpy(), x=[f"{g:.2%}" for g in growths], y=[f"{w:.2%}" for w in waccs],
        text=[[("—" if pd.isna(v) else f"{v:.1f}×") for v in row] for row in multiple.to_numpy()],
        texttemplate="%{text}", colorscale=[[0, "#184f95"], [0.5, "#2a78d6"], [1, "#6aa5ee"]], showscale=False,
        hovertemplate="WACC %{y}, terminal growth %{x}<extra></extra>",
    ))
    heat.update_layout(xaxis_title="Terminal growth", yaxis_title="Cost of capital")
    heat.update_xaxes(type="category")
    heat.update_yaxes(type="category")
    st.plotly_chart(style_figure(heat, height=340), width="stretch", config=CHART_CONFIG)

# ---- scenario comparison ---------------------------------------------------------------------------
section("All companies, all scenarios", "Same cost of capital and terminal growth, each company's own default drivers.", "Comparison")
rows = []
for name in tickers:
    try:
        company_inputs = inputs_from_history(ltm.loc[name], annual[annual["ticker"] == name])
        company_base = base_assumptions(company_inputs, wacc, terminal_growth)
        company_debt = company_inputs.get("net_debt")
        company_debt = 0.0 if company_debt is None or pd.isna(company_debt) else float(company_debt)
        company_ebitda = company_inputs.get("ltm_ebitda")
        row = {"Company": name}
        for label in SCENARIOS:
            value = dcf(apply_scenario(company_base, label), company_debt)["enterprise_value"]
            row[f"{label} EV ($B)"] = value / 1e9
            row[f"{label} EV/EBITDA"] = value / float(company_ebitda) if company_ebitda and not pd.isna(company_ebitda) else None
        rows.append(row)
    except (ValueError, KeyError, TypeError):
        continue
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

# ---- reverse DCF -----------------------------------------------------------------------------------
section(
    "What would a market value imply?",
    "Enter a market value of equity (USD billions) from your own source. The model solves for the near-term growth "
    "that would justify it, holding margin and cost of capital fixed.",
    "Reverse DCF",
)
market_equity = st.number_input(f"{ticker} market value of equity ($B)", min_value=0.0, value=0.0, step=10.0,
                                help="Optional. Not supplied by this application.")
if market_equity > 0:
    market_ev = market_equity * 1e9 + net_debt
    shift = implied_growth_shift(chosen, market_ev, net_debt)
    gap = result["equity_value"] / (market_equity * 1e9) - 1
    st.markdown(
        f"**Model equity value is {gap:+.0%} versus the value you entered.** "
        + (
            f"To justify it, near-term growth would need to be about **{(chosen.growth_path[0] + shift):.1%}** in year 1 "
            f"({shift * 100:+.1f} points versus this scenario), fading to {terminal_growth:.1%}, with margin and cost of capital unchanged."
            if shift is not None else
            "That value is outside what growth alone can justify within this model; it would require a higher margin, a lower "
            "cost of capital, or a longer period of excess returns."
        )
    )
else:
    st.caption("Leave at 0 to skip. A market value far above the model's range is a statement about duration of advantage, not an error.")

st.caption(
    f"Defaults: year-1 growth is the average of trailing-twelve-month growth and three-year CAGR (capped at 12%), fading linearly "
    f"to terminal growth over {YEARS} years; operating margin is held at the trailing-twelve-month margin before tagged "
    "restructuring and impairment charges; capex follows its three-year average share of revenue; depreciation follows its "
    "trailing share; working capital follows the latest year's inventory plus receivables less payables as a share of revenue; "
    "tax is the effective rate within 18-30%. Bear lowers year-1 growth by 2 points and margin by 15%; bull raises growth by 1.5 "
    "points and margin by 10%."
)
