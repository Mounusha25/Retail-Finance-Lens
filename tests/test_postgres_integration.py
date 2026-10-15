from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from financial_analysis.db import initialize_database, make_engine


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is not configured")
def test_schema_and_analytics_views_install_idempotently():
    engine = make_engine(os.environ["TEST_DATABASE_URL"])
    initialize_database(engine)
    initialize_database(engine)
    with engine.connect() as connection:
        tables = connection.execute(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
        ).scalar_one()
        views = connection.execute(
            text("SELECT count(*) FROM information_schema.views WHERE table_schema = 'analytics'")
        ).scalar_one()
    assert tables == 7
    assert views == 5


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is not configured")
def test_dashboard_reader_keeps_view_access_after_reinstall():
    engine = make_engine(os.environ["TEST_DATABASE_URL"])
    with engine.begin() as connection:
        exists = connection.execute(
            text("SELECT count(*) FROM pg_roles WHERE rolname = 'dashboard_reader'")
        ).scalar_one()
        if not exists:
            try:
                connection.execute(text("CREATE ROLE dashboard_reader NOLOGIN"))
            except Exception:
                pytest.skip("test role cannot create dashboard_reader")
    initialize_database(engine)
    initialize_database(engine)  # second install drops and recreates the views
    with engine.connect() as connection:
        granted = connection.execute(
            text(
                "SELECT bool_and(has_table_privilege('dashboard_reader', 'analytics.' || v, 'SELECT')) "
                "FROM unnest(ARRAY['v_annual_metrics','v_quarterly_metrics','v_peer_comparison','v_data_quality','v_ltm_metrics']) AS v"
            )
        ).scalar_one()
    assert granted is True
