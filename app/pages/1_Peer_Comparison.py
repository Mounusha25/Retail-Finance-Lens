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
from app.ui import CHART_CONFIG, COMPANY_COLORS, LABELS, PERCENT_METRICS, format_value, kpi_grid, page_setup, section, style_figure, winner


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
        "value": f"5 years × {annual['ticker'].nunique()} peers",
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

section(
    f"{LABELS[metric]}: five-year range",
    "Each bar spans the lowest to highest value in the window; the marker is the latest fiscal year. Wide bars mean volatile results.",
    "Football field",
)
ranges = annual.groupby("ticker")[metric].agg(["min", "max"]).join(latest.set_index("ticker")[metric].rename("latest")).reset_index()
ranges = ranges.dropna(subset=["min", "max"]).sort_values("latest", ascending=False)
field = go.Figure()
for _, row in ranges.iterrows():
    colour = COMPANY_COLORS.get(row["ticker"], "#898781")
    field.add_trace(go.Scatter(
        x=[row["min"], row["max"]], y=[row["ticker"], row["ticker"]], mode="lines",
        line=dict(color=colour, width=14), opacity=0.55, showlegend=False, hoverinfo="skip",
    ))
    field.add_trace(go.Scatter(
        x=[row["latest"]], y=[row["ticker"]], mode="markers+text", showlegend=False,
        marker=dict(color="#f0efec", size=12, line=dict(color=colour, width=3)),
        text=[format_value(metric, row["latest"])], textposition="top center",
    ))
field.update_layout(yaxis=dict(autorange="reversed"), xaxis_title=LABELS[metric], hovermode="closest")
styled = style_figure(field, None, 300)
lo, hi = float(ranges["min"].min()), float(ranges["max"].max())
pad = (hi - lo) * 0.06 or 0.01
styled.update_xaxes(tickformat=".1%" if metric in PERCENT_METRICS else None, gridcolor="#2c2c2a", range=[lo - pad, hi + pad])
styled.update_layout(margin=dict(l=64, r=24, t=56, b=26))
st.plotly_chart(styled, width="stretch", config=CHART_CONFIG)

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
