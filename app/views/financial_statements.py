"""Tab content for the primary statements view; rendered inside a merged page."""
from __future__ import annotations


import plotly.graph_objects as go
import streamlit as st


from app.data import latest_periods, load_or_stop
from app.ui import (
    CHART_CONFIG, COMPANY_COLORS, TONES, brand_theme, display_period_caption, format_value, kpi_grid, page_setup, section,
    statement_table, style_figure,
)


def render() -> None:
    st.caption('Income statement, balance sheet and cash flow in analyst layout, with year-over-year change, common-size view and a revenue-to-profit bridge.')
    annual = latest_periods(load_or_stop("annual"), 5)
    ticker = st.selectbox("Company", sorted(annual["ticker"].unique()), key="statement_company")
    brand_theme(ticker)
    company = annual[annual["ticker"] == ticker].sort_values("period_end").copy()
    company["gross_profit"] = company["net_sales"] - company["cost_of_sales"]
    latest = company.iloc[-1]
    st.caption(f"Latest: {display_period_caption(latest)}. Amounts are as most recently filed; missing lines are shown as — and never zero-filled.")

    view = st.segmented_control("Basis", ["USD millions", "Common-size"], default="USD millions", key="statement_basis")
    common = view == "Common-size"

    section("Income statement", "Common-size lines are percentages of total revenue.", "Statement 1")
    statement_table(company, [
        ("Revenue", None, "head", ""),
        ("Net sales", "net_sales", "row", "total_revenue"),
        ("Membership & other revenue", "membership_other_revenue", "row", "total_revenue"),
        ("Total revenue", "total_revenue", "total", "total_revenue"),
        ("Profit", None, "head", ""),
        ("Cost of sales", "cost_of_sales", "row", "total_revenue"),
        ("Gross profit (net sales − cost of sales)", "gross_profit", "total", "total_revenue"),
        ("Operating income", "operating_income", "total", "total_revenue"),
        ("Net income", "net_income", "total", "total_revenue"),
    ], common)

    section("Balance sheet", "Common-size lines are percentages of total assets.", "Statement 2")
    statement_table(company, [
        ("Assets", None, "head", ""),
        ("Cash and equivalents", "cash_and_cash_equivalents", "sub", "total_assets"),
        ("Short-term investments", "short_term_investments", "sub", "total_assets"),
        ("Receivables", "accounts_receivable_net_current", "sub", "total_assets"),
        ("Inventory", "inventory", "sub", "total_assets"),
        ("Total current assets", "current_assets", "total", "total_assets"),
        ("Total assets", "total_assets", "total", "total_assets"),
        ("Liabilities & equity", None, "head", ""),
        ("Accounts payable", "accounts_payable_current", "sub", "total_assets"),
        ("Total current liabilities", "current_liabilities", "total", "total_assets"),
        ("Total debt", "total_debt", "row", "total_assets"),
        ("Parent stockholders' equity", "stockholders_equity", "row", "total_assets"),
        ("Total equity (incl. non-controlling)", "total_equity", "total", "total_assets"),
    ], common)

    section("Cash flow", "Operating cash flow less capital expenditures gives free cash flow.", "Statement 3")
    statement_table(company, [
        ("Operating cash flow", "operating_cash_flow", "row", "total_revenue"),
        ("Capital expenditures", "capital_expenditures", "row", "total_revenue"),
        ("Free cash flow", "free_cash_flow", "total", "total_revenue"),
    ], common)

    section("From revenue to net income", "Costs between the reported lines are derived and labelled as such, not separately disclosed here.", "Margin bridge")
    needed = ["total_revenue", "cost_of_sales", "operating_income", "net_income"]
    if latest[needed].isna().any():
        st.info("The bridge needs total revenue, cost of sales, operating income and net income for the latest period.")
    else:
        revenue, cost = float(latest["total_revenue"]), float(latest["cost_of_sales"])
        op, ni = float(latest["operating_income"]), float(latest["net_income"])
        steps = [
            ("Total revenue", revenue, "absolute"),
            ("Cost of sales", -cost, "relative"),
            ("Operating costs (derived)", -(revenue - cost - op), "relative"),
            ("Operating income", op, "total"),
            ("Interest, taxes & other (derived)", -(op - ni), "relative"),
            ("Net income", ni, "total"),
        ]
        waterfall = go.Figure(go.Waterfall(
            x=[label for label, _, _ in steps], y=[value / 1e9 for _, value, _ in steps],
            measure=[kind for _, _, kind in steps],
            text=[f"${abs(value) / 1e9:,.1f}B" for _, value, _ in steps], textposition="outside",
            connector={"line": {"color": "#383835", "width": 1}},
            increasing={"marker": {"color": COMPANY_COLORS[ticker]}},
            decreasing={"marker": {"color": "#898781"}},
            totals={"marker": {"color": TONES["primary"]}},
        ))
        waterfall.update_layout(showlegend=False, yaxis_title="USD billions", xaxis_title="")
        waterfall.update_yaxes(range=[-0.06 * revenue / 1e9, revenue / 1e9 * 1.1])
        st.plotly_chart(style_figure(waterfall, height=400), width="stretch", config=CHART_CONFIG)
        kpi_grid([
            {"label": "Gross margin", "value": format_value("gross_margin", latest.get("gross_margin")), "detail": "Net sales basis", "tone": "blue"},
            {"label": "Operating margin", "value": format_value("operating_margin", latest.get("operating_margin")), "detail": "On total revenue", "tone": "good"},
            {"label": "Net margin", "value": format_value("net_margin", latest.get("net_margin")), "detail": "On total revenue", "tone": "good"},
        ])
    st.markdown(f"[Primary filing for the latest period]({latest['source_url']})")
