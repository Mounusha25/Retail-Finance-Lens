"""Renders every dashboard page against a loaded database and fails on any exception.

Skipped unless TEST_DATABASE_URL points at a database that already holds the analytics views with data
(the CI database is empty, so this runs in local and Docker checks).
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import pytest
from sqlalchemy import text

from financial_analysis.db import make_engine

ROOT = Path(__file__).resolve().parents[1]


def _database_has_data() -> bool:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        return False
    try:
        with make_engine(url).connect() as connection:
            return connection.execute(text("SELECT count(*) FROM analytics.v_ltm_metrics")).scalar_one() > 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _database_has_data(), reason="no populated analytics views in TEST_DATABASE_URL")


def test_every_page_renders_without_exceptions(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    monkeypatch.chdir(ROOT)
    at = AppTest.from_file("app/streamlit_app.py", default_timeout=240).run()
    failures = {"Overview": [str(e.value) for e in at.exception]}
    for page in sorted(glob.glob("app/pages/*.py")):
        at.switch_page(page.replace("app/", "", 1)).run()
        failures[Path(page).name] = [str(e.value) for e in at.exception]
    assert {name: errs for name, errs in failures.items() if errs} == {}
    assert len(failures) == 7  # overview + six pages: the navigation is exactly seven entries


def test_navigation_lists_exactly_the_pages_on_disk():
    from app.ui import _NAV

    on_disk = {f"pages/{Path(p).name}" for p in glob.glob(str(ROOT / "app/pages/*.py"))}
    listed = {path for path, _ in _NAV if path != "streamlit_app.py"}
    assert listed == on_disk
