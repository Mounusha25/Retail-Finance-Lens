"""Create canonical financial schema and analytical views."""
from pathlib import Path

from alembic import op

from financial_analysis.models import Base

revision = "20261013_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())
    sql_path = Path(__file__).resolve().parents[2] / "sql" / "002_analytics_views.sql"
    op.execute(sql_path.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS analytics CASCADE")
    Base.metadata.drop_all(op.get_bind())
