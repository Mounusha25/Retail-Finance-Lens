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
    assert views == 4
