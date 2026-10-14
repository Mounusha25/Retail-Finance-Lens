from __future__ import annotations

import sys
from pathlib import Path

import plotly.express as px
from plotly.subplots import make_subplots
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data import latest_periods, load_or_stop
from app.ui import CHART_CONFIG, COMPANY_COLORS, LABELS, format_value, insight, kpi_grid, page_setup, section, style_figure, winner


page_setup(
    "Returns & DuPont",
    kicker="Capital efficiency",
    description="Show how much profit each retailer earns on the capital it employs, and whether returns come from margin, asset turnover, or leverage.",
)
annual = latest_periods(load_or_stop("annual"), 5)
latest = annual.sort_values("period_end").groupby("ticker", as_index=False).tail(1)

roic = winner(latest, "roic")
roe = winner(latest, "return_on_equity")
turnover = winner(latest, "asset_turnover")
if roic is None or roe is None or turnover is None:
    st.warning("Return metrics are not available yet. Re-run the pipeline load to refresh the analytical views.")
    st.stop()
kpi_grid([
    {"label": "Highest ROIC", "value": f"{roic['ticker']} · {format_value('roic', roic['roic'])}", "detail": "After-tax operating profit on average invested capital", "tone": "good"},
    {"label": "Highest return on equity", "value": f"{roe['ticker']} · {format_value('return_on_equity', roe['return_on_equity'])}", "detail": "Net income on average stockholders' equity", "tone": "blue"},
    {"label": "Fastest asset turnover", "value": f"{turnover['ticker']} · {format_value('asset_turnover', turnover['asset_turnover'])}", "detail": "Revenue per dollar of average assets", "tone": "blue"},
])

section("Return on invested capital", "ROIC strips out financing choices: it asks what the operating business earns on debt plus equity, net of cash.", "Capital efficiency")
roic_trend = px.line(
    annual.sort_values("period_end"), x="period_end", y="roic", color="ticker", markers=True,
    color_discrete_map=COMPANY_COLORS,
    labels={"roic": LABELS["roic"], "period_end": "Fiscal period end", "ticker": "Company"},
)
roic_trend.update_traces(line_width=3, marker_size=8)
st.plotly_chart(style_figure(roic_trend, "roic"), width="stretch", config=CHART_CONFIG)

section("DuPont decomposition", "Net margin × asset turnover × equity multiplier reproduces return on equity exactly.", "Why returns differ")
ordered = latest.sort_values("return_on_equity", ascending=False)
panels = (
    ("net_margin", "Net margin"),
    ("asset_turnover", "Asset turnover (×)"),
    ("equity_multiplier", "Equity multiplier (×)"),
)
bridge = make_subplots(rows=1, cols=3, subplot_titles=[label for _, label in panels], horizontal_spacing=0.08)
for position, (column, _label) in enumerate(panels, start=1):
    bridge.add_bar(
        x=ordered["ticker"], y=ordered[column], showlegend=False, row=1, col=position,
        marker_color=[COMPANY_COLORS[t] for t in ordered["ticker"]],
        text=[f"{v:.1%}" if column == "net_margin" else f"{v:.2f}×" for v in ordered[column]],
        textposition="outside",
    )
for position, (column, _label) in enumerate(panels, start=1):
    top = float(ordered[column].max())
    bridge.update_yaxes(
        range=[0, top * 1.22], row=1, col=position,
        tickformat=".1%" if column == "net_margin" else ".1f",
    )
st.plotly_chart(style_figure(bridge, height=340), width="stretch", config=CHART_CONFIG)

driver = st.radio(
    "Driver trend", ["return_on_equity", "net_margin", "asset_turnover", "equity_multiplier", "effective_tax_rate"],
    format_func=lambda item: LABELS[item], horizontal=True,
)
driver_trend = px.line(
    annual.sort_values("period_end"), x="period_end", y=driver, color="ticker", markers=True,
    color_discrete_map=COMPANY_COLORS,
    labels={driver: LABELS[driver], "period_end": "Fiscal period end", "ticker": "Company"},
)
driver_trend.update_traces(line_width=3, marker_size=8)
st.plotly_chart(style_figure(driver_trend, driver), width="stretch", config=CHART_CONFIG)

section("Analyst interpretation", "Read the three drivers together: a high ROE built on leverage is a different quality of return than one built on margin.", "Management implications")
for _, row in latest.sort_values("return_on_equity", ascending=False).iterrows():
    insight(
        f"{row['ticker']} · ROE {format_value('return_on_equity', row['return_on_equity'])}, ROIC {format_value('roic', row['roic'])}",
        f"Net margin {format_value('net_margin', row['net_margin'])}, asset turnover {format_value('asset_turnover', row['asset_turnover'])}, "
        f"equity multiplier {format_value('equity_multiplier', row['equity_multiplier'])}. "
        f"Effective tax rate {format_value('effective_tax_rate', row['effective_tax_rate'])}.",
    )

st.caption(
    "Invested capital = total debt + total equity − cash, averaged over beginning and ending balances. Operating leases are excluded, "
    "and Target's debt includes finance leases as tagged. The tax rate is approximated as tax expense ÷ (net income + tax expense). "
    "ROE uses net income attributable to the parent over parent stockholders' equity."
)
