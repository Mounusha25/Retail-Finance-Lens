from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from app.data import latest_periods, load_or_stop
from app.ui import (
    CHART_CONFIG, COMPANY_COLORS, LABELS, format_value, insight,
    kpi_grid, page_setup, section, style_figure, winner,
)


page_setup(
    "RetailScope",
    kicker="Executive overview",
    description=(
        "Financial performance and working-capital intelligence across Walmart, Target, and Costco—"
        "with every conclusion traced to SEC filings."
    ),
)

peer = load_or_stop("peer").sort_values("ticker").reset_index(drop=True)
annual = latest_periods(load_or_stop("annual"), 5)
quality = load_or_stop("quality")

growth_leader = winner(peer, "revenue_growth")
cash_leader = winner(peer, "free_cash_flow")
inventory_leader = winner(peer, "inventory_turnover")
cycle_leader = winner(peer, "cash_conversion_cycle", highest=False)

section(
    "Current peer position",
    "Latest completed issuer fiscal years; prior periods remain available in the detailed views.",
    "Executive snapshot",
)
kpi_grid([
    {
        "label": "Growth leader",
        "value": f"{growth_leader['ticker']} · {format_value('revenue_growth', growth_leader['revenue_growth'])}" if growth_leader is not None else "N/A",
        "detail": "Latest issuer fiscal year; net sales basis",
        "tone": "good",
    },
    {
        "label": "Cash-generation leader",
        "value": f"{cash_leader['ticker']} · {format_value('free_cash_flow', cash_leader['free_cash_flow'])}" if cash_leader is not None else "N/A",
        "detail": "Operating cash flow less capital expenditures",
        "tone": "blue",
    },
    {
        "label": "Inventory leader",
        "value": f"{inventory_leader['ticker']} · {format_value('inventory_turnover', inventory_leader['inventory_turnover'])}" if inventory_leader is not None else "N/A",
        "detail": "Cost of sales divided by average inventory",
        "tone": "good",
    },
    {
        "label": "Shortest cash cycle",
        "value": f"{cycle_leader['ticker']} · {format_value('cash_conversion_cycle', cycle_leader['cash_conversion_cycle'])}" if cycle_leader is not None else "N/A",
        "detail": "Receivable days + inventory days − payable days",
        "tone": "watch",
    },
])

section(
    "Management readout",
    "A concise interpretation of the latest comparable operating and cash-flow signals.",
    "Analyst assessment",
)

cost = peer.loc[peer["ticker"] == "COST"].iloc[0]
tgt = peer.loc[peer["ticker"] == "TGT"].iloc[0]
wmt = peer.loc[peer["ticker"] == "WMT"].iloc[0]

left, middle, right = st.columns(3)
with left:
    insight(
        "Costco — strongest operating momentum",
        f"Net sales grew {format_value('revenue_growth', cost['revenue_growth'])}; "
        f"inventory turned {format_value('inventory_turnover', cost['inventory_turnover'])} with a "
        f"{format_value('cash_conversion_cycle', cost['cash_conversion_cycle'])} cash cycle.",
    )
with middle:
    insight(
        "Walmart — largest cash engine",
        f"Generated {format_value('free_cash_flow', wmt['free_cash_flow'])} of free cash flow and converted "
        f"earnings to operating cash at {format_value('ocf_to_net_income', wmt['ocf_to_net_income'])}.",
    )
with right:
    direction = "contracted" if float(tgt["revenue_growth"]) < 0 else "grew"
    insight(
        "Target — profitability watch",
        f"Net sales {direction} {abs(float(tgt['revenue_growth'])):.1%}; inventory turnover of "
        f"{format_value('inventory_turnover', tgt['inventory_turnover'])} trails both peers.",
    )

section("Peer scorecard", "Compare current performance across the metrics most relevant to finance leadership.")
profit_tab, cash_tab, operations_tab = st.tabs(["Growth & margins", "Cash conversion", "Working capital"])

with profit_tab:
    metric = st.selectbox(
        "Performance metric",
        ["revenue_growth", "gross_margin", "operating_margin", "net_margin"],
        format_func=lambda item: LABELS[item],
        key="executive_profit_metric",
    )
    chart = px.bar(
        peer, x="ticker", y=metric, color="ticker", text=metric,
        color_discrete_map=COMPANY_COLORS,
        labels={metric: LABELS[metric], "ticker": ""},
    )
    chart.update_traces(texttemplate="%{text:.1%}", textposition="outside", cliponaxis=False)
    chart.update_layout(showlegend=False)
    st.plotly_chart(style_figure(chart, metric, 360), width="stretch", config=CHART_CONFIG)

with cash_tab:
    cash_long = peer[["ticker", "operating_cash_flow", "free_cash_flow"]].melt(
        id_vars="ticker", var_name="metric", value_name="value"
    )
    chart = px.bar(
        cash_long, x="ticker", y="value", color="metric", barmode="group",
        color_discrete_map={"operating_cash_flow": "#2563EB", "free_cash_flow": "#0D9488"},
        labels={"value": "USD", "ticker": "", "metric": ""},
    )
    chart.update_layout(legend_title_text="")
    st.plotly_chart(style_figure(chart, "free_cash_flow", 360), width="stretch", config=CHART_CONFIG)

with operations_tab:
    operations = peer[["ticker", "days_inventory_outstanding", "payable_days", "cash_conversion_cycle"]].melt(
        id_vars="ticker", var_name="metric", value_name="days"
    )
    chart = px.bar(
        operations, x="ticker", y="days", color="metric", barmode="group",
        color_discrete_map={
            "days_inventory_outstanding": "#2563EB", "payable_days": "#7C3AED", "cash_conversion_cycle": "#0D9488"
        }, labels={"days": "Days", "ticker": "", "metric": ""},
    )
    st.plotly_chart(style_figure(chart, "cash_conversion_cycle", 360), width="stretch", config=CHART_CONFIG)

section("Latest-period evidence", "Every figure retains its issuer fiscal label, period end, and primary filing link.", "Control & traceability")
table = peer[[
    "ticker", "issuer_fiscal_year", "period_end", "revenue_growth", "gross_margin", "operating_margin",
    "ocf_to_net_income", "free_cash_flow", "inventory_turnover", "cash_conversion_cycle", "source_url",
]].copy()
st.dataframe(
    table,
    hide_index=True,
    width="stretch",
    column_config={
        "ticker": "Company", "issuer_fiscal_year": "Issuer FY", "period_end": st.column_config.DateColumn("Period end"),
        "revenue_growth": st.column_config.NumberColumn("Sales growth", format="percent"),
        "gross_margin": st.column_config.NumberColumn("Gross margin", format="percent"),
        "operating_margin": st.column_config.NumberColumn("Operating margin", format="percent"),
        "ocf_to_net_income": st.column_config.NumberColumn("OCF / NI", format="%.2fx"),
        "free_cash_flow": st.column_config.NumberColumn("FCF", format="$%.0f"),
        "inventory_turnover": st.column_config.NumberColumn("Inventory turns", format="%.2fx"),
        "cash_conversion_cycle": st.column_config.NumberColumn("CCC days", format="%.1f"),
        "source_url": st.column_config.LinkColumn("SEC filing", display_text="Open filing"),
    },
)

status_counts = quality["status"].value_counts()
problem_count = int(status_counts.get("warning", 0) + status_counts.get("error", 0))
if problem_count:
    st.warning(f"Latest validation run contains {problem_count} flagged checks. Review Methodology & Data Quality for provenance and impact.")
else:
    st.success("All checks in the latest validation run passed.")
