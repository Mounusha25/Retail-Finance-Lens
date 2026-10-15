from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ui import page_setup
from app.views import returns_dupont, why_returns_moved

page_setup('Returns', kicker='Are returns good, and why', description='Return on invested capital and equity, what drives them, and whether new capital is earning its keep.')
tabs = st.tabs(['ROIC & DuPont', 'Why returns moved'])
with tabs[0]:
    returns_dupont.render()
with tabs[1]:
    why_returns_moved.render()
