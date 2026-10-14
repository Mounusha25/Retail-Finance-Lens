from __future__ import annotations

import sys
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data import latest_periods, load_or_stop
from app.ui import CHART_CONFIG, COMPANY_COLORS, LABELS, format_value, insight, kpi_grid, page_setup, section, style_figure, winner


page_setup(
    "Working Capital",
    kicker="Operating efficiency",
    description="Separate operational speed from supplier financing and show whether inventory is building faster than sales.",
)
annual = latest_periods(load_or_stop("annual"), 5)
latest = annual.sort_values("period_end").groupby("ticker", as_index=False).tail(1)

turns = winner(latest, "inventory_turnover")
cycle = winner(latest, "cash_conversion_cycle", highest=False)
dio = winner(latest, "days_inventory_outstanding", highest=False)
kpi_grid([
    {"label": "Fastest inventory turns", "value": f"{turns['ticker']} · {format_value('inventory_turnover', turns['inventory_turnover'])}", "detail": "Higher indicates faster sell-through", "tone": "good"},
    {"label": "Shortest cash cycle", "value": f"{cycle['ticker']} · {format_value('cash_conversion_cycle', cycle['cash_conversion_cycle'])}", "detail": "Lower indicates less cash tied up", "tone": "good"},
    {"label": "Lowest inventory days", "value": f"{dio['ticker']} · {format_value('days_inventory_outstanding', dio['days_inventory_outstanding'])}", "detail": "Average inventory on actual fiscal days", "tone": "blue"},
])

section("Latest operating-cycle bridge", "Inventory and receivable days consume cash; payable days fund the cycle.")
bridge = go.Figure()
bridge.add_bar(name="Receivable days", x=latest["ticker"], y=latest["receivable_days"], marker_color="#60A5FA")
bridge.add_bar(name="Inventory days", x=latest["ticker"], y=latest["days_inventory_outstanding"], marker_color="#2563EB")
bridge.add_bar(name="Payable days (offset)", x=latest["ticker"], y=-latest["payable_days"], marker_color="#7C3AED")
bridge.add_scatter(name="Cash conversion cycle", x=latest["ticker"], y=latest["cash_conversion_cycle"], mode="markers+text", text=[f"{v:.1f}" for v in latest["cash_conversion_cycle"]], textposition="top center", marker=dict(size=13, color="#0D9488", symbol="diamond"))
bridge.update_layout(barmode="relative", yaxis_title="Days", xaxis_title="")
st.plotly_chart(style_figure(bridge, "cash_conversion_cycle"), width="stretch", config=CHART_CONFIG)

section("Five-year working-capital trend", "Choose the pressure point to compare direction and volatility.")
metric = st.radio(
    "Metric", ["days_inventory_outstanding", "payable_days", "cash_conversion_cycle", "inventory_growth_gap"],
    format_func=lambda item: LABELS[item], horizontal=True,
)
trend = px.line(
    annual.sort_values("period_end"), x="period_end", y=metric, color="ticker", markers=True,
    color_discrete_map=COMPANY_COLORS,
    labels={metric: LABELS[metric], "period_end": "Fiscal period end", "ticker": "Company"},
)
trend.update_traces(line_width=3, marker_size=8)
st.plotly_chart(style_figure(trend, metric), width="stretch", config=CHART_CONFIG)

section("Analyst interpretation", "Use the cash cycle as an operating diagnostic, not a standalone verdict.", "Management implications")
for _, row in latest.sort_values("cash_conversion_cycle").iterrows():
    gap = row.get("inventory_growth_gap")
    gap_text = "not available" if gap is None or gap != gap else f"{float(gap):+.1%} versus sales growth"
    insight(
        f"{row['ticker']} · {format_value('cash_conversion_cycle', row['cash_conversion_cycle'])} cycle",
        f"Inventory turns {format_value('inventory_turnover', row['inventory_turnover'])}; inventory growth gap is {gap_text}. "
        f"Payables provide {format_value('payable_days', row['payable_days'])} of supplier financing.",
    )

st.caption("Days metrics use average beginning and ending balances. Missing components remain null; balance-sheet facts are never differenced.")
