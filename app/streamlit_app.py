from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Streamlit Community Cloud executes this file with ``app/`` as the import
# root. Add the repository root explicitly so ``app`` resolves identically in
# local, Docker, and hosted environments.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data import latest_periods, load_or_stop
from app.scoring import DEFAULT_WEIGHTS, PILLARS, latest_and_prior, pillar_leaders, score_peers, with_fcf_margin
from app.ui import (
    CHART_CONFIG, COMPANY_COLORS, LABELS, TONES, _fmt_delta, format_value, kpi_grid, page_setup, rank_heatmap,
    score_table, section, style_figure, verdict,
)


page_setup(
    "Retail Finance Lens",
    kicker="Executive overview",
    description=(
        "Financial performance and working-capital intelligence across Walmart, Target, Costco, and Kroger—"
        "with every conclusion traced to SEC filings."
    ),
)

annual = latest_periods(load_or_stop("annual"), 5)
quality = load_or_stop("quality")
fiscal_peer = load_or_stop("peer").sort_values("ticker").reset_index(drop=True)

basis = st.segmented_control(
    "Comparison basis", ["Trailing 12 months (aligned)", "Latest fiscal year"], default="Trailing 12 months (aligned)",
    help="Fiscal years end at different times (Costco in August, the others in January). The trailing-12-month basis "
         "measures every company over the same twelve months.",
)
ltm_peer = load_or_stop("ltm").sort_values("ticker").reset_index(drop=True)
use_ltm = basis != "Latest fiscal year"
if use_ltm and not bool(ltm_peer["is_complete"].fillna(False).all()):
    st.warning("Some companies lack four complete quarters; showing the latest fiscal year for everyone instead.")
    use_ltm = False
peer = ltm_peer if use_ltm else fiscal_peer
if use_ltm:
    ends = pd.to_datetime(peer["period_end"])
    st.caption(
        f"Trailing twelve months ending {ends.min():%b %d} to {ends.max():%b %d, %Y}: the latest four reported quarters "
        "for each company, so every figure covers the same period within a few weeks."
    )
else:
    st.caption("Latest completed fiscal years end on different dates (Costco in August, the others in January).")

with st.expander("Scoring weights", expanded=False):
    st.caption(
        "Each metric is ranked across the peer set (best = 100, worst = 0), averaged within its pillar, and combined "
        "using these weights. Rank-based scoring means a single outlier cannot dominate."
    )
    columns = st.columns(len(PILLARS))
    weights = {
        pillar: column.slider(pillar, 0, 100, int(DEFAULT_WEIGHTS[pillar]), 5, key=f"weight_{pillar}")
        for pillar, column in zip(PILLARS, columns)
    }
if sum(weights.values()) == 0:
    st.warning("All weights are zero; restoring equal weights.")
    weights = dict(DEFAULT_WEIGHTS)

scores = score_peers(peer, weights)
leaders = pillar_leaders(scores)
top = scores.iloc[0]
runner_up = scores.iloc[1] if len(scores) > 1 else None
pillar_wins = [pillar for pillar, ticker in leaders.items() if ticker == top["ticker"]]
weakest_pillar = scores.loc[scores["ticker"] == top["ticker"], list(PILLARS)].iloc[0].dropna().idxmin()
headline = f"{top['ticker']} leads the peer set with a composite score of {top['Composite']:.0f} / 100."
reasoning = (
    (f"It ranks first on {', '.join(pillar_wins)}. " if pillar_wins else "It does not rank first on any single pillar; its lead is breadth. ")
    + (f"The runner-up, {runner_up['ticker']}, scores {runner_up['Composite']:.0f}. " if runner_up is not None else "")
    + f"{top['ticker']}'s weakest pillar is {weakest_pillar} ({scores.loc[scores['ticker'] == top['ticker'], weakest_pillar].iloc[0]:.0f}). "
    + "Scores are relative to this four-company set, not to the market, and reflect "
    + ("trailing twelve months to each issuer's latest quarter." if use_ltm else "each issuer's latest completed fiscal year.")
)
verdict(headline, reasoning)

section("Composite scorecard", "Pillar scores run 0-100 by rank. Click 'Scoring weights' above to see how the ordering responds.", "Peer ranking")
score_table(scores, list(PILLARS))

section("Pillar leaders", "Latest fiscal year with the change from the prior year and five-year history.", "Executive snapshot")
cards = []
spec = {
    "Growth": ("revenue_growth", "Net-sales growth", "Net sales basis"),
    "Profitability": ("operating_margin", "Operating margin", "On total revenue"),
    "Efficiency": ("cash_conversion_cycle", "Cash conversion cycle", "Lower is better"),
    "Cash": ("fcf_margin", "FCF margin", "Free cash flow on revenue"),
    "Returns": ("roic", "ROIC", "After-tax operating profit on invested capital"),
}
annual_scored = with_fcf_margin(annual)
for pillar, (metric, label, detail) in spec.items():
    ticker = leaders.get(pillar)
    if ticker is None:
        continue
    history = latest_and_prior(annual_scored[annual_scored["ticker"] == ticker], metric).iloc[0]
    if use_ltm:
        scored_peer = with_fcf_margin(peer).set_index("ticker")
        history = {"latest": scored_peer.loc[ticker, metric], "change": None, "history": []}
        detail = f"{detail} · trailing 12 months"
    text, direction = _fmt_delta(metric, history["change"])
    # For the cash cycle a decrease is the favourable direction, so flip the colour semantics.
    if metric == "cash_conversion_cycle" and direction in {"up", "down"}:
        direction = "down" if direction == "up" else "up"
    cards.append({
        "label": f"{pillar} leader · {label}",
        "value": f"{ticker} · {format_value(metric, history['latest'])}",
        "delta": f"{text} vs prior year" if text != "—" else "",
        "delta_dir": direction,
        "detail": detail,
        "tone": "good",
        "spark": history["history"],
        "spark_color": COMPANY_COLORS.get(ticker, "#898781"),
    })
kpi_grid(cards)

section(
    "Rank heatmap",
    "Brighter cells rank better within each column; the number after each value is the rank among peers.",
    "Cross-section",
)
rank_heatmap(
    with_fcf_margin(peer),
    [
        ("revenue_growth", "Sales growth", True),
        ("gross_margin", "Gross margin", True),
        ("operating_margin", "Operating margin", True),
        ("fcf_margin", "FCF margin", True),
        ("inventory_turnover", "Inventory turns", True),
        ("cash_conversion_cycle", "Cash cycle", False),
        ("current_ratio", "Current ratio", True),
        ("roic", "ROIC", True),
        ("return_on_equity", "ROE", True),
    ],
)
st.caption("Kroger's cost of sales excludes depreciation and rent-type items, so its gross margin is not strictly comparable.")

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
    cash_long["metric"] = cash_long["metric"].map(LABELS)
    chart = px.bar(
        cash_long, x="ticker", y="value", color="metric", barmode="group",
        color_discrete_map={LABELS["operating_cash_flow"]: TONES["secondary"], LABELS["free_cash_flow"]: TONES["accent"]},
        labels={"value": "USD", "ticker": "", "metric": ""},
    )
    chart.update_layout(legend_title_text="")
    st.plotly_chart(style_figure(chart, "free_cash_flow", 360), width="stretch", config=CHART_CONFIG)

with operations_tab:
    operations = peer[["ticker", "days_inventory_outstanding", "payable_days", "cash_conversion_cycle"]].melt(
        id_vars="ticker", var_name="metric", value_name="days"
    )
    operations["metric"] = operations["metric"].map(LABELS)
    chart = px.bar(
        operations, x="ticker", y="days", color="metric", barmode="group",
        color_discrete_map={
            LABELS["days_inventory_outstanding"]: TONES["secondary"], LABELS["payable_days"]: TONES["muted"],
            LABELS["cash_conversion_cycle"]: TONES["accent"],
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
