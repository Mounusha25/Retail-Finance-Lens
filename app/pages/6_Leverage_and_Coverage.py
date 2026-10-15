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

from app.data import latest_periods, load_or_stop
from app.ui import (
    CHART_CONFIG, COMPANY_COLORS, COMPANY_ORDER, LABELS, TONES, format_value, insight, kpi_grid, page_setup, section,
    style_figure, winner,
)


page_setup(
    "Leverage & Coverage",
    kicker="Balance-sheet strength",
    description=(
        "EBITDA, net debt, interest coverage and lease-adjusted returns: how much debt each retailer carries, "
        "how comfortably it services it, and how leases change the picture."
    ),
)

annual = latest_periods(load_or_stop("annual"), 5).sort_values(["ticker", "period_end"])
ltm = load_or_stop("ltm")
basis = st.segmented_control("Basis", ["Latest fiscal year", "Trailing 12 months"], default="Latest fiscal year")
if basis == "Trailing 12 months":
    current = ltm[ltm["is_complete"].fillna(False)].copy()
    stamp = pd.to_datetime(current["period_end"]).dt.strftime("%b %Y")
    current["period_label"] = "LTM to " + stamp
else:
    current = annual.groupby("ticker", as_index=False).tail(1).copy()
    current["period_label"] = "FY ended " + pd.to_datetime(current["period_end"]).dt.strftime("%b %Y")
current["ticker"] = pd.Categorical(current["ticker"], categories=list(COMPANY_ORDER), ordered=True)
current = current.sort_values("ticker").reset_index(drop=True)
current["ticker"] = current["ticker"].astype(str)

lowest = winner(current, "net_debt_to_ebitda", highest=False)
cover = winner(current, "interest_coverage")
kpi_grid([
    {
        "label": "Lowest net debt / EBITDA",
        "value": f"{lowest['ticker']} · {format_value('net_debt_to_ebitda', lowest['net_debt_to_ebitda'])}" if lowest is not None else "N/A",
        "detail": "Negative means cash exceeds debt (net cash)",
        "tone": "good",
    },
    {
        "label": "Strongest interest coverage",
        "value": f"{cover['ticker']} · {format_value('interest_coverage', cover['interest_coverage'])}" if cover is not None else "N/A",
        "detail": "Operating income ÷ cash interest paid",
        "tone": "blue",
    },
    {
        "label": "Interest data available",
        "value": f"{int(current['interest_coverage'].notna().sum())} of {len(current)}",
        "detail": "Quarterly filings often omit interest paid, so coverage can be null on a trailing basis",
        "tone": "watch",
    },
])

section("Net debt relative to earnings", "Net debt ÷ EBITDA by fiscal year. Below zero means the company holds more cash than debt.", "Leverage")
leverage = annual.dropna(subset=["net_debt_to_ebitda"])
line = px.line(
    leverage, x="period_end", y="net_debt_to_ebitda", color="ticker", markers=True,
    color_discrete_map=COMPANY_COLORS,
    labels={"net_debt_to_ebitda": "Net debt / EBITDA (×)", "period_end": "Fiscal period end", "ticker": "Company"},
)
line.add_hline(y=0, line_color="#898781")
line.update_traces(line_width=3, marker_size=8)
st.plotly_chart(style_figure(line), width="stretch", config=CHART_CONFIG)
st.caption("Net debt = debt (current, long-term and short-term borrowings) − cash and equivalents; short-term investments are not netted. EBITDA = operating income + depreciation and amortization.")

section("Can they service it?", "Operating income ÷ cash interest paid. The scale is logarithmic because Costco's coverage dwarfs the others.", "Coverage")
coverage = current.dropna(subset=["interest_coverage"])
if coverage.empty:
    st.info("Interest paid is not reported for this basis.")
else:
    bars = go.Figure(go.Bar(
        x=coverage["ticker"], y=coverage["interest_coverage"],
        marker_color=[COMPANY_COLORS[t] for t in coverage["ticker"]],
        text=[f"{v:,.1f}×" for v in coverage["interest_coverage"]], textposition="outside",
    ))
    bars.update_yaxes(type="log", title="Interest coverage (×, log scale)")
    st.plotly_chart(style_figure(bars, height=340), width="stretch", config=CHART_CONFIG)
    st.caption("Cash interest paid can be lumpy (bond coupon timing, capitalized interest), so single-year coverage is indicative, not precise.")

section(
    "Leases change the answer",
    "Reported ROIC ignores operating leases. The adjusted view adds lease liabilities to capital and adds back the interest embedded in lease cost.",
    "Lease adjustment",
)
lease = annual.groupby("ticker", as_index=False).tail(1).dropna(subset=["roic", "lease_adjusted_roic"]).copy()
if lease.empty:
    st.info("Lease data are not available.")
else:
    comparison = go.Figure()
    comparison.add_bar(name="Reported ROIC", x=lease["ticker"], y=lease["roic"], marker_color=TONES["muted"],
                       text=[f"{v:.1%}" for v in lease["roic"]], textposition="outside")
    comparison.add_bar(name="Lease-adjusted ROIC", x=lease["ticker"], y=lease["lease_adjusted_roic"], marker_color=TONES["accent"],
                       text=[f"{v:.1%}" for v in lease["lease_adjusted_roic"]], textposition="outside")
    comparison.update_layout(barmode="group")
    comparison.update_yaxes(tickformat=".0%", rangemode="tozero")
    st.plotly_chart(style_figure(comparison, height=360), width="stretch", config=CHART_CONFIG)
    st.caption(
        "Implied lease interest = average operating lease liability × the weighted-average discount rate each company discloses. "
        "Finance leases are already inside debt for some issuers (Target) and outside it for others, so treat debt comparisons with care."
    )

section("Capital structure detail", "Latest fiscal year, USD billions.", "Control table")
table = annual.groupby("ticker", as_index=False).tail(1)[[
    "ticker", "period_end", "total_debt", "operating_lease_liability", "lease_adjusted_debt", "net_debt", "ebitda",
    "net_debt_to_ebitda", "interest_coverage", "roic", "lease_adjusted_roic", "source_url",
]].copy()
for column in ("total_debt", "operating_lease_liability", "lease_adjusted_debt", "net_debt", "ebitda"):
    table[column] = table[column] / 1e9
st.dataframe(
    table, hide_index=True, width="stretch",
    column_config={
        "ticker": "Company", "period_end": st.column_config.DateColumn("Period end"),
        "total_debt": st.column_config.NumberColumn("Debt ($B)", format="%.1f"),
        "operating_lease_liability": st.column_config.NumberColumn("Op. leases ($B)", format="%.1f"),
        "lease_adjusted_debt": st.column_config.NumberColumn("Lease-adj. debt ($B)", format="%.1f"),
        "net_debt": st.column_config.NumberColumn("Net debt ($B)", format="%.1f"),
        "ebitda": st.column_config.NumberColumn("EBITDA ($B)", format="%.1f"),
        "net_debt_to_ebitda": st.column_config.NumberColumn("Net debt / EBITDA", format="%.2fx"),
        "interest_coverage": st.column_config.NumberColumn("Coverage", format="%.1fx"),
        "roic": st.column_config.NumberColumn("ROIC", format="percent"),
        "lease_adjusted_roic": st.column_config.NumberColumn("Lease-adj. ROIC", format="percent"),
        "source_url": st.column_config.LinkColumn("Source", display_text="SEC filing"),
    },
)

section("Reading the numbers", "Computed from the latest fiscal year; see the caveats above.", "Analyst interpretation")
columns = st.columns(2)
for index, (_, row) in enumerate(annual.groupby("ticker", as_index=False).tail(1).sort_values("ticker").iterrows()):
    with columns[index % 2]:
        if pd.notna(row["net_debt"]) and row["net_debt"] < 0:
            stance = f"net cash of {format_value('net_debt', abs(row['net_debt']))}"
        elif pd.notna(row["net_debt"]):
            stance = f"net debt of {format_value('net_debt', row['net_debt'])} ({format_value('net_debt_to_ebitda', row['net_debt_to_ebitda'])} EBITDA)"
        else:
            stance = "net debt unavailable"
        gap = (
            f"; leases lower ROIC from {format_value('roic', row['roic'])} to {format_value('lease_adjusted_roic', row['lease_adjusted_roic'])}"
            if pd.notna(row["roic"]) and pd.notna(row["lease_adjusted_roic"]) else ""
        )
        insight(
            f"{row['ticker']} · {stance}",
            f"Interest coverage {format_value('interest_coverage', row['interest_coverage'])}{gap}.",
        )
