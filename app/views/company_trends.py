"""Tab content for the issuer analysis view; rendered inside a merged page."""
from __future__ import annotations


import plotly.express as px
import streamlit as st


from app.data import latest_periods, load_or_stop
from app.ui import (
    CHART_CONFIG, COMPANY_COLORS, LABELS, brand_theme, display_period_caption,
    format_value, kpi_grid, page_setup, section, style_figure,
)


def render() -> None:
    st.caption('Move from the peer snapshot into five annual periods or the latest twelve standalone quarters with filing lineage.')
    frequency = st.segmented_control("Frequency", ["Annual", "Quarterly"], default="Annual", key="trend_frequency")
    view = "annual" if frequency == "Annual" else "quarterly"
    count = 5 if frequency == "Annual" else 12
    frame = latest_periods(load_or_stop(view), count)
    ticker = st.selectbox("Company", sorted(frame["ticker"].unique()), key="trend_company")
    brand_theme(ticker)
    company = frame[frame["ticker"] == ticker].sort_values("period_end")
    latest = company.iloc[-1]

    kpi_grid([
        {"label": "Latest net sales", "value": format_value("net_sales", latest["net_sales"]), "detail": display_period_caption(latest), "tone": "blue"},
        {"label": "Sales growth", "value": format_value("revenue_growth", latest["revenue_growth"]), "detail": "Year-over-year comparable period", "tone": "good" if float(latest["revenue_growth"]) >= 0 else "red"},
        {"label": "Operating margin", "value": format_value("operating_margin", latest["operating_margin"]), "detail": "Operating income / total revenue", "tone": "good"},
        {"label": "Free cash flow", "value": format_value("free_cash_flow", latest["free_cash_flow"]), "detail": "OCF less capital expenditures", "tone": "good"},
    ])

    growth_tab, cash_tab, balance_tab = st.tabs(["Growth & margins", "Cash generation", "Balance sheet"])
    with growth_tab:
        section("Growth and margin trajectory", "Revenue growth can be compared directly with gross and operating margin direction.")
        metric = st.selectbox("Metric", ["revenue_growth", "gross_margin", "operating_margin", "net_margin"], format_func=lambda item: LABELS[item], key="trend_profit")
        figure = px.line(company, x="period_end", y=metric, markers=True, color_discrete_sequence=[COMPANY_COLORS[ticker]], labels={metric: LABELS[metric], "period_end": "Fiscal period end"})
        figure.update_traces(line_width=4, marker_size=10)
        st.plotly_chart(style_figure(figure, metric), width="stretch", config=CHART_CONFIG)

    with cash_tab:
        section("Profit-to-cash conversion", "Compare operating cash flow and free cash flow, then inspect OCF relative to net income.")
        cash = company[["period_end", "operating_cash_flow", "free_cash_flow"]].melt(id_vars="period_end", var_name="metric", value_name="value")
        cash["metric"] = cash["metric"].map(LABELS)
        figure = px.bar(cash, x="period_end", y="value", color="metric", barmode="group", color_discrete_map={LABELS["operating_cash_flow"]: "#c3c2b7", LABELS["free_cash_flow"]: "#fab219"}, labels={"value": "USD", "period_end": "Fiscal period end", "metric": ""})
        st.plotly_chart(style_figure(figure, "free_cash_flow"), width="stretch", config=CHART_CONFIG)

    with balance_tab:
        section("Inventory and leverage", "Track capital tied up in inventory alongside reported debt.")
        balance_options = [
            item for item in ["inventory", "inventory_turnover", "cash_conversion_cycle", "total_debt", "current_ratio"]
            if company[item].notna().any()
        ]
        metric = st.selectbox("Metric", balance_options, format_func=lambda item: LABELS[item], key="trend_balance")
        figure = px.line(company, x="period_end", y=metric, markers=True, color_discrete_sequence=[COMPANY_COLORS[ticker]], labels={metric: LABELS[metric], "period_end": "Fiscal period end"})
        figure.update_traces(line_width=4, marker_size=10)
        st.plotly_chart(style_figure(figure, metric), width="stretch", config=CHART_CONFIG)

    section("Filing lineage", "Open the primary filing supporting any displayed period.", "Control & traceability")
    columns = ["period_end", "issuer_fiscal_year"]
    if frequency == "Quarterly":
        columns.extend(["issuer_fiscal_period", "is_derived"])
    columns.extend(["net_sales", "operating_income", "operating_cash_flow", "accession_number", "source_url"])
    st.dataframe(
        company[columns].sort_values("period_end", ascending=False), hide_index=True, width="stretch",
        column_config={
            "period_end": st.column_config.DateColumn("Period end"), "issuer_fiscal_year": "Issuer FY",
            "issuer_fiscal_period": "Fiscal quarter", "is_derived": "Derived quarter",
            "net_sales": st.column_config.NumberColumn("Net sales", format="$%.0f"),
            "operating_income": st.column_config.NumberColumn("Operating income", format="$%.0f"),
            "operating_cash_flow": st.column_config.NumberColumn("Operating cash flow", format="$%.0f"),
            "accession_number": "SEC accession",
            "source_url": st.column_config.LinkColumn("Filing", display_text="Open SEC filing"),
        },
    )
