from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ui import page_setup
from app.views import exploratory, peer_comparison, working_capital

page_setup('Performance', kicker='How they compare', description='Growth, margins and liquidity, the working-capital cycle, and how each company is positioned against its peers.')
tabs = st.tabs(['Growth & margins', 'Working capital', 'Positioning'])
with tabs[0]:
    peer_comparison.render()
with tabs[1]:
    working_capital.render()
with tabs[2]:
    exploratory.render()
