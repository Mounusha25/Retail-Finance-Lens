from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ui import page_setup
from app.views import company_trends, financial_statements

page_setup('Company', kicker='One company in depth', description='Annual and quarterly trends with filing lineage, and the primary financial statements in analyst layout.')
tabs = st.tabs(['Trends', 'Statements'])
with tabs[0]:
    company_trends.render()
with tabs[1]:
    financial_statements.render()
