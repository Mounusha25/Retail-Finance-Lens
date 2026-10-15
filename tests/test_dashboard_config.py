import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import data  # noqa: E402


def test_dotenv_value_reads_the_requested_key(tmp_path):
    env = tmp_path / ".env"
    env.write_text('SEC_USER_AGENT="Project me@example.com"\nDATABASE_URL=postgresql+psycopg://u:p@localhost:5432/db\n')
    assert data._dotenv_value("DATABASE_URL", env) == "postgresql+psycopg://u:p@localhost:5432/db"
    assert data._dotenv_value("SEC_USER_AGENT", env) == "Project me@example.com"
    assert data._dotenv_value("MISSING", env) == ""


def test_dotenv_value_tolerates_a_missing_file(tmp_path):
    assert data._dotenv_value("DATABASE_URL", tmp_path / "absent.env") == ""
