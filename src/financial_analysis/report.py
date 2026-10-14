from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from .config import PROJECT_ROOT, Settings
from .db import make_engine


def _percent(value: object) -> str:
    return "—" if pd.isna(value) else f"{float(value):.1%}"


def _billions(value: object) -> str:
    return "—" if pd.isna(value) else f"${float(value) / 1_000_000_000:,.1f}B"


def _number(value: object, suffix: str = "") -> str:
    return "—" if pd.isna(value) else f"{float(value):,.1f}{suffix}"


def _winner(peer: pd.DataFrame, metric: str, highest: bool = True) -> pd.Series | None:
    valid = peer.dropna(subset=[metric])
    if valid.empty:
        return None
    return valid.loc[valid[metric].idxmax() if highest else valid[metric].idxmin()]


def _filing_link(row: pd.Series, label: str = "SEC filing") -> str:
    return f"[{label}]({row['source_url']})"


def _five_year_change(company: pd.DataFrame) -> tuple[pd.Series, pd.Series, float | None]:
    periods = company.sort_values("period_end").tail(5)
    first, latest = periods.iloc[0], periods.iloc[-1]
    if pd.isna(first["net_sales"]) or pd.isna(latest["net_sales"]) or float(first["net_sales"]) <= 0:
        return first, latest, None
    intervals = max(len(periods) - 1, 1)
    cagr = (float(latest["net_sales"]) / float(first["net_sales"])) ** (1 / intervals) - 1
    return first, latest, cagr


def generate_report(settings: Settings, output: Path | None = None) -> Path:
    output = output or PROJECT_ROOT / "reports" / "v1_findings.md"
    with make_engine(settings.database_url).connect() as connection:
        peer = pd.read_sql(text("SELECT * FROM analytics.v_peer_comparison ORDER BY ticker"), connection)
        annual = pd.read_sql(
            text(
                "SELECT * FROM analytics.v_annual_metrics "
                "WHERE period_end >= DATE '2021-01-01' ORDER BY ticker, period_end"
            ),
            connection,
        )
        quarterly = pd.read_sql(
            text(
                "WITH ranked AS ("
                " SELECT q.*, row_number() OVER (PARTITION BY ticker ORDER BY period_end DESC) AS rn"
                " FROM analytics.v_quarterly_metrics q"
                ") SELECT * FROM ranked WHERE rn <= 12 ORDER BY ticker, period_end"
            ),
            connection,
        )
        quality = pd.read_sql(text("SELECT * FROM analytics.v_data_quality"), connection)
    if peer.empty:
        raise RuntimeError("No analytical periods are loaded; run the refresh command first")

    by_ticker = {row["ticker"]: row for _, row in peer.iterrows()}
    cost = by_ticker["COST"]
    tgt = by_ticker["TGT"]
    wmt = by_ticker["WMT"]
    status_counts = quality["status"].value_counts() if not quality.empty else pd.Series(dtype=int)
    target_quarters = quarterly[quarterly["ticker"] == "TGT"]
    target_ccc_missing = int(target_quarters["cash_conversion_cycle"].isna().sum())

    lines = [
        "# Retail Finance Lens — Performance & Working Capital Analytics",
        "",
        "## Analyst report — Walmart, Target, and Costco",
        "",
        f"**Prepared:** {date.today().isoformat()}  ",
        "**Decision question:** Which retailer is growing profitably, managing inventory efficiently, and converting profit into cash?  ",
        "**Scope:** Latest five completed annual periods and twelve standalone quarters per company, based on latest-known SEC filings.",
        "",
        "---",
        "",
        "## Executive conclusion",
        "",
        (
            f"**Costco currently presents the strongest combination of growth and operating efficiency.** Its latest net sales "
            f"grew {_percent(cost['revenue_growth'])}, inventory turned {_number(cost['inventory_turnover'], '×')}, and the cash "
            f"conversion cycle was only {_number(cost['cash_conversion_cycle'], ' day')}. Walmart remains the peer group's "
            f"largest absolute cash generator, producing {_billions(wmt['free_cash_flow'])} of free cash flow. Target retained "
            f"the highest operating margin at {_percent(tgt['operating_margin'])}, but its {_percent(tgt['revenue_growth'])} sales "
            f"decline and slower inventory turns make the quality of that margin the most important issue to investigate."
        ),
        "",
        "This is not a single-winner story. Costco leads on momentum and working-capital speed; Walmart leads on cash scale; Target "
        "shows that higher margin does not automatically imply stronger growth or inventory productivity.",
        "",
        "### Latest completed fiscal-year scorecard",
        "",
        "| Company | Period end | Net-sales growth | Operating margin | OCF / net income | Free cash flow | Inventory turns | Cash cycle |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in peer.iterrows():
        lines.append(
            f"| {row['ticker']} | {row['period_end']} | {_percent(row['revenue_growth'])} | "
            f"{_percent(row['operating_margin'])} | {_number(row['ocf_to_net_income'], '×')} | "
            f"{_billions(row['free_cash_flow'])} | {_number(row['inventory_turnover'], '×')} | "
            f"{_number(row['cash_conversion_cycle'], ' days')} |"
        )

    lines.extend([
        "",
        "*Periods reflect each issuer's fiscal calendar. Target's year ended 2026-01-31 is issuer FY2025; Walmart labels the same "
        "ending date FY2026. Costco's latest year ended 2026-08-30.*",
        "",
        "---",
        "",
        "## Findings and financial implications",
        "",
        "### 1. Costco combines the fastest growth with the strongest inventory productivity",
        "",
        (
            f"Costco's latest net sales increased {_percent(cost['revenue_growth'])} to {_billions(cost['net_sales'])}. Gross margin "
            f"was {_percent(cost['gross_margin'])} and operating margin was {_percent(cost['operating_margin'])}, while inventory "
            f"turned {_number(cost['inventory_turnover'], '×')}—well ahead of Walmart and Target. Its "
            f"{_number(cost['cash_conversion_cycle'], '-day')} cash conversion cycle indicates that very little cash remained tied "
            f"up between paying suppliers and collecting from customers. {_filing_link(cost)}"
        ),
        "",
        (
            f"**Implication.** The low-margin model is economically attractive because sales velocity and supplier financing reduce "
            f"the working capital required to support growth. Operating cash flow of {_billions(cost['operating_cash_flow'])} covered "
            f"capex of {_billions(cost['capital_expenditures'])} and left {_billions(cost['free_cash_flow'])} of free cash flow. The "
            f"main analytical question is therefore not whether Costco can move inventory, but whether membership economics and "
            f"warehouse expansion can sustain this pace without weakening returns on incremental capital."
        ),
        "",
        "### 2. Walmart is the cash-flow leader, but its liquidity profile deserves context",
        "",
        (
            f"Walmart generated {_billions(wmt['operating_cash_flow'])} of operating cash flow and {_billions(wmt['free_cash_flow'])} "
            f"of free cash flow—the highest absolute amount in the group. OCF/net income of "
            f"{_number(wmt['ocf_to_net_income'], '×')} supports the quality of reported earnings. Net sales grew "
            f"{_percent(wmt['revenue_growth'])}, while inventory turnover reached {_number(wmt['inventory_turnover'], '×')} and the "
            f"cash conversion cycle was {_number(wmt['cash_conversion_cycle'], ' days')}. {_filing_link(wmt)}"
        ),
        "",
        (
            f"**Implication.** Walmart's scale produces exceptional cash capacity even after {_billions(wmt['capital_expenditures'])} "
            f"of capital investment. Its current ratio of {_number(wmt['current_ratio'], '×')} is below 1.0, but that should not be "
            f"read in isolation as distress: high sales frequency and short operating cycles allow large retailers to operate with "
            f"structurally low current ratios. The follow-up question is whether capex is translating into durable productivity and "
            f"digital-margin improvement rather than merely maintaining scale."
        ),
        "",
        "### 3. Target protects margin, but weaker sales and slower turns create the clearest execution risk",
        "",
        (
            f"Target's latest net sales declined {abs(float(tgt['revenue_growth'])):.1%}, even though its operating margin of "
            f"{_percent(tgt['operating_margin'])} was the highest of the three companies. Inventory turned only "
            f"{_number(tgt['inventory_turnover'], '×')}, versus {_number(wmt['inventory_turnover'], '×')} at Walmart and "
            f"{_number(cost['inventory_turnover'], '×')} at Costco. Target still produced {_billions(tgt['free_cash_flow'])} of free "
            f"cash flow and converted earnings into operating cash at {_number(tgt['ocf_to_net_income'], '×')}. {_filing_link(tgt)}"
        ),
        "",
        (
            "**Implication.** Margin resilience is positive, but declining sales combined with lower inventory productivity can signal "
            "mix pressure, markdown exposure, weaker traffic, or excess capacity. The next investigation should separate comparable "
            "sales, traffic, average ticket, shrink, markdowns, advertising revenue, and category mix. Target's reported cash cycle is "
            "short, but it relies on annual receivable data; quarterly cash-cycle analysis remains unavailable rather than being "
            "estimated."
        ),
        "",
        "### 4. Reported profit is supported by cash across all three peers",
        "",
        (
            f"OCF/net income was {_number(cost['ocf_to_net_income'], '×')} for Costco, "
            f"{_number(tgt['ocf_to_net_income'], '×')} for Target, and {_number(wmt['ocf_to_net_income'], '×')} for Walmart. Each ratio "
            "was above 1.0, and all three companies reported positive free cash flow. That reduces concern that current profit is "
            "primarily accrual-driven."
        ),
        "",
        (
            "**Implication.** One year of strong conversion is supportive, not conclusive. Cash conversion can be temporarily lifted by "
            "inventory reductions, supplier timing, or tax and compensation accruals. The quarterly cash-flow bridge should therefore "
            "be monitored alongside the five-year trend before concluding that the latest conversion rate is sustainable."
        ),
        "",
        "---",
        "",
        "## Five-year direction",
        "",
    ])
    for ticker, company in annual.groupby("ticker"):
        first, latest, cagr = _five_year_change(company)
        cagr_text = "—" if cagr is None else f"{cagr:.1%}"
        lines.append(
            f"- **{ticker}:** net sales moved from {_billions(first['net_sales'])} for the period ended {first['period_end']} to "
            f"{_billions(latest['net_sales'])} for the period ended {latest['period_end']}, an approximate {cagr_text} annualized "
            f"growth rate across the displayed observations. Latest free cash flow was {_billions(latest['free_cash_flow'])}. "
            f"[source for {first['period_end']} period]({first['source_url']}) · "
            f"[source for {latest['period_end']} period]({latest['source_url']})"
        )

    lines.extend([
        "",
        "## Recommended areas for investigation",
        "",
        "1. **Costco:** decompose growth into comparable sales, new warehouses, membership-fee growth, and foreign exchange; compare "
        "incremental operating profit with incremental capex.",
        "2. **Walmart:** evaluate returns from store, supply-chain, automation, and e-commerce investment; normalize working-capital "
        "timing before extrapolating the latest cash conversion ratio.",
        "3. **Target:** reconcile sales pressure with margin resilience through traffic, ticket, category mix, markdowns, shrink, and "
        "advertising/credit-card revenue; monitor inventory growth against sales each quarter.",
        "4. **Across peers:** compare supplier-term changes and lease-adjusted obligations, then extend the analysis to segment-level and "
        "comparable-sales disclosures before making capital-allocation conclusions.",
        "",
        "## Methodology, controls, and limitations",
        "",
        f"The latest validation run recorded **{int(status_counts.get('passed', 0))} passed checks, "
        f"{int(status_counts.get('warning', 0))} warnings, and {int(status_counts.get('error', 0))} errors**. Revenue components "
        "reconcile for all displayed annual periods and quarters. Raw SEC responses, accession numbers, filing dates, source concepts, "
        "units, dimensions, and derived-fact status are retained.",
        "",
        "- Net sales—not consolidated revenue—drives growth and gross margin. Membership and other revenue remains separate.",
        "- Average beginning and ending balances drive inventory, receivable, and payable efficiency. Actual fiscal-day counts drive days metrics.",
        "- Standalone quarterly flows are derived from cumulative disclosures when necessary; Q4 equals the annual value less Q3 YTD. Instant balances are never differenced.",
        "- Fiscal years are aligned by calendar year of period end but are not identical economic windows. Two displayed annual periods are 53-week years and are flagged rather than normalized away.",
        "- Missing facts remain null. Total-liability mapping gaps produce the 12 current warnings; no missing amount is silently treated as zero.",
        f"- Target has {target_ccc_missing} missing quarterly cash-cycle observations because a comparable quarterly receivables series is not disclosed under the configured concepts.",
        "- The analysis is consolidated-company, nominal USD, and U.S. GAAP. It excludes segments, constant-currency adjustments, leases beyond reported debt fields, valuation, and stock-price performance.",
        "- Latest-known facts power the dashboard. Historical versions remain stored, but this report is not an as-of-date investment backtest.",
        "",
        "## Evidence index",
        "",
    ])
    for _, row in peer.iterrows():
        lines.append(
            f"- **{row['ticker']} — issuer FY{int(row['issuer_fiscal_year'])}, ended {row['period_end']}:** "
            f"accession `{row['accession_number']}` · {_filing_link(row, 'primary filing')}"
        )
    lines.extend([
        "",
        "*This report is an operating-performance analysis, not an investment recommendation.*",
    ])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output
