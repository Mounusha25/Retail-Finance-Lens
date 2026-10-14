from __future__ import annotations

import html
import math
from collections.abc import Iterable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


COMPANY_COLORS = {"COST": "#005DAA", "TGT": "#CC0000", "WMT": "#0071CE"}

BRAND_THEMES = {
    "COST": {
        "name": "Costco Wholesale",
        "primary": "#005DAA",
        "secondary": "#E31837",
        "soft": "#EAF4FB",
        "sidebar_start": "#061A2D",
        "sidebar_end": "#082B48",
    },
    "TGT": {
        "name": "Target Corporation",
        "primary": "#CC0000",
        "secondary": "#F25F5C",
        "soft": "#FDEEEE",
        "sidebar_start": "#260708",
        "sidebar_end": "#4A0B0E",
    },
    "WMT": {
        "name": "Walmart Inc.",
        "primary": "#0071CE",
        "secondary": "#FFC220",
        "soft": "#EAF5FC",
        "sidebar_start": "#071B31",
        "sidebar_end": "#0A345A",
    },
}

PERCENT_METRICS = {
    "revenue_growth", "gross_margin", "operating_margin", "net_margin",
    "inventory_growth", "inventory_growth_gap",
}

CURRENCY_METRICS = {
    "net_sales", "total_revenue", "operating_income", "net_income",
    "operating_cash_flow", "free_cash_flow", "inventory",
    "cash_and_cash_equivalents", "total_debt",
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
}

CHART_CONFIG = {"displayModeBar": False, "responsive": True, "scrollZoom": False}

APP_CSS = """
<style>
:root {
  --navy-950:#07111F; --navy-900:#0B172A; --navy-800:#13233A;
  --ink:#142033; --slate:#526174; --muted:#748196; --line:#E2E8F0;
  --canvas:#F5F7FA; --paper:#FFFFFF; --teal:#0F766E; --blue:#2563EB;
  --amber:#D97706; --red:#DC2626;
}
html, body, [class*="css"] { font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); }
[data-testid="stAppViewContainer"] { background:var(--canvas); }
[data-testid="stHeader"] { height:0; background:transparent; }
[data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer { display:none !important; }
.block-container { max-width:1380px; padding:1.25rem 2rem 4rem; }
h1,h2,h3 { color:var(--ink); letter-spacing:-.025em; }

/* Product navigation */
[data-testid="stSidebar"] {
  background:linear-gradient(180deg,var(--navy-950),var(--navy-900));
  border-right:1px solid #1E2F47; min-width:268px; max-width:268px;
}
[data-testid="stSidebar"] > div:first-child { padding-top:.8rem; }
[data-testid="stSidebarNav"] { display:none; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color:#A9B6C8; }
[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] button { color:#D9E2EE; }
.side-brand { display:flex; align-items:center; gap:.75rem; padding:.55rem .2rem 1.25rem; }
.brand-mark {
  display:grid; place-items:center; width:38px; height:38px; border-radius:9px;
  background:linear-gradient(145deg,#2DD4BF,#0F766E); color:white; font-size:.74rem;
  font-weight:800; letter-spacing:.04em; box-shadow:0 7px 18px rgba(13,148,136,.24);
}
.brand-name { color:#F8FAFC; font-size:.92rem; font-weight:750; line-height:1.2; }
.brand-sub { color:#7F91A8; font-size:.67rem; margin-top:.2rem; letter-spacing:.04em; text-transform:uppercase; }
.nav-label { color:#667990; font-size:.62rem; letter-spacing:.12em; text-transform:uppercase; font-weight:800; margin:.25rem 0 .45rem; }
[data-testid="stSidebar"] [data-testid="stPageLink"] a {
  border-radius:8px; padding:.62rem .68rem; color:#BFCADB; font-size:.86rem;
  font-weight:550; border:1px solid transparent; margin:.08rem 0;
}
[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover { color:white; background:#13233A; border-color:#20344E; }
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] { color:white; background:#17384A; border-color:#23556A; }
.side-status { margin-top:1.35rem; padding:.85rem; border:1px solid #20344E; border-radius:10px; background:rgba(19,35,58,.62); }
.side-status-label { color:#71849B; font-size:.61rem; font-weight:800; letter-spacing:.1em; text-transform:uppercase; }
.side-status-value { color:#E7EEF7; font-size:.79rem; font-weight:650; margin:.45rem 0 .25rem; }
.live-dot { display:inline-block; width:7px; height:7px; border-radius:50%; background:#34D399; margin-right:7px; box-shadow:0 0 0 3px rgba(52,211,153,.12); }
.side-status-detail { color:#8091A7; font-size:.69rem; line-height:1.4; }

/* Header and information hierarchy */
.page-header {
  display:flex; justify-content:space-between; align-items:flex-end; gap:1.5rem;
  padding:.35rem 0 1.35rem; border-bottom:1px solid var(--line); margin-bottom:1.25rem;
}
.page-eyebrow { color:var(--teal); font-size:.67rem; font-weight:800; text-transform:uppercase; letter-spacing:.12em; }
.page-header h1 { margin:.33rem 0 .35rem; font-size:clamp(1.75rem,3vw,2.35rem); line-height:1.1; font-weight:750; }
.page-header p { color:var(--slate); font-size:.9rem; line-height:1.5; margin:0; max-width:780px; }
.scope-badge {
  flex:0 0 auto; display:flex; align-items:center; gap:.5rem; padding:.52rem .72rem;
  border:1px solid #CBD5E1; border-radius:8px; background:#FFF; color:#425167;
  font-size:.69rem; font-weight:700; white-space:nowrap; box-shadow:0 1px 2px rgba(15,23,42,.03);
}
.scope-dot { width:7px; height:7px; border-radius:50%; background:#10B981; }
.section-kicker { color:var(--teal); text-transform:uppercase; letter-spacing:.11em; font-size:.64rem; font-weight:800; margin-top:1.8rem; }
.section-title { font-size:1.22rem; font-weight:750; letter-spacing:-.02em; margin:.28rem 0 .18rem; }
.section-copy { color:var(--slate); font-size:.84rem; margin:0 0 .85rem; }

/* Executive components */
.kpi-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:10px; margin:.65rem 0 1.25rem; }
.kpi-card {
  position:relative; background:var(--paper); border:1px solid var(--line); border-radius:10px;
  padding:1rem 1rem .9rem; min-height:112px; box-shadow:0 1px 2px rgba(15,23,42,.025);
}
.kpi-card:before { content:""; position:absolute; left:1rem; top:1rem; width:7px; height:7px; border-radius:50%; background:var(--teal); }
.kpi-card.good:before { background:#0F766E; } .kpi-card.watch:before { background:var(--amber); }
.kpi-card.blue:before { background:var(--blue); } .kpi-card.red:before { background:var(--red); }
.kpi-card .label { color:var(--slate); font-size:.69rem; font-weight:700; text-transform:uppercase; letter-spacing:.055em; padding-left:14px; }
.kpi-card .value { color:var(--ink); font-size:1.48rem; line-height:1.15; font-weight:760; letter-spacing:-.025em; margin:.55rem 0 .28rem; }
.kpi-card .detail { color:var(--muted); font-size:.72rem; line-height:1.4; }
.insight {
  background:#FFF; border:1px solid var(--line); border-radius:10px; padding:.95rem 1rem;
  margin:.25rem 0; color:#526174; font-size:.81rem; line-height:1.5; min-height:112px;
}
.insight strong { display:block; color:var(--ink); font-size:.86rem; letter-spacing:-.01em; margin-bottom:.24rem; }
.brand-context {
  display:flex; align-items:center; justify-content:space-between; gap:1rem; margin:.2rem 0 1rem;
  padding:.68rem .8rem; border:1px solid var(--line); border-radius:9px; background:#FFF;
  color:var(--slate); font-size:.72rem;
}
.brand-context strong { color:var(--ink); font-size:.8rem; }
.brand-context-left { display:flex; align-items:center; gap:.58rem; }
.brand-swatch { width:9px; height:30px; border-radius:4px; }
.brand-context-meta { color:var(--muted); text-transform:uppercase; letter-spacing:.07em; font-size:.62rem; font-weight:750; }

/* Native component refinements */
[data-testid="stMetric"] { background:#FFF; border:1px solid var(--line); padding:.85rem; border-radius:10px; }
[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:9px; overflow:hidden; background:#FFF; }
[data-testid="stPlotlyChart"] { background:#FFF; border:1px solid var(--line); border-radius:10px; padding:.4rem; }
[data-baseweb="tab-list"] { gap:0; border-bottom:1px solid var(--line); }
[data-baseweb="tab"] { border-radius:0; padding:.56rem .95rem; background:transparent; color:#66758A; border-bottom:2px solid transparent; font-size:.82rem; }
[aria-selected="true"][data-baseweb="tab"] { color:var(--ink); border-bottom-color:var(--teal); background:transparent; }
[data-testid="stSegmentedControl"] button, [data-testid="stRadio"] label { font-size:.8rem; }
[data-baseweb="select"] > div, [data-testid="stTextInput"] input { border-radius:8px; border-color:#CBD5E1; background:#FFF; }
div[data-testid="stAlert"] { border-radius:9px; font-size:.82rem; }
[data-testid="stCaptionContainer"] { color:var(--muted); }
hr { border-color:var(--line); }

@media(max-width:800px) {
  .block-container { padding:1rem .9rem 3rem; }
  .page-header { align-items:flex-start; flex-direction:column; }
  .kpi-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .kpi-card .value { font-size:1.25rem; }
}
</style>
"""


def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            """
            <div class="side-brand">
              <div class="brand-mark">RF</div>
              <div><div class="brand-name">RetailScope</div><div class="brand-sub">Financial Analytics</div></div>
            </div>
            <div class="nav-label">Workspace</div>
            """,
            unsafe_allow_html=True,
        )
        st.page_link("streamlit_app.py", label="Executive overview")
        st.page_link("pages/1_Peer_Comparison.py", label="Peer benchmarking")
        st.page_link("pages/2_Working_Capital.py", label="Working capital")
        st.page_link("pages/3_Company_Trends.py", label="Company detail")
        st.page_link("pages/4_Exploratory_Analysis.py", label="Exploratory analysis")
        st.page_link("pages/4_Methodology_and_Data_Quality.py", label="Data quality & methods")
        st.markdown(
            """
            <div class="side-status">
              <div class="side-status-label">Data environment</div>
              <div class="side-status-value"><span class="live-dot"></span>SEC dataset available</div>
              <div class="side-status-detail">Walmart · Target · Costco<br>Auditable filing lineage enabled</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def page_setup(title: str, kicker: str = "Retail intelligence", description: str | None = None) -> None:
    st.set_page_config(page_title=f"{title} | RetailScope", page_icon="◆", layout="wide", initial_sidebar_state="auto")
    st.markdown(APP_CSS, unsafe_allow_html=True)
    _render_sidebar()
    description = description or "Auditable SEC analysis across Walmart, Target, and Costco."
    st.markdown(
        f"""
        <div class="page-header">
          <div>
            <div class="page-eyebrow">{html.escape(kicker)}</div>
            <h1>{html.escape(title)}</h1>
            <p>{html.escape(description)}</p>
          </div>
          <div class="scope-badge"><span class="scope-dot"></span>3 issuers · SEC sourced</div>
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
    """Apply a company-specific visual system after the company selector reruns."""
    theme = BRAND_THEMES[ticker]
    st.markdown(
        f"""
        <style>
        :root {{ --teal:{theme['primary']}; }}
        [data-testid="stSidebar"] {{
          background:linear-gradient(180deg,{theme['sidebar_start']},{theme['sidebar_end']});
        }}
        .brand-mark {{ background:linear-gradient(145deg,{theme['secondary']},{theme['primary']}); }}
        .page-eyebrow,.section-kicker {{ color:{theme['primary']}; }}
        .scope-dot,.kpi-card.good:before {{ background:{theme['primary']}; }}
        [aria-selected="true"][data-baseweb="tab"] {{ border-bottom-color:{theme['primary']}; }}
        .insight {{ border-left-color:{theme['primary']}; }}
        </style>
        <div class="brand-context">
          <div class="brand-context-left">
            <span class="brand-swatch" style="background:linear-gradient(180deg,{theme['primary']} 0 62%,{theme['secondary']} 62%);"></span>
            <div><strong>{html.escape(theme['name'])}</strong><br><span class="brand-context-meta">Active company workspace</span></div>
          </div>
          <span>Theme synchronized to {html.escape(ticker)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_grid(cards: Iterable[dict[str, str]]) -> None:
    pieces = ['<div class="kpi-grid">']
    for card in cards:
        tone = html.escape(card.get("tone", "good"))
        pieces.append(
            f'<div class="kpi-card {tone}"><div class="label">{html.escape(card["label"])}</div>'
            f'<div class="value">{html.escape(card["value"])}</div>'
            f'<div class="detail">{html.escape(card.get("detail", ""))}</div></div>'
        )
    pieces.append("</div>")
    st.markdown("".join(pieces), unsafe_allow_html=True)


def insight(title: str, body: str) -> None:
    st.markdown(
        f'<div class="insight"><strong>{html.escape(title)}</strong>{html.escape(body)}</div>',
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
    figure.update_layout(
        height=height,
        margin=dict(l=24, r=24, t=38, b=22),
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        font=dict(family='Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', color="#526174", size=12),
        hoverlabel=dict(bgcolor="#0B172A", font_color="white", bordercolor="#0B172A"),
        legend=dict(orientation="h", y=1.1, x=0, title_text="", font=dict(size=11)),
        xaxis=dict(gridcolor="rgba(0,0,0,0)", linecolor="#D8E0EA", tickfont=dict(color="#66758A"), title_font=dict(color="#526174")),
        yaxis=dict(gridcolor="#EDF1F5", linecolor="#D8E0EA", zerolinecolor="#AEBBCB", tickfont=dict(color="#66758A"), title_font=dict(color="#526174")),
        colorway=[COMPANY_COLORS["COST"], COMPANY_COLORS["TGT"], COMPANY_COLORS["WMT"]],
        hovermode="x unified", bargap=.28,
    )
    figure.update_traces(hovertemplate=None)
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
