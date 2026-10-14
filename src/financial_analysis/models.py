from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    cik: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    ticker: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    fiscal_year_end: Mapped[str | None] = mapped_column(String(40))
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="running", nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    message: Mapped[str | None] = mapped_column(Text)


class SourcePayload(Base):
    __tablename__ = "source_payloads"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingestion_runs.id"))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    endpoint: Mapped[str] = mapped_column(String(40), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_headers: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    content_encoding: Mapped[str] = mapped_column(String(20), default="gzip", nullable=False)
    body: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)


class Filing(Base):
    __tablename__ = "filings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    accession_number: Mapped[str] = mapped_column(String(24), nullable=False)
    form: Mapped[str] = mapped_column(String(12), nullable=False)
    report_date: Mapped[date | None] = mapped_column(Date)
    filed_at: Mapped[date] = mapped_column(Date, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    primary_document: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    is_amendment: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("company_id", "accession_number", name="uq_filing_company_accession"),)


class ConceptMapping(Base):
    __tablename__ = "concept_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    scope: Mapped[str] = mapped_column(String(12), default="*", nullable=False)
    canonical_concept: Mapped[str] = mapped_column(String(80), nullable=False)
    taxonomy: Mapped[str] = mapped_column(String(80), nullable=False)
    source_concept: Mapped[str] = mapped_column(String(180), nullable=False)
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint(
            "scope", "canonical_concept", "taxonomy", "source_concept", name="uq_concept_mapping"
        ),
    )


class FinancialFact(Base):
    __tablename__ = "financial_facts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    filing_id: Mapped[int | None] = mapped_column(ForeignKey("filings.id"))
    accession_number: Mapped[str] = mapped_column(String(24), nullable=False)
    natural_key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    canonical_concept: Mapped[str] = mapped_column(String(80), nullable=False)
    taxonomy: Mapped[str] = mapped_column(String(80), nullable=False)
    source_concept: Mapped[str] = mapped_column(String(180), nullable=False)
    raw_value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[Decimal] = mapped_column(Numeric(30, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    decimals: Mapped[str | None] = mapped_column(String(20))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    fiscal_days: Mapped[int | None] = mapped_column(Integer)
    is_53_week: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    issuer_fiscal_year: Mapped[int | None] = mapped_column(Integer)
    issuer_fiscal_period: Mapped[str | None] = mapped_column(String(8))
    fiscal_end_year: Mapped[int] = mapped_column(Integer, nullable=False)
    form: Mapped[str] = mapped_column(String(12), nullable=False)
    filed_at: Mapped[date] = mapped_column(Date, nullable=False)
    frame: Mapped[str | None] = mapped_column(String(24))
    dimensions: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    dimension_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_derived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    derivation: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_fact_analysis", "company_id", "canonical_concept", "period_end", "period_kind"),
    )


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingestion_runs.id"))
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    accession_number: Mapped[str | None] = mapped_column(String(24))
    period_end: Mapped[date | None] = mapped_column(Date)
    check_name: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    observed_value: Mapped[Decimal | None] = mapped_column(Numeric(30, 4))
    expected_value: Mapped[Decimal | None] = mapped_column(Numeric(30, 4))
    tolerance: Mapped[Decimal | None] = mapped_column(Numeric(30, 4))
    details: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
