from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://financial:financial@localhost:5432/financial_analysis"
    database_write_url: str | None = None
    sec_user_agent: str = ""
    raw_data_dir: Path = PROJECT_ROOT / "data" / "raw"
    staged_data_dir: Path = PROJECT_ROOT / "data" / "staged"
    sec_requests_per_second: float = Field(default=5.0, gt=0, le=10)

    @field_validator("raw_data_dir", "staged_data_dir", mode="before")
    @classmethod
    def resolve_project_path(cls, value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def write_database_url(self) -> str:
        return self.database_write_url or self.database_url

    def require_sec_identity(self) -> None:
        if not self.sec_user_agent or "@" not in self.sec_user_agent:
            raise ValueError(
                "SEC_USER_AGENT must identify the project and contain a real contact email, "
                "for example 'RetailFinanceLens analyst@example.com'."
            )


COMPANIES = {
    "WMT": {"name": "Walmart Inc.", "cik": "0000104169", "ticker": "WMT", "fiscal_year_end": "0131", "fiscal_year_end_month": 1, "fiscal_year_label_offset": 0},
    "TGT": {"name": "Target Corporation", "cik": "0000027419", "ticker": "TGT", "fiscal_year_end": "nearest Saturday to 0131", "fiscal_year_end_month": 1, "fiscal_year_label_offset": -1},
    "COST": {"name": "Costco Wholesale Corporation", "cik": "0000909832", "ticker": "COST", "fiscal_year_end": "nearest Sunday to 0831", "fiscal_year_end_month": 8, "fiscal_year_label_offset": 0},
}
