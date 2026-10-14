from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data import latest_periods, load_or_stop
from app.ui import kpi_grid, page_setup, section


page_setup(
    "Data Quality & Methodology",
    kicker="Governance and controls",
    description="See exactly what was sourced, derived, unavailable, or flagged—and how every business metric is defined.",
)
annual_all = load_or_stop("annual")
quarterly_all = load_or_stop("quarterly")
annual = latest_periods(annual_all, 5)
quarterly = latest_periods(quarterly_all, 12)
quality = load_or_stop("quality")

passed = int((quality["status"] == "passed").sum())
warnings = int((quality["status"] == "warning").sum())
errors = int((quality["status"] == "error").sum())
kpi_grid([
    {"label": "Displayed annual periods", "value": f"{len(annual)} / {5 * annual['ticker'].nunique()}", "detail": f"Five periods for each of {annual['ticker'].nunique()} companies", "tone": "good"},
    {"label": "Displayed quarters", "value": f"{len(quarterly)} / {12 * quarterly['ticker'].nunique()}", "detail": "Twelve quarters for each company", "tone": "blue"},
    {"label": "Checks passed", "value": str(passed), "detail": "Latest validation run only", "tone": "good"},
    {"label": "Flags requiring context", "value": f"{warnings} warnings · {errors} errors", "detail": "Missing data is visible and never zero-filled", "tone": "watch" if not errors else "red"},
])

section("Coverage by company", "Completeness is measured on the exact periods shown in the dashboard.")
coverage_rows = []
critical = ["net_sales", "total_revenue", "operating_margin", "free_cash_flow", "inventory_turnover", "cash_conversion_cycle"]
for ticker in sorted(annual["ticker"].unique()):
    annual_company = annual[annual["ticker"] == ticker]
    quarter_company = quarterly[quarterly["ticker"] == ticker]
    available = int(annual_company[critical].notna().sum().sum())
    possible = len(annual_company) * len(critical)
    coverage_rows.append({
        "Company": ticker,
        "Annual periods": len(annual_company),
        "Quarterly periods": len(quarter_company),
        "Critical annual fields": f"{available}/{possible}",
        "Latest period": annual_company["period_end"].max(),
    })
st.dataframe(pd.DataFrame(coverage_rows), hide_index=True, width="stretch")

definitions_tab, lineage_tab, checks_tab = st.tabs(["Metric definitions", "Lineage policy", "Validation results"])
with definitions_tab:
    st.markdown(
        """
        **Growth and profitability**

        - Net-sales growth = current net sales / prior comparable-period net sales − 1.
        - Gross margin = (net sales − cost of sales) / net sales.
        - Operating and net margins use total revenue, including membership and other revenue.

        **Cash and working capital**

        - Free cash flow = operating cash flow − capital expenditures; capex is stored as a positive outflow.
        - Inventory, receivable, and payable days use average beginning/ending balances and actual fiscal days.
        - Cash conversion cycle = receivable days + inventory days − payable days.
        - Quick ratio is null when any required source component is unavailable; missing investments are not assumed to be zero.
        """
    )
with lineage_tab:
    st.markdown(
        """
        - SEC Submissions, Company Facts, and primary inline-XBRL filing documents are preserved as gzip files and compressed database payloads.
        - Dimensional inline-XBRL separates Costco membership revenue and Target product versus other revenue.
        - Kroger does not tag net inventory; it is derived as FIFO inventory less the LIFO reserve at the same balance-sheet date and flagged as derived. Its cost of sales excludes depreciation and rent-type items.
        - Latest-filed values power analytical views; original and amended versions remain in `financial_facts`.
        - Standalone quarters are preferred. Q2/Q3 may be derived from cumulative disclosures; Q4 is annual less nine months.
        - Point-in-time balance-sheet facts are never differenced. Fifty-three-week periods remain visibly flagged.
        """
    )
with checks_tab:
    status = st.multiselect("Status", ["error", "warning", "passed"], default=["error", "warning"])
    filtered = quality[quality["status"].isin(status)]
    if filtered.empty:
        st.success("No checks match the selected status.")
    else:
        st.dataframe(
            filtered.sort_values(["status", "ticker", "period_end"], ascending=[True, True, False]),
            hide_index=True, width="stretch",
            column_config={"period_end": st.column_config.DateColumn("Period end"), "created_at": st.column_config.DatetimeColumn("Checked at")},
        )

st.info("A warning communicates an unavailable or ambiguous filing field. It does not silently replace that field with zero.")
