from __future__ import annotations

import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data import latest_periods, load_or_stop
from app.ui import CHART_CONFIG, COMPANY_COLORS, LABELS, page_setup, section, style_figure


page_setup(
    "Exploratory Analysis",
    kicker="Pattern discovery",
    description=(
        "Explore relationships and distributions that may warrant deeper investigation. "
        "These views identify signals; they do not imply causation."
    ),
)

annual = latest_periods(load_or_stop("annual"), 5).sort_values(["ticker", "period_end"])
quarterly = latest_periods(load_or_stop("quarterly"), 12).sort_values(["ticker", "period_end"])

section(
    "Growth and profitability map",
    "Periods in the upper-right combine stronger net-sales growth with higher operating margins.",
    "Strategic positioning",
)
growth_margin = px.scatter(
    annual,
    x="revenue_growth",
    y="operating_margin",
    color="ticker",
    symbol="ticker",
    color_discrete_map=COMPANY_COLORS,
    hover_data={
        "period_end": "|%Y-%m-%d",
        "issuer_fiscal_year": True,
        "revenue_growth": ":.1%",
        "operating_margin": ":.1%",
        "free_cash_flow": ":$,.0f",
    },
    labels={
        "revenue_growth": "Net-sales growth",
        "operating_margin": "Operating margin",
        "ticker": "Company",
    },
)
growth_margin.update_traces(marker=dict(size=11, line=dict(width=1.5, color="white")))
growth_margin.update_xaxes(tickformat=".1%", zeroline=True, zerolinecolor="#383835")
growth_margin.update_yaxes(tickformat=".1%")
st.plotly_chart(style_figure(growth_margin, None, 430), width="stretch", config=CHART_CONFIG)

left, right = st.columns(2)
with left:
    section(
        "Operating-cycle relationship",
        "Compare inventory days with the resulting cash conversion cycle across annual periods.",
        "Working capital",
    )
    cycle = px.scatter(
        annual,
        x="days_inventory_outstanding",
        y="cash_conversion_cycle",
        color="ticker",
        symbol="ticker",
        color_discrete_map=COMPANY_COLORS,
        hover_data={"period_end": "|%Y-%m-%d", "payable_days": ":.1f", "inventory_turnover": ":.2f"},
        labels={
            "days_inventory_outstanding": "Inventory days",
            "cash_conversion_cycle": "Cash conversion cycle (days)",
            "ticker": "Company",
        },
    )
    cycle.update_traces(marker=dict(size=10, line=dict(width=1.2, color="white")))
    st.plotly_chart(style_figure(cycle, "cash_conversion_cycle", 390), width="stretch", config=CHART_CONFIG)

with right:
    section(
        "Quarterly distribution",
        "View the spread, median, and outlying observations across the latest twelve quarters.",
        "Variability",
    )
    distribution_metric = st.selectbox(
        "Distribution metric",
        ["revenue_growth", "gross_margin", "operating_margin", "net_margin"],
        format_func=lambda item: LABELS[item],
    )
    distribution = px.box(
        quarterly,
        x="ticker",
        y=distribution_metric,
        color="ticker",
        points="all",
        color_discrete_map=COMPANY_COLORS,
        hover_data=["period_end", "issuer_fiscal_year", "issuer_fiscal_period"],
        labels={distribution_metric: LABELS[distribution_metric], "ticker": "Company"},
    )
    distribution.update_layout(showlegend=False)
    distribution.update_traces(jitter=.18, marker=dict(size=6, opacity=.7))
    st.plotly_chart(style_figure(distribution, distribution_metric, 390), width="stretch", config=CHART_CONFIG)

section(
    "How to use this page",
    "Treat clusters, directional shifts, and outliers as prompts for filing review—not as standalone conclusions.",
    "Analyst guidance",
)
st.info(
    "The executive and peer pages contain the decision-ready findings. This exploratory view is intentionally separate so analytical discovery does not crowd the management narrative."
)
