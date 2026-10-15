from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.analysis import cash_flow_steps, dupont_bridge_series
from app.data import latest_periods, load_or_stop
from app.ui import (
    CHART_CONFIG, COMPANY_COLORS, COMPANY_ORDER, LABELS, TONES, brand_theme, format_value, insight, kpi_grid, page_setup,
    section, style_figure,
)


page_setup(
    "Why Returns Moved",
    kicker="Attribution",
    description=(
        "Do new dollars of capital earn their keep, how much profit does extra revenue add, why does cash flow differ "
        "from earnings, and what drove each change in return on equity?"
    ),
)

annual = latest_periods(load_or_stop("annual"), 5).sort_values(["ticker", "period_end"])
latest = annual.groupby("ticker", as_index=False).tail(1).copy()
latest["ticker"] = pd.Categorical(latest["ticker"], categories=list(COMPANY_ORDER), ordered=True)
latest = latest.sort_values("ticker").reset_index(drop=True)
latest["ticker"] = latest["ticker"].astype(str)

def _fmt(metric: str, value: object) -> str:
    return format_value(metric, value)

best_incremental = latest.dropna(subset=["roiic_3y"])
kpi_grid([
    {
        "label": "Highest 3-yr incremental ROIC",
        "value": (
            f"{best_incremental.loc[best_incremental['roiic_3y'].idxmax(), 'ticker']} · "
            f"{_fmt('roiic_3y', best_incremental['roiic_3y'].max())}"
        ) if not best_incremental.empty else "N/A",
        "detail": "Earnings added per dollar of capital added over three years",
        "tone": "good",
    },
    {
        "label": "Highest FCF conversion",
        "value": (
            f"{latest.loc[latest['fcf_conversion'].idxmax(), 'ticker']} · {_fmt('fcf_conversion', latest['fcf_conversion'].max())}"
            if latest["fcf_conversion"].notna().any() else "N/A"
        ),
        "detail": "Free cash flow ÷ net income; inflated when earnings carry non-cash charges",
        "tone": "blue",
    },
    {
        "label": "Heaviest net reinvestment",
        "value": (
            f"{latest.loc[latest['reinvestment_rate'].idxmax(), 'ticker']} · {_fmt('reinvestment_rate', latest['reinvestment_rate'].max())}"
            if latest["reinvestment_rate"].notna().any() else "N/A"
        ),
        "detail": "(Capex − D&A + working-capital build) ÷ NOPAT",
        "tone": "watch",
    },
])

# ---- 1. Incremental returns ------------------------------------------------------------------------
section(
    "Do new dollars of capital earn their keep?",
    "Incremental ROIC is the change in after-tax operating profit divided by the change in invested capital. "
    "If it exceeds the existing ROIC, growth is widening the advantage; if it is below, returns are being diluted.",
    "Incremental returns",
)
returns_view = latest.dropna(subset=["roic"]).copy()
fig = go.Figure()
fig.add_bar(name="ROIC (existing capital)", x=returns_view["ticker"], y=returns_view["roic"], marker_color=TONES["muted"],
            text=[f"{v:.0%}" for v in returns_view["roic"]], textposition="outside")
fig.add_bar(name="Incremental ROIC, 3-year", x=returns_view["ticker"], y=returns_view["roiic_3y"], marker_color=TONES["accent"],
            text=[("n/m" if pd.isna(v) else f"{v:.0%}") for v in returns_view["roiic_3y"]], textposition="outside")
fig.update_layout(barmode="group")
fig.update_yaxes(tickformat=".0%", range=[0, float(returns_view[["roic", "roiic_3y"]].max().max()) * 1.2])
st.plotly_chart(style_figure(fig, height=360), width="stretch", config=CHART_CONFIG)
st.caption(
    "n/m = not meaningful: invested capital did not grow by at least 5% over three years (or 2% in one year), so the ratio "
    "would be unstable. A three-year figure can flatter a company recovering from a depressed starting year, so read it "
    "beside the single-year line below, which is noisier but shows the latest year on its own."
)
roiic_history = annual.dropna(subset=["roiic"])
if not roiic_history.empty:
    line = px.line(
        roiic_history, x="period_end", y="roiic", color="ticker", markers=True, color_discrete_map=COMPANY_COLORS,
        labels={"roiic": LABELS["roiic"], "period_end": "Fiscal period end", "ticker": "Company"},
    )
    line.add_hline(y=0, line_color="#898781")
    line.update_traces(line_width=3, marker_size=8)
    st.plotly_chart(style_figure(line, "roiic", 320), width="stretch", config=CHART_CONFIG)

# ---- 2. Operating leverage -------------------------------------------------------------------------
section(
    "How much profit does extra revenue add?",
    "Incremental operating margin is the extra operating income earned per extra dollar of revenue. Compared with the "
    "average margin it shows whether growth is accretive.",
    "Operating leverage",
)
lever = latest.dropna(subset=["operating_margin"]).copy()
bars = go.Figure()
bars.add_bar(name="Average operating margin", x=lever["ticker"], y=lever["operating_margin"], marker_color=TONES["muted"],
             text=[f"{v:.1%}" for v in lever["operating_margin"]], textposition="outside")
bars.add_bar(name="Incremental operating margin", x=lever["ticker"], y=lever["incremental_operating_margin"],
             marker_color=TONES["accent"],
             text=[("n/m" if pd.isna(v) else f"{v:.1%}") for v in lever["incremental_operating_margin"]], textposition="outside")
bars.update_layout(barmode="group")
bars.update_yaxes(tickformat=".0%", range=[0, float(lever[["operating_margin", "incremental_operating_margin"]].max().max()) * 1.2])
st.plotly_chart(style_figure(bars, height=340), width="stretch", config=CHART_CONFIG)
st.caption("n/m = revenue grew less than 1% (or fell), so the change in margin per dollar of growth is not meaningful.")

# ---- 3. Profit to cash -----------------------------------------------------------------------------
section(
    "Why does cash flow differ from earnings?",
    "Net income plus non-cash charges and working-capital movements reconciles to operating cash flow. "
    "Working capital is measured from balance-sheet changes in inventory, receivables and payables.",
    "Cash-flow quality",
)
tickers = [t for t in COMPANY_ORDER if t in set(annual["ticker"])]
selected = st.selectbox("Company", tickers, key="why_company")
brand_theme(selected)
company = annual[annual["ticker"] == selected].sort_values("period_end")
steps = cash_flow_steps(company.iloc[-1])
if steps is None:
    st.info("The latest year lacks one of the lines needed for the net income to cash flow bridge.")
else:
    waterfall = go.Figure(go.Waterfall(
        x=[label for label, _, _ in steps], y=[value / 1e9 for _, value, _ in steps],
        measure=[kind for _, _, kind in steps],
        text=[f"${value / 1e9:,.1f}B" for _, value, _ in steps], textposition="outside",
        connector={"line": {"color": "#383835", "width": 1}},
        increasing={"marker": {"color": COMPANY_COLORS[selected]}},
        decreasing={"marker": {"color": "#898781"}},
        totals={"marker": {"color": TONES["primary"]}},
    ))
    waterfall.update_layout(showlegend=False, yaxis_title="USD billions", xaxis_title="")
    st.plotly_chart(style_figure(waterfall, height=380), width="stretch", config=CHART_CONFIG)
quality = annual.dropna(subset=["fcf_conversion"])
conv = px.line(
    quality, x="period_end", y="fcf_conversion", color="ticker", markers=True, color_discrete_map=COMPANY_COLORS,
    labels={"fcf_conversion": LABELS["fcf_conversion"], "period_end": "Fiscal period end", "ticker": "Company"},
)
conv.add_hline(y=1.0, line_dash="dash", line_color="#898781")
conv.update_traces(line_width=3, marker_size=8)
st.plotly_chart(style_figure(conv, "fcf_conversion", 320), width="stretch", config=CHART_CONFIG)
st.caption(
    "FCF conversion = free cash flow ÷ net income (years with non-positive earnings are not plotted). Values far above 100% usually "
    "mean earnings were depressed by non-cash charges, not that cash generation was unusually strong."
)

# ---- 4. ROE attribution ----------------------------------------------------------------------------
section(
    "What moved return on equity?",
    "Each year's change in ROE is split exactly into net margin, asset turnover and leverage (logarithmic-mean decomposition).",
    "DuPont attribution",
)
bridge = dupont_bridge_series(company)
if bridge.empty:
    st.info("Not enough consecutive years with positive margin, turnover and leverage to attribute changes.")
else:
    labels = [f"FY{int(y)}" if pd.notna(y) else pd.Timestamp(d).strftime("%b %Y")
              for y, d in zip(bridge["issuer_fiscal_year"], bridge["period_end"])]
    stack = go.Figure()
    for column, colour in (("Net margin", TONES["accent"]), ("Asset turnover", TONES["secondary"]), ("Leverage", TONES["muted"])):
        stack.add_bar(name=column, x=labels, y=bridge[column] * 100, marker_color=colour)
    stack.add_scatter(name="Change in ROE", x=labels, y=bridge["Change in ROE"] * 100, mode="markers",
                      marker=dict(color="#f0efec", size=11, symbol="diamond", line=dict(color="#0d0d0d", width=1)))
    stack.update_layout(barmode="relative", yaxis_title="Percentage points of ROE", xaxis_title="")
    st.plotly_chart(style_figure(stack, height=360), width="stretch", config=CHART_CONFIG)
    st.caption("Bars sum to the diamond, which is the year's total change in ROE.")

# ---- 5. Reinvestment -------------------------------------------------------------------------------
section(
    "Are they investing to grow or to stand still?",
    "Capex above depreciation means the asset base is growing; near 1× is close to maintenance.",
    "Reinvestment profile",
)
invest = latest.dropna(subset=["capex_to_da"]).copy()
ratio = go.Figure(go.Bar(
    x=invest["ticker"], y=invest["capex_to_da"], marker_color=[COMPANY_COLORS[t] for t in invest["ticker"]],
    text=[f"{v:.2f}×" for v in invest["capex_to_da"]], textposition="outside",
))
ratio.add_hline(y=1.0, line_dash="dash", line_color="#898781")
ratio.update_yaxes(title="Capex ÷ depreciation & amortization", rangemode="tozero")
st.plotly_chart(style_figure(ratio, height=320), width="stretch", config=CHART_CONFIG)

table = latest[["ticker", "capex_to_da", "capex_to_revenue", "ppe_turnover", "net_reinvestment", "reinvestment_rate",
                "roic", "roiic_3y", "incremental_operating_margin", "operating_leverage", "accruals_ratio", "fcf_conversion"]].copy()
table["net_reinvestment"] = table["net_reinvestment"] / 1e9
st.dataframe(
    table, hide_index=True, width="stretch",
    column_config={
        "ticker": "Company",
        "capex_to_da": st.column_config.NumberColumn("Capex / D&A", format="%.2fx"),
        "capex_to_revenue": st.column_config.NumberColumn("Capex / revenue", format="percent"),
        "ppe_turnover": st.column_config.NumberColumn("PP&E turnover", format="%.2fx"),
        "net_reinvestment": st.column_config.NumberColumn("Net reinvestment ($B)", format="%.1f"),
        "reinvestment_rate": st.column_config.NumberColumn("Reinvestment rate", format="percent"),
        "roic": st.column_config.NumberColumn("ROIC", format="percent"),
        "roiic_3y": st.column_config.NumberColumn("Incr. ROIC 3y", format="percent"),
        "incremental_operating_margin": st.column_config.NumberColumn("Incr. op. margin", format="percent"),
        "operating_leverage": st.column_config.NumberColumn("Operating leverage", format="%.1fx"),
        "accruals_ratio": st.column_config.NumberColumn("Accruals ratio", format="percent"),
        "fcf_conversion": st.column_config.NumberColumn("FCF conversion", format="percent"),
    },
)

section("Reading the numbers", "Generated from the latest fiscal year; interpret with the caveats above.", "Analyst interpretation")
columns = st.columns(2)
for index, (_, row) in enumerate(latest.iterrows()):
    notes = []
    if pd.notna(row["roiic_3y"]) and pd.notna(row["roic"]):
        direction = "above" if row["roiic_3y"] > row["roic"] else "below"
        notes.append(
            f"three-year incremental ROIC of {_fmt('roiic_3y', row['roiic_3y'])} is {direction} its {_fmt('roic', row['roic'])} average"
        )
        if pd.notna(row["roiic"]) and row["roiic"] < row["roic"]:
            notes.append(
                f"but the latest single year is only {_fmt('roiic', row['roiic'])}, so the three-year figure partly reflects a "
                "recovery from a weaker starting year"
            )
    elif pd.notna(row["roic"]):
        notes.append("capital did not grow enough for a meaningful incremental return")
    if pd.notna(row["capex_to_da"]):
        stance = "investing for growth" if row["capex_to_da"] > 1.5 else "near a maintenance level" if row["capex_to_da"] < 1.25 else "growing its asset base"
        notes.append(f"capex is {_fmt('capex_to_da', row['capex_to_da'])} depreciation ({stance})")
    if pd.notna(row["fcf_conversion"]):
        notes.append(f"FCF conversion is {_fmt('fcf_conversion', row['fcf_conversion'])}")
    with columns[index % 2]:
        insight(str(row["ticker"]), "; ".join(notes).capitalize() + "." if notes else "Insufficient data.")
