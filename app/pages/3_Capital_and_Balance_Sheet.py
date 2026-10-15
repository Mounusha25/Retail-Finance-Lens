from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ui import page_setup
from app.views import capital_allocation, leverage_coverage

page_setup('Capital & Balance Sheet', kicker='Where the cash goes', description='How operating cash flow is deployed, and how much debt each company carries and can service.')
tabs = st.tabs(['Capital allocation', 'Leverage & coverage'])
with tabs[0]:
    capital_allocation.render()
with tabs[1]:
    leverage_coverage.render()
