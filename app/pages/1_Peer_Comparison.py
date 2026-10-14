from __future__ import annotations

import plotly.express as px
import streamlit as st

from app.data import latest_periods, load_or_stop
from app.ui import CHART_CONFIG, COMPANY_COLORS, LABELS, format_value, kpi_grid, page_setup, section, style_figure, winner


page_setup(
    "Peer Benchmarking",
    kicker="Performance analysis",
    description="Compare growth, margin quality, cash conversion, and liquidity on each issuer’s actual fiscal calendar.",
)
annual = latest_periods(load_or_stop("annual"), 5)
latest = annual.sort_values("period_end").groupby("ticker", as_index=False).tail(1)

metric_groups = {
    "Growth & profitability": ["revenue_growth", "gross_margin", "operating_margin", "net_margin"],
    "Cash generation": ["ocf_to_net_income", "free_cash_flow", "operating_cash_flow"],
    "Liquidity": ["current_ratio", "quick_ratio", "total_debt"],
}
group = st.segmented_control("Lens", list(metric_groups), default="Growth & profitability")
metric = st.selectbox("Metric", metric_groups[group], format_func=lambda item: LABELS[item])

leader = winner(latest, metric, highest=metric != "total_debt")
kpi_grid([
    {
        "label": f"Latest {LABELS[metric].lower()} leader",
        "value": f"{leader['ticker']} · {format_value(metric, leader[metric])}" if leader is not None else "N/A",
        "detail": "Latest completed issuer fiscal year",
        "tone": "good",
    },
    {
        "label": "Comparison window",
        "value": "5 years × 3 peers",
        "detail": "Calendar year of fiscal-period end; issuer FY retained",
        "tone": "blue",
    },
    {
        "label": "53-week handling",
        "value": f"{int(annual['is_53_week'].fillna(False).sum())} flagged",
        "detail": "Actual fiscal-day counts drive days metrics",
        "tone": "watch",
    },
])

section(f"{LABELS[metric]} trend", "Hover any point for fiscal labels, day counts, and 52/53-week context.")
figure = px.line(
    annual.sort_values("period_end"), x="period_end", y=metric, color="ticker", markers=True,
    color_discrete_map=COMPANY_COLORS,
    hover_data=["issuer_fiscal_year", "fiscal_days", "is_53_week"],
    labels={metric: LABELS[metric], "period_end": "Fiscal period end", "ticker": "Company"},
)
figure.update_traces(line_width=3, marker_size=9)
st.plotly_chart(style_figure(figure, metric), width="stretch", config=CHART_CONFIG)

section("Comparable annual evidence", "Nulls remain visible and every period retains a direct filing link.", "Control table")
display_columns = [
    "ticker", "period_end", "issuer_fiscal_year", "fiscal_days", "is_53_week", "revenue_growth",
    "gross_margin", "operating_margin", "net_margin", "ocf_to_net_income", "free_cash_flow", "source_url",
]
st.dataframe(
    annual[display_columns].sort_values(["period_end", "ticker"], ascending=[False, True]),
    hide_index=True, width="stretch",
    column_config={
        "ticker": "Company", "period_end": st.column_config.DateColumn("Period end"), "issuer_fiscal_year": "Issuer FY",
        "fiscal_days": "Days", "is_53_week": "53-week year",
        "revenue_growth": st.column_config.NumberColumn("Sales growth", format="percent"),
        "gross_margin": st.column_config.NumberColumn("Gross margin", format="percent"),
        "operating_margin": st.column_config.NumberColumn("Operating margin", format="percent"),
        "net_margin": st.column_config.NumberColumn("Net margin", format="percent"),
        "ocf_to_net_income": st.column_config.NumberColumn("OCF / NI", format="%.2fx"),
        "free_cash_flow": st.column_config.NumberColumn("Free cash flow", format="$%.0f"),
        "source_url": st.column_config.LinkColumn("Source", display_text="SEC filing"),
    },
)
