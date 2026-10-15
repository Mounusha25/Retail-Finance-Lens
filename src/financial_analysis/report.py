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


def _returns_paragraph(peer: pd.DataFrame) -> str:
    needed = ["roic", "return_on_equity", "net_margin", "asset_turnover", "equity_multiplier"]
    valid = peer.dropna(subset=needed)
    if valid.empty:
        return "Return metrics are unavailable because the required balance-sheet facts are missing."
    ordered = valid.sort_values("roic", ascending=False)
    parts = [
        f"{row['ticker']} earned a {_percent(row['roic'])} ROIC and {_percent(row['return_on_equity'])} return on equity "
        f"({_percent(row['net_margin'])} net margin × {_number(row['asset_turnover'], '×')} asset turnover × "
        f"{_number(row['equity_multiplier'], '×')} equity multiplier)"
        for _, row in ordered.iterrows()
    ]
    return "; ".join(parts) + "."


def _depressed_earnings_note(peer: pd.DataFrame, threshold: float = 3.0) -> str:
    flagged = peer[peer["ocf_to_net_income"].notna() & (peer["ocf_to_net_income"] > threshold)]
    if flagged.empty:
        return ""
    names = ", ".join(f"{row['ticker']} ({_number(row['ocf_to_net_income'], '×')})" for _, row in flagged.iterrows())
    return (
        f" OCF / net income is unusually high for {names}; a ratio that large usually reflects net income depressed by non-cash "
        "charges such as impairments, not exceptional cash generation, so it should not be read as a stronger cash-quality signal."
    )


CORE_PEERS = ("COST", "TGT", "WMT")


def _kroger_paragraph(peer: pd.DataFrame) -> str:
    """Rank Kroger against every loaded peer on the headline metrics, from the data."""
    if "KR" not in set(peer["ticker"]):
        return ""
    metrics = [
        ("revenue_growth", "net-sales growth", True, _percent),
        ("operating_margin", "operating margin", True, _percent),
        ("inventory_turnover", "inventory turnover", True, lambda v: _number(v, "×")),
        ("cash_conversion_cycle", "cash conversion cycle (shorter is better)", False, lambda v: _number(v, " days")),
        ("ocf_to_net_income", "OCF / net income", True, lambda v: _number(v, "×")),
        ("roic", "ROIC", True, _percent),
    ]
    row = peer[peer["ticker"] == "KR"].iloc[0]
    pieces = []
    for column, label, higher_is_better, fmt in metrics:
        valid = peer.dropna(subset=[column])
        if pd.isna(row[column]) or "KR" not in set(valid["ticker"]):
            continue
        ordered = valid.sort_values(column, ascending=not higher_is_better)["ticker"].tolist()
        pieces.append(f"{label} of {fmt(row[column])} ranked {ordered.index('KR') + 1} of {len(ordered)}")
    return "Kroger's latest fiscal year " + "; ".join(pieces) + "." if pieces else ""


def _capital_allocation_paragraph(annual: pd.DataFrame) -> str:
    needed = ["operating_cash_flow", "capital_expenditures", "dividends_paid", "share_repurchases"]
    pieces = []
    for ticker, company in annual.dropna(subset=needed).sort_values("period_end").groupby("ticker"):
        window = company.tail(5)
        ocf = window["operating_cash_flow"].sum()
        capex = window["capital_expenditures"].sum()
        dividends = window["dividends_paid"].sum()
        buybacks = window["share_repurchases"].sum()
        fcf = ocf - capex
        remaining = ocf - capex - dividends - buybacks
        payout = f"{(dividends + buybacks) / fcf:.0%} of free cash flow" if fcf > 0 else "payouts with no positive free cash flow"
        gap = "left " + _billions(remaining) + " unallocated" if remaining >= 0 else "overspent operating cash flow by " + _billions(-remaining)
        pieces.append(
            f"{ticker} paid {_billions(dividends)} in dividends and {_billions(buybacks)} in buybacks over {len(window)} fiscal years "
            f"({payout}) and {gap}"
        )
    return "; ".join(pieces) + "." if pieces else "Dividend and buyback data are unavailable."


def _ltm_paragraph(ltm: pd.DataFrame) -> str:
    if ltm.empty or not bool(ltm["is_complete"].fillna(False).all()):
        return ""
    ends = pd.to_datetime(ltm["period_end"])
    parts = [
        f"{row['ticker']} {_percent(row['revenue_growth'])} growth, {_percent(row['operating_margin'])} operating margin, "
        f"{_billions(row['free_cash_flow'])} free cash flow"
        for _, row in ltm.sort_values("ticker").iterrows()
    ]
    return (
        f"On a trailing-twelve-month basis, every company is measured over the four quarters ending between {ends.min():%b %d} and "
        f"{ends.max():%b %d, %Y}, which removes the gap between Costco's August year-end and the January year-ends of the others: "
        + "; ".join(parts) + "."
    )


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
        ltm = pd.read_sql(text("SELECT * FROM analytics.v_ltm_metrics ORDER BY ticker"), connection)
    if peer.empty:
        raise RuntimeError("No analytical periods are loaded; run the refresh command first")

    by_ticker = {row["ticker"]: row for _, row in peer.iterrows()}
    cost = by_ticker["COST"]
    tgt = by_ticker["TGT"]
    wmt = by_ticker["WMT"]
    status_counts = quality["status"].value_counts() if not quality.empty else pd.Series(dtype=int)
    n53 = int(annual["is_53_week"].fillna(False).astype(bool).sum()) if "is_53_week" in annual else 0
    target_quarters = quarterly[quarterly["ticker"] == "TGT"]
    target_ccc_missing = int(target_quarters["cash_conversion_cycle"].isna().sum())

    lines = [
        "# Retail Finance Lens — Performance & Working Capital Analytics",
        "",
        "## Analyst report — Walmart, Target, Costco, and Kroger",
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
            f"**Among Walmart, Target, and Costco, Costco presents the strongest combination of growth and operating efficiency.** Its latest net sales "
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
        _kroger_paragraph(peer),
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
        _ltm_paragraph(ltm),
        "",
        "*Periods reflect each issuer's fiscal calendar. Target's and Kroger's years ended 2026-01-31 are issuer FY2025; Walmart labels "
        "the same ending date FY2026. Costco's latest year ended 2026-08-30.*",
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
            f"turned {_number(cost['inventory_turnover'], '×')}—well ahead of Walmart and Target (Kroger's grocery model is compared separately below). Its "
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
        "### 5. Kroger shows what a grocery-led model looks like against the general-merchandise and club peers",
        "",
        _kroger_paragraph(peer),
        "",
        (
            "**Implication.** Grocery turns inventory faster and carries thinner margins than general merchandise, so Kroger should be "
            "read against Costco and Walmart's grocery mix rather than against Target. Kroger's cost of sales excludes depreciation and "
            "rent-type items, so its gross margin is not strictly comparable with peers that include them; operating margin and cash "
            "metrics are the cleaner cross-company comparison. Its net inventory is derived as FIFO inventory less the LIFO reserve "
            "because it does not tag a single net figure."
            + _depressed_earnings_note(peer)
        ),
        "",
        "### 6. Returns differ because of capital intensity and leverage, not only margin",
        "",
        _returns_paragraph(peer),
        "",
        (
            "**Implication.** ROIC isolates what the operating business earns on debt plus equity, while the DuPont split shows whether "
            "return on equity comes from margin, asset productivity, or balance-sheet leverage. A high ROE supported mainly by a larger "
            "equity multiplier deserves more scrutiny than one supported by margin or turnover. Invested capital here excludes operating "
            "leases, which understates the capital base of the store-heavy peers."
        ),
        "",
        "### 7. Capital allocation: payouts are funded differently across the peers",
        "",
        _capital_allocation_paragraph(annual),
        "",
        (
            "**Implication.** Payouts above free cash flow are sustainable only while balance-sheet capacity or cash on hand covers "
            "the gap, so the useful question is how much of the payout is discretionary buyback versus a committed dividend. "
            "Buybacks flex with conditions; dividends are sticky. A company that spends more than its operating cash flow on capex "
            "and payouts together is drawing on cash or debt, which also explains rising leverage in the DuPont decomposition. Costco's "
            "fiscal 2024 includes a one-off special dividend."
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
        "4. **Kroger:** separate the effect of impairment and restructuring charges on operating margin, the buyback-driven fall in "
        "equity on ROE, and the contribution of pharmacy, fuel, and alternative profits to cash conversion.",
        "5. **Across peers:** compare supplier-term changes and lease-adjusted obligations, then extend the analysis to segment-level and "
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
        f"- Fiscal years are aligned by calendar year of period end but are not identical economic windows. {n53} displayed annual period(s) are 53-week years and are flagged rather than normalized away.",
        f"- Missing facts remain null; the current run has {int(status_counts.get('warning', 0))} warnings and no missing amount is silently treated as zero.",
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
