from __future__ import annotations

import html
import math
from collections.abc import Iterable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Categorical slots 1-4 of the validated dark palette, assigned by entity in fixed order.
COMPANY_COLORS = {"COST": "#3987e5", "TGT": "#d95926", "WMT": "#199e70", "KR": "#c98500"}
COMPANY_ORDER = ("COST", "TGT", "WMT", "KR")
COMPANY_NAMES = {
    "COST": "Costco Wholesale",
    "TGT": "Target Corporation",
    "WMT": "Walmart Inc.",
    "KR": "The Kroger Co.",
}
BRAND_THEMES = {t: {"name": COMPANY_NAMES[t], "primary": COMPANY_COLORS[t]} for t in COMPANY_ORDER}

# Neutral ink for series that are not companies (e.g. days components).
TONES = {"primary": "#f0efec", "secondary": "#c3c2b7", "muted": "#898781", "accent": "#fab219"}
SURFACE, PAGE, PANEL, LINE, LINE_STRONG = "#1a1a19", "#0d0d0d", "#141413", "#2c2c2a", "#383835"
GOOD, CRITICAL = "#0ca30c", "#d03b3b"
SEQUENTIAL_BLUE = ["#184f95", "#1e63b8", "#2a78d6", "#3987e5", "#6aa5ee"]

PERCENT_METRICS = {
    "revenue_growth", "gross_margin", "operating_margin", "net_margin",
    "inventory_growth", "inventory_growth_gap",
    "roic", "return_on_equity", "effective_tax_rate", "nopat_margin",
}

CURRENCY_METRICS = {
    "net_sales", "total_revenue", "operating_income", "net_income",
    "operating_cash_flow", "free_cash_flow", "inventory",
    "cash_and_cash_equivalents", "total_debt", "shareholder_payouts", "dividends_paid", "share_repurchases",
    "net_debt_issuance", "fcf_after_payouts", "capital_expenditures", "ebitda", "net_debt", "lease_adjusted_debt",
    "implied_lease_interest", "operating_lease_liability", "adjusted_operating_income",
    "restructuring_impairment_charges",
}

LABELS = {
    "revenue_growth": "Net-sales growth",
    "gross_margin": "Gross margin",
    "operating_margin": "Operating margin",
    "net_margin": "Net margin",
    "ocf_to_net_income": "OCF / net income",
    "free_cash_flow": "Free cash flow",
    "inventory_growth_gap": "Inventory growth vs. sales",
    "inventory_turnover": "Inventory turnover",
    "days_inventory_outstanding": "Inventory days",
    "receivable_days": "Receivable days",
    "payable_days": "Payable days",
    "cash_conversion_cycle": "Cash conversion cycle",
    "current_ratio": "Current ratio",
    "quick_ratio": "Quick ratio",
    "total_debt": "Total debt",
    "net_sales": "Net sales",
    "total_revenue": "Total revenue",
    "operating_cash_flow": "Operating cash flow",
    "inventory": "Inventory",
    "roic": "Return on invested capital",
    "return_on_equity": "Return on equity",
    "asset_turnover": "Asset turnover",
    "equity_multiplier": "Equity multiplier",
    "effective_tax_rate": "Effective tax rate",
}

PERCENT_METRICS.update({"roiic", "roiic_3y", "incremental_operating_margin", "accruals_ratio", "fcf_conversion", "capex_to_revenue", "reinvestment_rate", "fcf_margin", "payout_ratio_fcf", "capex_to_ocf", "ebitda_margin", "lease_adjusted_roic", "adjusted_operating_margin"})
LABELS.update({
    "fcf_margin": "FCF margin",
    "payout_ratio_fcf": "Payout / FCF",
    "adjusted_operating_margin": "Adjusted operating margin",
    "roiic": "Incremental ROIC (1 yr)",
    "roiic_3y": "Incremental ROIC (3 yr)",
    "incremental_operating_margin": "Incremental operating margin",
    "operating_leverage": "Operating leverage",
    "accruals_ratio": "Accruals ratio",
    "fcf_conversion": "FCF conversion",
    "capex_to_da": "Capex / D&A",
    "capex_to_revenue": "Capex / revenue",
    "ppe_turnover": "PP&E turnover",
    "reinvestment_rate": "Reinvestment rate",
    "ebitda": "EBITDA",
    "ebitda_margin": "EBITDA margin",
    "net_debt": "Net debt",
    "net_debt_to_ebitda": "Net debt / EBITDA",
    "interest_coverage": "Interest coverage",
    "lease_adjusted_roic": "Lease-adjusted ROIC",
    "lease_adjusted_debt": "Lease-adjusted debt",
    "operating_lease_liability": "Operating lease liability",
    "capex_to_ocf": "Capex / OCF",
    "roic": "ROIC",
    "return_on_equity": "Return on equity",
    "asset_turnover": "Asset turnover",
    "equity_multiplier": "Equity multiplier",
    "effective_tax_rate": "Effective tax rate",
})

CHART_CONFIG = {"displayModeBar": False, "responsive": True, "scrollZoom": False}

APP_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
:root {
  --bg:#0d0d0d; --panel:#141413; --surface:#1a1a19; --line:#2c2c2a; --line2:#383835;
  --ink:#f0efec; --ink2:#c3c2b7; --muted:#898781; --accent:#fab219;
  --good:#0ca30c; --bad:#d03b3b;
  --mono:'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,monospace;
  --sans:'IBM Plex Sans',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
}
html, body, [class*="css"], [data-testid="stAppViewContainer"] { font-family:var(--sans); color:var(--ink); }
[data-testid="stAppViewContainer"], [data-testid="stApp"] { background:var(--bg); }
[data-testid="stHeader"] { height:0; background:transparent; }
[data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer { display:none !important; }
.block-container { max-width:1480px; padding:0 1.6rem 4rem; }
h1,h2,h3,h4 { color:var(--ink); letter-spacing:-.01em; font-family:var(--sans); }
p, li, label, span { color:inherit; }

/* Sidebar */
[data-testid="stSidebar"] { background:var(--panel); border-right:1px solid var(--line); min-width:250px; max-width:250px; }
[data-testid="stSidebarNav"] { display:none; }
[data-testid="stSidebar"] > div:first-child { padding-top:.6rem; }
.side-brand { display:flex; align-items:center; gap:.7rem; padding:.5rem .1rem 1.1rem; border-bottom:1px solid var(--line); margin-bottom:.9rem; }
.brand-mark { display:grid; place-items:center; width:34px; height:34px; border:1px solid var(--accent); color:var(--accent);
  font-family:var(--mono); font-size:.72rem; font-weight:600; letter-spacing:.04em; }
.brand-name { color:var(--ink); font-size:.88rem; font-weight:600; line-height:1.2; }
.brand-sub { color:var(--muted); font-size:.62rem; margin-top:.15rem; letter-spacing:.1em; text-transform:uppercase; font-family:var(--mono); }
.nav-label { color:var(--muted); font-size:.6rem; letter-spacing:.14em; text-transform:uppercase; font-family:var(--mono); margin:.2rem 0 .4rem; }
[data-testid="stSidebar"] [data-testid="stPageLink"] a { border-radius:0; padding:.5rem .6rem; color:var(--ink2); font-size:.83rem;
  border-left:2px solid transparent; margin:.05rem 0; }
[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover { background:var(--surface); color:var(--ink); }
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] { background:var(--surface); color:var(--ink); border-left-color:var(--accent); }
.side-status { margin-top:1.3rem; padding:.75rem; border:1px solid var(--line); background:var(--bg); }
.side-status-label { color:var(--muted); font-size:.58rem; letter-spacing:.14em; text-transform:uppercase; font-family:var(--mono); }
.side-status-value { color:var(--ink); font-size:.78rem; margin:.4rem 0 .2rem; }
.live-dot { display:inline-block; width:6px; height:6px; border-radius:50%; background:var(--good); margin-right:7px; }
.side-status-detail { color:var(--muted); font-size:.68rem; line-height:1.45; }

/* Ticker strip */
.tape { position:relative; display:block; width:100%; max-width:100%; overflow:hidden; contain:inline-size;
  border:1px solid var(--line); background:var(--panel); margin:.6rem 0 1rem; box-sizing:border-box;
  -webkit-mask-image:linear-gradient(90deg,transparent,#000 3%,#000 97%,transparent);
  mask-image:linear-gradient(90deg,transparent,#000 3%,#000 97%,transparent); }
[data-testid="stElementContainer"]:has(.tape), [data-testid="stMarkdownContainer"]:has(.tape) { min-width:0; max-width:100%; overflow:hidden; }
.tape-track { display:flex; width:max-content; animation:tape-scroll 55s linear infinite; will-change:transform; }
.tape:hover .tape-track { animation-play-state:paused; }
@keyframes tape-scroll { from { transform:translateX(0); } to { transform:translateX(-50%); } }
@media (prefers-reduced-motion: reduce) {
  .tape { overflow-x:auto; -webkit-mask-image:none; mask-image:none; }
  .tape-track { animation:none; }
}
.tick { flex:0 0 auto; display:flex; align-items:baseline; gap:.65rem; padding:.5rem 1.1rem; border-right:1px solid var(--line);
  font-family:var(--mono); font-size:.7rem; white-space:nowrap; }
.tick .sym { color:var(--ink); font-weight:600; letter-spacing:.04em; display:flex; align-items:center; gap:.4rem; }
.tick .sw { width:8px; height:8px; display:inline-block; }
.tick .lbl { color:var(--muted); }
.tick .val { color:var(--ink); }
.up { color:var(--good); } .down { color:var(--bad); } .flat { color:var(--muted); }

/* Header */
.page-header { display:flex; justify-content:space-between; align-items:flex-end; gap:1.5rem; padding:.2rem 0 1rem;
  border-bottom:1px solid var(--line); margin-bottom:1rem; }
.page-eyebrow { color:var(--accent); font-size:.64rem; font-weight:500; text-transform:uppercase; letter-spacing:.16em; font-family:var(--mono); }
.page-header h1 { margin:.3rem 0 .3rem; font-size:clamp(1.5rem,2.4vw,1.95rem); line-height:1.15; font-weight:600; }
.page-header p { color:var(--ink2); font-size:.86rem; line-height:1.5; margin:0; max-width:820px; }
.scope-badge { flex:0 0 auto; display:flex; align-items:center; gap:.5rem; padding:.4rem .65rem; border:1px solid var(--line2);
  color:var(--ink2); font-size:.66rem; font-family:var(--mono); white-space:nowrap; }
.scope-dot { width:6px; height:6px; border-radius:50%; background:var(--good); }
.section-kicker { color:var(--accent); text-transform:uppercase; letter-spacing:.16em; font-size:.6rem; font-family:var(--mono); margin-top:1.7rem; }
.section-title { font-size:1.05rem; font-weight:600; margin:.25rem 0 .15rem; }
.section-copy { color:var(--muted); font-size:.8rem; margin:0 0 .8rem; }

/* KPI cards */
.kpi-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(168px,1fr)); gap:1px; background:var(--line);
  border:1px solid var(--line); margin:.5rem 0 1.2rem; }
.kpi-card { background:var(--surface); padding:.85rem .95rem .8rem; min-height:118px; position:relative; }
.kpi-card .label { color:var(--muted); font-size:.62rem; text-transform:uppercase; letter-spacing:.1em; font-family:var(--mono); }
.kpi-card .value { color:var(--ink); font-family:var(--mono); font-size:1.5rem; font-weight:500; margin:.45rem 0 .15rem; letter-spacing:-.02em; }
.kpi-card .delta { font-family:var(--mono); font-size:.72rem; }
.kpi-card .detail { color:var(--muted); font-size:.7rem; line-height:1.4; margin-top:.25rem; max-width:62%; }
.kpi-card .spark { position:absolute; right:.8rem; bottom:.7rem; }
.kpi-card.good { border-top:2px solid var(--good); } .kpi-card.watch { border-top:2px solid var(--accent); }
.kpi-card.blue { border-top:2px solid #3987e5; } .kpi-card.red { border-top:2px solid var(--bad); }
.insight { background:var(--surface); border:1px solid var(--line); border-left:2px solid var(--accent); padding:.85rem .95rem;
  margin:.25rem 0; color:var(--ink2); font-size:.8rem; line-height:1.5; min-height:100px; }
.insight strong { display:block; color:var(--ink); font-size:.85rem; margin-bottom:.25rem; }
.brand-context { display:flex; align-items:center; justify-content:space-between; gap:1rem; margin:.1rem 0 1rem; padding:.55rem .8rem;
  border:1px solid var(--line); background:var(--surface); color:var(--ink2); font-size:.72rem; }
.brand-context strong { color:var(--ink); font-size:.82rem; }
.brand-context-left { display:flex; align-items:center; gap:.6rem; }
.brand-swatch { width:4px; height:28px; }
.brand-context-meta { color:var(--muted); text-transform:uppercase; letter-spacing:.1em; font-size:.6rem; font-family:var(--mono); }

/* Verdict + scorecards */
.verdict { border:1px solid var(--line); background:var(--surface); padding:1rem 1.1rem; margin:.5rem 0 1rem; }
.verdict .head { color:var(--muted); font-family:var(--mono); font-size:.62rem; letter-spacing:.14em; text-transform:uppercase; }
.verdict .lead { font-size:1.15rem; font-weight:600; margin:.4rem 0 .35rem; line-height:1.35; }
.verdict .why { color:var(--ink2); font-size:.82rem; line-height:1.55; }
table.score, table.heat, table.stmt { width:100%; border-collapse:collapse; font-family:var(--mono); font-size:.76rem; }
table.score th, table.heat th, table.stmt th { color:var(--muted); font-weight:500; text-align:right; padding:.5rem .6rem; font-size:.62rem;
  text-transform:uppercase; letter-spacing:.08em; border-bottom:1px solid var(--line2); background:var(--panel); }
table.score th:first-child, table.heat th:first-child, table.stmt th:first-child { text-align:left; }
table.score td, table.heat td, table.stmt td { padding:.5rem .6rem; border-bottom:1px solid var(--line); text-align:right; color:var(--ink); }
table.score td:first-child, table.heat td:first-child, table.stmt td:first-child { text-align:left; }
table.heat td.cell { color:#fff; }
table.stmt tr.total td { font-weight:600; border-top:1px solid var(--line2); background:var(--panel); }
table.stmt tr.sub td:first-child { padding-left:1.4rem; color:var(--ink2); }
table.stmt tr.head td { color:var(--accent); font-size:.62rem; letter-spacing:.14em; text-transform:uppercase; background:var(--bg); }
table.stmt td.neg { color:var(--ink2); }
.barcell { display:flex; align-items:center; gap:.5rem; justify-content:flex-end; }
.bar { height:8px; background:var(--line); width:110px; position:relative; }
.bar > i { position:absolute; left:0; top:0; bottom:0; display:block; }
.rank { color:var(--muted); width:1.6rem; display:inline-block; }
.wrap { overflow-x:auto; border:1px solid var(--line); background:var(--surface); }

/* Native components */
[data-testid="stMetric"] { background:var(--surface); border:1px solid var(--line); padding:.8rem; border-radius:0; }
[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:0; }
[data-testid="stPlotlyChart"] { background:var(--surface); border:1px solid var(--line); padding:.3rem; }
[data-baseweb="tab-list"] { gap:0; border-bottom:1px solid var(--line); }
[data-baseweb="tab"] { border-radius:0; padding:.5rem .9rem; background:transparent; color:var(--muted); border-bottom:2px solid transparent;
  font-size:.78rem; font-family:var(--mono); }
[aria-selected="true"][data-baseweb="tab"] { color:var(--ink); border-bottom-color:var(--accent); }
[data-testid="stSegmentedControl"] button, [data-testid="stRadio"] label { font-size:.78rem; }
[data-baseweb="select"] > div, [data-testid="stTextInput"] input { border-radius:0; border-color:var(--line2); background:var(--surface); }
div[data-testid="stAlert"] { border-radius:0; font-size:.8rem; }
[data-testid="stCaptionContainer"] { color:var(--muted); }
hr { border-color:var(--line); }
@media(max-width:800px) {
  .block-container { padding:0 .9rem 3rem; }
  .page-header { align-items:flex-start; flex-direction:column; }
  .kpi-card .value { font-size:1.25rem; }
}
</style>
"""

_NAV = [
    ("streamlit_app.py", "Executive overview"),
    ("pages/1_Peer_Comparison.py", "Peer benchmarking"),
    ("pages/2_Working_Capital.py", "Working capital"),
    ("pages/3_Returns_and_DuPont.py", "Returns & DuPont"),
    ("pages/4_Why_Returns_Moved.py", "Why returns moved"),
    ("pages/5_Capital_Allocation.py", "Capital allocation"),
    ("pages/6_Leverage_and_Coverage.py", "Leverage & coverage"),
    ("pages/7_Financial_Statements.py", "Financial statements"),
    ("pages/8_Company_Trends.py", "Company detail"),
    ("pages/9_Exploratory_Analysis.py", "Exploratory analysis"),
    ("pages/10_Methodology_and_Data_Quality.py", "Data quality & methods"),
]


def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            """
            <div class="side-brand">
              <div class="brand-mark">RFL</div>
              <div><div class="brand-name">Retail Finance Lens</div><div class="brand-sub">Equity research</div></div>
            </div>
            <div class="nav-label">Workspace</div>
            """,
            unsafe_allow_html=True,
        )
        for path, label in _NAV:
            st.page_link(path, label=label)
        st.markdown(
            """
            <div class="side-status">
              <div class="side-status-label">Data environment</div>
              <div class="side-status-value"><span class="live-dot"></span>SEC filings loaded</div>
              <div class="side-status-detail">Walmart · Target · Costco · Kroger<br>Every figure links to its filing</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _fmt_delta(metric: str, change: float | None) -> tuple[str, str]:
    """Return (text, direction) for a year-over-year change; percent metrics use percentage points."""
    if change is None or pd.isna(change):
        return "—", "flat"
    direction = "up" if change > 0 else "down" if change < 0 else "flat"
    arrow = "▲" if change > 0 else "▼" if change < 0 else "■"
    if metric in PERCENT_METRICS:
        return f"{arrow} {abs(change) * 100:.1f} pp", direction
    if metric in {"cash_conversion_cycle", "days_inventory_outstanding", "payable_days", "receivable_days"}:
        return f"{arrow} {abs(change):.1f} days", direction
    return f"{arrow} {abs(change):.2f}×", direction


def sparkline(values: Iterable[float], color: str = "#898781", width: int = 84, height: int = 26) -> str:
    points = [float(v) for v in values if v is not None and not pd.isna(v)]
    if len(points) < 2:
        return ""
    low, high = min(points), max(points)
    span = (high - low) or 1.0
    step = (width - 4) / (len(points) - 1)
    coords = [(2 + i * step, 2 + (height - 4) * (1 - (v - low) / span)) for i, v in enumerate(points)]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    x, y = coords[-1]
    return (
        f'<svg class="spark" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="trend">'
        f'<polyline fill="none" stroke="{color}" stroke-width="1.5" points="{path}"/>'
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="{color}"/></svg>'
    )


def ticker_strip() -> None:
    """Top tape: latest fiscal-year sales growth, operating margin and ROIC with year-over-year change."""
    try:
        from app.data import load_view
        from app.scoring import latest_and_prior

        annual = load_view("annual")
    except Exception:
        return
    if annual.empty:
        return
    annual = annual.copy()
    annual["period_end"] = pd.to_datetime(annual["period_end"])
    annual = annual.sort_values(["ticker", "period_end"])
    items = []
    for ticker in [t for t in COMPANY_ORDER if t in set(annual["ticker"])]:
        company = annual[annual["ticker"] == ticker]
        latest = company.iloc[-1]
        cells = [
            f'<span class="sym"><i class="sw" style="background:{COMPANY_COLORS[ticker]}"></i>{html.escape(ticker)}</span>'
        ]
        for metric, label in (("revenue_growth", "SALES"), ("operating_margin", "OPM"), ("roic", "ROIC")):
            value = latest.get(metric)
            if value is None or pd.isna(value):
                continue
            moves = latest_and_prior(company, metric).iloc[0]
            text, direction = _fmt_delta(metric, moves["change"]) if metric != "revenue_growth" else ("", "flat")
            delta = f' <span class="{direction}">{text}</span>' if text and text != "—" else ""
            cells.append(f'<span class="lbl">{label}</span><span class="val">{float(value):.1%}</span>{delta}')
        items.append(f'<div class="tick">{" ".join(cells)}</div>')
    if not items:
        return
    # Four copies in two identical halves: the track slides left by 50% and loops seamlessly,
    # and each half stays wider than the viewport even on very wide screens.
    copies = "".join(items)
    track = copies + "".join(f'<div style="display:contents" aria-hidden="true">{copies}</div>' for _ in range(3))
    st.markdown(f'<div class="tape"><div class="tape-track">{track}</div></div>', unsafe_allow_html=True)


def page_setup(title: str, kicker: str = "Retail intelligence", description: str | None = None) -> None:
    st.set_page_config(page_title=f"{title} | Retail Finance Lens", page_icon="◆", layout="wide", initial_sidebar_state="auto")
    st.markdown(APP_CSS, unsafe_allow_html=True)
    _render_sidebar()
    ticker_strip()
    description = description or "Auditable SEC analysis across Walmart, Target, Costco, and Kroger."
    st.markdown(
        f"""
        <div class="page-header">
          <div>
            <div class="page-eyebrow">{html.escape(kicker)}</div>
            <h1>{html.escape(title)}</h1>
            <p>{html.escape(description)}</p>
          </div>
          <div class="scope-badge"><span class="scope-dot"></span>SEC sourced · fiscal-year basis</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section(title: str, copy: str = "", kicker: str = "Analysis") -> None:
    st.markdown(
        f'<div class="section-kicker">{html.escape(kicker)}</div>'
        f'<div class="section-title">{html.escape(title)}</div>'
        f'<p class="section-copy">{html.escape(copy)}</p>',
        unsafe_allow_html=True,
    )


def brand_theme(ticker: str) -> None:
    """Show the active company and tint the accent to its series color."""
    theme = BRAND_THEMES[ticker]
    st.markdown(
        f"""
        <style>
        :root {{ --accent:{theme['primary']}; }}
        </style>
        <div class="brand-context">
          <div class="brand-context-left">
            <span class="brand-swatch" style="background:{theme['primary']};"></span>
            <div><strong>{html.escape(theme['name'])}</strong><br><span class="brand-context-meta">Active company</span></div>
          </div>
          <span>{html.escape(ticker)} · series color</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_grid(cards: Iterable[dict]) -> None:
    """Cards accept label, value, detail, tone, and optionally delta (text), delta_dir (up/down/flat), spark (values)."""
    pieces = ['<div class="kpi-grid">']
    for card in cards:
        tone = html.escape(card.get("tone", "good"))
        delta = ""
        if card.get("delta"):
            direction = html.escape(card.get("delta_dir", "flat"))
            delta = f'<div class="delta {direction}">{html.escape(card["delta"])}</div>'
        spark = sparkline(card["spark"], card.get("spark_color", "#898781")) if card.get("spark") else ""
        pieces.append(
            f'<div class="kpi-card {tone}">{spark}<div class="label">{html.escape(card["label"])}</div>'
            f'<div class="value">{html.escape(card["value"])}</div>{delta}'
            f'<div class="detail">{html.escape(card.get("detail", ""))}</div></div>'
        )
    pieces.append("</div>")
    st.markdown("".join(pieces), unsafe_allow_html=True)


def insight(title: str, body: str) -> None:
    st.markdown(
        f'<div class="insight"><strong>{html.escape(title)}</strong>{html.escape(body)}</div>',
        unsafe_allow_html=True,
    )


def verdict(headline: str, reasoning: str, head: str = "Analyst verdict") -> None:
    st.markdown(
        f'<div class="verdict"><div class="head">{html.escape(head)}</div>'
        f'<div class="lead">{html.escape(headline)}</div><div class="why">{html.escape(reasoning)}</div></div>',
        unsafe_allow_html=True,
    )


def score_table(scores: pd.DataFrame, pillars: list[str]) -> None:
    """Composite score bars with pillar sub-scores, one row per company."""
    head = "".join(f"<th>{html.escape(p)}</th>" for p in pillars)
    rows = []
    for _, row in scores.iterrows():
        color = COMPANY_COLORS.get(row["ticker"], "#898781")
        composite = float(row["Composite"]) if pd.notna(row["Composite"]) else 0.0
        cells = "".join(
            f'<td>{"—" if pd.isna(row[p]) else f"{row[p]:.0f}"}</td>' for p in pillars
        )
        rows.append(
            f'<tr><td><span class="rank">#{int(row["Rank"])}</span>{html.escape(row["ticker"])} '
            f'<span style="color:var(--muted)">{html.escape(COMPANY_NAMES.get(row["ticker"], ""))}</span></td>'
            f'<td><div class="barcell"><div class="bar"><i style="width:{composite:.0f}%;background:{color}"></i></div>'
            f'<span>{composite:.0f}</span></div></td>{cells}</tr>'
        )
    st.markdown(
        f'<div class="wrap"><table class="score"><thead><tr><th>Company</th><th>Composite</th>{head}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>',
        unsafe_allow_html=True,
    )


def rank_heatmap(frame: pd.DataFrame, metrics: list[tuple[str, str, bool]]) -> None:
    """Companies x metrics. Cell intensity encodes rank (brighter = better) so one scale reads across units."""
    head = "".join(f"<th>{html.escape(label)}</th>" for _, label, _ in metrics)
    rows = []
    for _, row in frame.iterrows():
        cells = []
        for column, _label, higher in metrics:
            value = row.get(column)
            if value is None or pd.isna(value):
                cells.append('<td class="cell" style="background:var(--panel);color:var(--muted)">N/A</td>')
                continue
            valid = frame[column].dropna()
            rank = valid.rank(ascending=not higher, method="min")[row.name]
            position = 0.5 if len(valid) < 2 else (len(valid) - rank) / (len(valid) - 1)
            shade = SEQUENTIAL_BLUE[min(int(position * (len(SEQUENTIAL_BLUE) - 1) + 0.5), len(SEQUENTIAL_BLUE) - 1)]
            ink = "#0d0d0d" if shade in SEQUENTIAL_BLUE[3:] else "#ffffff"
            cells.append(
                f'<td class="cell" style="background:{shade};color:{ink}">{html.escape(format_value(column, value))}'
                f'<span style="opacity:.7;font-size:.62rem"> #{int(rank)}</span></td>'
            )
        rows.append(f'<tr><td>{html.escape(row["ticker"])}</td>{"".join(cells)}</tr>')
    st.markdown(
        f'<div class="wrap"><table class="heat"><thead><tr><th>Company</th>{head}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>',
        unsafe_allow_html=True,
    )


def format_value(metric: str, value: object) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    numeric = float(value)
    if metric in PERCENT_METRICS:
        return f"{numeric:.1%}"
    if metric in CURRENCY_METRICS:
        return f"${numeric / 1_000_000_000:,.1f}B"
    if "days" in metric or metric == "cash_conversion_cycle":
        return f"{numeric:,.1f} days"
    return f"{numeric:,.2f}×"


def display_period_caption(row: pd.Series) -> str:
    year_label = f"FY{int(row['issuer_fiscal_year'])}" if pd.notna(row.get("issuer_fiscal_year")) else "Fiscal year"
    week_note = " · 53 weeks" if bool(row.get("is_53_week", False)) else ""
    return f"{year_label} · ended {pd.Timestamp(row['period_end']).date()}{week_note}"





def style_figure(figure: go.Figure, metric: str | None = None, height: int = 410) -> go.Figure:
    axis = dict(
        gridcolor=LINE, linecolor=LINE_STRONG, zerolinecolor=LINE_STRONG,
        tickfont=dict(color="#898781", family="IBM Plex Mono, monospace", size=11),
        title_font=dict(color="#c3c2b7", size=11),
    )
    figure.update_layout(
        height=height,
        margin=dict(l=64, r=24, t=34, b=26),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family="IBM Plex Sans, -apple-system, sans-serif", color="#c3c2b7", size=12),
        hoverlabel=dict(bgcolor=PAGE, font_color="#f0efec", bordercolor=LINE_STRONG),
        legend=dict(orientation="h", y=1.1, x=0, title_text="", font=dict(size=11, color="#c3c2b7")),
        xaxis=dict(**{**axis, "gridcolor": "rgba(0,0,0,0)"}),
        yaxis=axis,
        colorway=[COMPANY_COLORS[t] for t in COMPANY_ORDER],
        hovermode="x unified", bargap=.35,
    )
    figure.update_xaxes(automargin=True)
    figure.update_yaxes(automargin=True)
    figure.update_traces(hovertemplate=None)
    figure.update_annotations(font=dict(color="#c3c2b7", size=11))
    if metric in PERCENT_METRICS:
        figure.update_yaxes(tickformat=".1%")
    elif metric in CURRENCY_METRICS:
        figure.update_yaxes(tickprefix="$", tickformat="~s")
    return figure


def winner(frame: pd.DataFrame, metric: str, highest: bool = True) -> pd.Series | None:
    valid = frame.dropna(subset=[metric])
    if valid.empty:
        return None
    index = valid[metric].idxmax() if highest else valid[metric].idxmin()
    return valid.loc[index]


def safe_number(value: object, fallback: float = 0.0) -> float:
    if value is None or pd.isna(value):
        return fallback
    numeric = float(value)
    return fallback if math.isnan(numeric) else numeric


def statement_table(frame: pd.DataFrame, rows: list[tuple[str, str | None, str, str]], common_size: bool) -> None:
    """Analyst-layout statement. rows = (label, column, style, base_column); style in head/row/sub/total.

    Values are USD millions with negatives in parentheses; the last column is year-over-year change.
    With common_size the base column (revenue or assets) turns every line into a percentage.
    """
    periods = frame.sort_values("period_end")
    head_cells = []
    for _, period in periods.iterrows():
        label = f"FY{int(period['issuer_fiscal_year'])}" if pd.notna(period.get("issuer_fiscal_year")) else "FY"
        head_cells.append(f"<th>{label}<br>{pd.Timestamp(period['period_end']).strftime('%b %Y')}</th>")
    body = []
    for label, column, style, base in rows:
        if style == "head":
            body.append(f'<tr class="head"><td colspan="{len(periods) + 2}">{html.escape(label)}</td></tr>')
            continue
        values = [periods.iloc[i].get(column) for i in range(len(periods))]
        bases = [periods.iloc[i].get(base) for i in range(len(periods))]
        cells = []
        for value, denominator in zip(values, bases):
            if value is None or pd.isna(value):
                cells.append('<td class="neg">—</td>')
            elif common_size:
                ok = denominator is not None and not pd.isna(denominator) and float(denominator) != 0
                cells.append(f"<td>{float(value) / float(denominator):.1%}</td>" if ok else '<td class="neg">—</td>')
            else:
                millions = float(value) / 1_000_000
                text = f"({abs(millions):,.0f})" if millions < 0 else f"{millions:,.0f}"
                cells.append(f"<td>{text}</td>")
        latest, prior = values[-1], values[-2] if len(values) > 1 else None
        if latest is None or prior is None or pd.isna(latest) or pd.isna(prior) or float(prior) <= 0:
            yoy = '<td class="neg">—</td>'
        else:
            change = float(latest) / float(prior) - 1
            direction = "up" if change > 0 else "down" if change < 0 else "flat"
            arrow = "▲" if change > 0 else "▼" if change < 0 else "■"
            yoy = f'<td class="{direction}">{arrow} {abs(change):.1%}</td>'
        css = {"sub": "sub", "total": "total"}.get(style, "")
        body.append(f'<tr class="{css}"><td>{html.escape(label)}</td>{"".join(cells)}{yoy}</tr>')
    unit = "% of revenue / assets" if common_size else "USD millions"
    st.markdown(
        f'<div class="wrap"><table class="stmt"><thead><tr><th>{unit}</th>{"".join(head_cells)}<th>YoY</th></tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>',
        unsafe_allow_html=True,
    )
