"""Tab content for the where the cash goes view; rendered inside a merged page."""
from __future__ import annotations


import pandas as pd
import plotly.express as px
import streamlit as st


from app.data import latest_periods, load_or_stop
from app.ui import (
    CHART_CONFIG, COMPANY_COLORS, COMPANY_ORDER, LABELS, TONES, format_value, insight, kpi_grid, page_setup, section,
    style_figure,
)


def render() -> None:
    st.caption('Follow operating cash flow through capex, dividends and buybacks, and see whether shareholder payouts are funded by free cash flow or by borrowing.')

    annual = latest_periods(load_or_stop("annual"), 5).sort_values(["ticker", "period_end"])
    ltm = load_or_stop("ltm")
    basis = st.segmented_control("Basis", ["Latest fiscal year", "Trailing 12 months"], default="Latest fiscal year", key="capital_basis")
    if basis == "Trailing 12 months":
        current = ltm[ltm["is_complete"].fillna(False)].copy()
        current["period_label"] = "LTM to " + pd.to_datetime(current["period_end"]).dt.strftime("%b %Y")
        if len(current) < len(ltm):
            st.warning("Some companies lack four complete quarters and are omitted from the trailing-12-month view.")
    else:
        current = annual.sort_values("period_end").groupby("ticker", as_index=False).tail(1).copy()
        current["period_label"] = "FY ended " + pd.to_datetime(current["period_end"]).dt.strftime("%b %Y")
    current["ticker"] = pd.Categorical(current["ticker"], categories=list(COMPANY_ORDER), ordered=True)
    current = current.sort_values("ticker").reset_index(drop=True)
    current["ticker"] = current["ticker"].astype(str)

    needed = ["operating_cash_flow", "capital_expenditures", "dividends_paid", "share_repurchases"]
    complete = current.dropna(subset=needed).copy()
    if complete.empty:
        st.info("Dividend and buyback data are not available for this basis yet.")
        return

    top_payout = complete.loc[complete["payout_ratio_fcf"].idxmax()] if complete["payout_ratio_fcf"].notna().any() else None
    top_buyback = complete.loc[complete["share_repurchases"].idxmax()]
    kpi_grid([
        {
            "label": "Highest payout of free cash flow",
            "value": f"{top_payout['ticker']} · {format_value('payout_ratio_fcf', top_payout['payout_ratio_fcf'])}" if top_payout is not None else "N/A",
            "detail": "Dividends plus buybacks ÷ free cash flow; above 100% means payouts exceeded FCF",
            "tone": "watch",
        },
        {
            "label": "Largest buyback",
            "value": f"{top_buyback['ticker']} · {format_value('share_repurchases', top_buyback['share_repurchases'])}",
            "detail": str(top_buyback["period_label"]),
            "tone": "blue",
        },
        {
            "label": "Companies shown",
            "value": f"{len(complete)} of {current['ticker'].nunique()}",
            "detail": "Only companies with all four cash-flow lines reported",
            "tone": "good",
        },
    ])

    section(
        "Uses of operating cash flow",
        "Each bar sums to operating cash flow. A negative remainder means payouts and capex exceeded operating cash flow.",
        "Sources and uses",
    )
    uses = pd.DataFrame({
        "ticker": complete["ticker"],
        "Capital expenditures": complete["capital_expenditures"] / 1e9,
        "Dividends": complete["dividends_paid"] / 1e9,
        "Buybacks": complete["share_repurchases"] / 1e9,
        "Remaining cash": complete["fcf_after_payouts"] / 1e9,
    })
    long = uses.melt(id_vars="ticker", var_name="Use", value_name="USD billions")
    chart = px.bar(
        long, x="ticker", y="USD billions", color="Use", barmode="relative",
        color_discrete_map={
            "Capital expenditures": TONES["muted"], "Dividends": TONES["secondary"],
            "Buybacks": TONES["accent"], "Remaining cash": TONES["primary"],
        },
        labels={"ticker": ""},
    )
    chart.update_layout(legend_title_text="")
    st.plotly_chart(style_figure(chart, height=400), width="stretch", config=CHART_CONFIG)
    st.caption("Remaining cash = operating cash flow − capex − dividends − buybacks (before debt flows, acquisitions and other items).")

    section(
        "Payout versus free cash flow",
        "Dividends plus buybacks as a share of free cash flow, by fiscal year. The dashed line marks 100%.",
        "Sustainability",
    )
    trend = annual.dropna(subset=["payout_ratio_fcf"])
    line = px.line(
        trend, x="period_end", y="payout_ratio_fcf", color="ticker", markers=True,
        color_discrete_map=COMPANY_COLORS,
        labels={"payout_ratio_fcf": LABELS["payout_ratio_fcf"], "period_end": "Fiscal period end", "ticker": "Company"},
    )
    line.add_hline(y=1.0, line_dash="dash", line_color="#898781")
    line.update_traces(line_width=3, marker_size=8)
    st.plotly_chart(style_figure(line, "payout_ratio_fcf"), width="stretch", config=CHART_CONFIG)
    st.caption("Fiscal years where free cash flow was zero or negative have no payout ratio and are not plotted.")

    section(
        "Cumulative five-year allocation",
        "Total operating cash flow over the displayed fiscal years and how it was deployed.",
        "Through the cycle",
    )
    cumulative = (
        annual.dropna(subset=needed)
        .groupby("ticker")[["operating_cash_flow", "capital_expenditures", "dividends_paid", "share_repurchases"]]
        .sum()
        .reset_index()
    )
    cumulative["years"] = annual.dropna(subset=needed).groupby("ticker")["period_end"].count().values
    cumulative["Capex share"] = cumulative["capital_expenditures"] / cumulative["operating_cash_flow"]
    cumulative["Dividend share"] = cumulative["dividends_paid"] / cumulative["operating_cash_flow"]
    cumulative["Buyback share"] = cumulative["share_repurchases"] / cumulative["operating_cash_flow"]
    absolute = pd.DataFrame({
        "ticker": cumulative["ticker"],
        "Capital expenditures": cumulative["capital_expenditures"] / 1e9,
        "Dividends": cumulative["dividends_paid"] / 1e9,
        "Buybacks": cumulative["share_repurchases"] / 1e9,
        "Remaining cash": (
            cumulative["operating_cash_flow"] - cumulative["capital_expenditures"]
            - cumulative["dividends_paid"] - cumulative["share_repurchases"]
        ) / 1e9,
    })
    stack = px.bar(
        absolute.melt(id_vars="ticker", var_name="Use", value_name="USD billions"),
        x="ticker", y="USD billions", color="Use", barmode="relative",
        color_discrete_map={
            "Capital expenditures": TONES["muted"], "Dividends": TONES["secondary"],
            "Buybacks": TONES["accent"], "Remaining cash": TONES["primary"],
        },
        labels={"ticker": ""},
    )
    stack.update_layout(legend_title_text="")
    st.plotly_chart(style_figure(stack, height=360), width="stretch", config=CHART_CONFIG)
    st.caption(
        "A bar's positive segments sum to the cash deployed; a negative 'remaining cash' means capex plus payouts exceeded operating "
        "cash flow over the period, so the gap was funded from cash on hand or borrowing."
    )

    section("Reading the numbers", "Computed from the reported cash-flow lines; interpret alongside the caveats below.", "Analyst interpretation")
    columns = st.columns(2)
    for index, (_, row) in enumerate(cumulative.iterrows()):
        latest_row = annual[annual["ticker"] == row["ticker"]].iloc[-1]
        borrowing = latest_row.get("net_debt_issuance")
        borrowing_text = (
            "net debt issuance was not reported"
            if borrowing is None or pd.isna(borrowing)
            else f"net debt {'issued' if borrowing >= 0 else 'repaid'} was {format_value('net_debt_issuance', abs(borrowing))} in the latest year"
        )
        with columns[index % 2]:
            insight(
                f"{row['ticker']} · {row['years']:.0f}-year payouts {format_value('payout_ratio_fcf', (row['dividends_paid'] + row['share_repurchases']) / max(row['operating_cash_flow'] - row['capital_expenditures'], 1))} of FCF",
                f"{row['Capex share']:.0%} of operating cash flow went to capex, {row['Dividend share']:.0%} to dividends and "
                f"{row['Buyback share']:.0%} to buybacks; {borrowing_text}.",
            )

    st.caption(
        "Dividends are common-stock dividends paid; buybacks are payments to repurchase common stock. Costco's fiscal 2024 includes "
        "a large special dividend. Debt flows come from long-term debt issuance and repayment lines only, so net debt issuance excludes "
        "short-term borrowing and lease principal."
    )
