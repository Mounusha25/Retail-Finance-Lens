from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text


VIEW_NAMES = {
    "annual": "analytics.v_annual_metrics",
    "quarterly": "analytics.v_quarterly_metrics",
    "peer": "analytics.v_peer_comparison",
    "ltm": "analytics.v_ltm_metrics",
    "quality": "analytics.v_data_quality",
}


def _dotenv_value(key: str, path: Path | None = None) -> str:
    """Read one key from the project's .env, so a local run needs no exported variables."""
    path = path or Path(__file__).resolve().parents[1] / ".env"
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            name, separator, value = line.partition("=")
            if separator and name.strip() == key:
                return value.strip().strip("\"'")
    except OSError:
        pass
    return ""


def _database_url() -> str:
    # Order: environment, Streamlit secrets (hosted app), then the project's .env (local run).
    value = os.getenv("DATABASE_URL")
    if not value:
        try:
            value = st.secrets["DATABASE_URL"]
        except (KeyError, FileNotFoundError):
            value = ""
    if not value:
        value = _dotenv_value("DATABASE_URL")
    if value.startswith("postgres://"):
        value = value.replace("postgres://", "postgresql+psycopg://", 1)
    elif value.startswith("postgresql://") and "+psycopg" not in value:
        value = value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


@st.cache_resource
def engine():
    url = _database_url()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not configured. Set it in .env, in .streamlit/secrets.toml, or as an environment variable."
        )
    return create_engine(url, pool_pre_ping=True, pool_recycle=240)


@st.cache_data(ttl=900)
def load_view(view: str) -> pd.DataFrame:
    if view not in VIEW_NAMES:
        raise ValueError(f"Unknown analytical view: {view}")
    with engine().connect() as connection:
        return pd.read_sql(text(f"SELECT * FROM {VIEW_NAMES[view]}"), connection)


def latest_periods(frame: pd.DataFrame, count: int) -> pd.DataFrame:
    if frame.empty:
        return frame
    frame = frame.copy()
    frame["period_end"] = pd.to_datetime(frame["period_end"])
    return (
        frame.sort_values(["ticker", "period_end"])
        .groupby("ticker", group_keys=False)
        .tail(count)
        .reset_index(drop=True)
    )


def load_or_stop(view: str) -> pd.DataFrame:
    try:
        frame = load_view(view)
    except Exception as exc:
        st.error("The analytical database is not ready.")
        st.code(str(exc))
        st.info("Run `financial-analysis refresh --companies all`, then reload this page.")
        st.stop()
    if frame.empty:
        st.warning("The pipeline has not loaded any comparable periods yet.")
        st.stop()
    return frame
