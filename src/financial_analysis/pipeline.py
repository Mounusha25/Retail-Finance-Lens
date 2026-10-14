from __future__ import annotations

import gzip
import hashlib
import json
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .config import COMPANIES, PROJECT_ROOT, Settings
from .db import initialize_database, make_engine, session_factory
from .filings import parse_recent_filings
from .inline_xbrl import extract_inline_revenue_facts, load_inline_rules
from .models import Company, ConceptMapping, Filing, FinancialFact, IngestionRun, SourcePayload
from .sec_client import RawResponse, SecClient, read_gzip_json
from .transform import (
    CanonicalFact,
    ConceptRegistry,
    derive_standalone_quarters,
    derive_total_revenue,
    extract_company_facts,
    write_staged_facts,
)
from .validate import run_validations


LOGGER = logging.getLogger(__name__)
MANIFEST_NAME = "raw_manifest.json"


def _normalize_tickers(tickers: Iterable[str]) -> list[str]:
    normalized = [ticker.strip().upper() for ticker in tickers if ticker.strip()]
    unknown = sorted(set(normalized) - set(COMPANIES))
    if unknown:
        raise ValueError(f"Unknown companies: {', '.join(unknown)}")
    return normalized


def ingest(settings: Settings, tickers: Iterable[str]) -> list[dict[str, Any]]:
    settings.require_sec_identity()
    records: list[dict[str, Any]] = []
    with SecClient(
        settings.sec_user_agent,
        settings.raw_data_dir,
        settings.sec_requests_per_second,
    ) as client:
        for ticker in _normalize_tickers(tickers):
            company = COMPANIES[ticker]
            submissions_response = client.fetch_json("submissions", company["cik"], ticker)
            records.append(_manifest_record(ticker, submissions_response))
            LOGGER.info("Fetched %s submissions to %s", ticker, submissions_response.file_path)

            facts_response = client.fetch_json("companyfacts", company["cik"], ticker)
            records.append(_manifest_record(ticker, facts_response))
            LOGGER.info("Fetched %s companyfacts to %s", ticker, facts_response.file_path)

            filings = parse_recent_filings(submissions_response.json(), company["cik"])
            annuals = [item for item in filings if item["form"].replace("/A", "") == "10-K"][:8]
            quarters = [item for item in filings if item["form"].replace("/A", "") == "10-Q"][:20]
            for filing in [*annuals, *quarters]:
                if not filing.get("primary_document"):
                    continue
                response = client.fetch_filing_document(
                    ticker,
                    filing["accession_number"],
                    filing["source_url"],
                )
                records.append(_manifest_record(ticker, response, filing["accession_number"]))
                LOGGER.info("Fetched %s filing %s", ticker, filing["accession_number"])
    manifest_path = settings.staged_data_dir / MANIFEST_NAME
    existing = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    by_hash = {item["sha256"]: item for item in [*existing, *records]}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(list(by_hash.values()), indent=2, sort_keys=True), encoding="utf-8")
    return records


def _manifest_record(
    ticker: str,
    response: RawResponse,
    accession_number: str | None = None,
) -> dict[str, Any]:
    record = {
        "ticker": ticker,
        "endpoint": response.endpoint,
        "url": response.url,
        "fetched_at": response.fetched_at.isoformat(),
        "http_status": response.status_code,
        "headers": response.headers,
        "sha256": response.sha256,
        "file_path": str(response.file_path),
    }
    if accession_number:
        record["accession_number"] = accession_number
    return record


def _latest_manifest_entries(settings: Settings) -> dict[tuple[str, str, str], dict[str, Any]]:
    manifest_path = settings.staged_data_dir / MANIFEST_NAME
    if not manifest_path.exists():
        raise FileNotFoundError("No raw manifest. Run the ingest command first.")
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    latest: dict[tuple[str, str, str], dict[str, Any]] = {}
    for entry in entries:
        key = (entry["ticker"], entry["endpoint"], entry.get("accession_number", ""))
        if key not in latest or entry["fetched_at"] > latest[key]["fetched_at"]:
            latest[key] = entry
    return latest


def transform(settings: Settings, tickers: Iterable[str], as_of: date | None = None) -> dict[str, int]:
    registry = ConceptRegistry.from_yaml(PROJECT_ROOT / "config" / "concepts.yml")
    inline_rules = load_inline_rules(PROJECT_ROOT / "config" / "inline_concepts.yml")
    latest = _latest_manifest_entries(settings)
    counts: dict[str, int] = {}
    for ticker in _normalize_tickers(tickers):
        facts_entry = latest.get((ticker, "companyfacts", ""))
        submissions_entry = latest.get((ticker, "submissions", ""))
        if not facts_entry or not submissions_entry:
            raise FileNotFoundError(f"Raw submissions and Company Facts are required for {ticker}")
        payload = read_gzip_json(Path(facts_entry["file_path"]))
        facts = extract_company_facts(payload, ticker, COMPANIES[ticker]["cik"], registry)
        submissions = read_gzip_json(Path(submissions_entry["file_path"]))
        filings = parse_recent_filings(submissions, COMPANIES[ticker]["cik"])
        if as_of:
            filings = [filing for filing in filings if filing["filed_at"] <= as_of]
        filing_by_accession = {filing["accession_number"]: filing for filing in filings}
        for key, entry in latest.items():
            if key[0] != ticker or key[1] != "filing":
                continue
            accession = entry.get("accession_number")
            filing = filing_by_accession.get(accession)
            if filing is None:
                continue
            with gzip.open(Path(entry["file_path"]), "rb") as stream:
                facts.extend(
                    extract_inline_revenue_facts(
                        stream.read(),
                        ticker,
                        COMPANIES[ticker]["cik"],
                        filing,
                        inline_rules,
                    )
                )
        if as_of:
            facts = [fact for fact in facts if fact.filed_at <= as_of]
        facts.extend(derive_total_revenue(facts))
        facts.extend(derive_standalone_quarters(facts))
        facts.extend(derive_total_revenue(facts))
        facts_path = settings.staged_data_dir / f"{ticker.lower()}_facts.jsonl"
        write_staged_facts(facts_path, facts)

        filing_path = settings.staged_data_dir / f"{ticker.lower()}_filings.json"
        filing_path.write_text(
            json.dumps(filings, default=lambda item: item.isoformat(), indent=2, sort_keys=True), encoding="utf-8"
        )
        counts[ticker] = len(facts)
        LOGGER.info("Staged %s facts for %s", len(facts), ticker)
    return counts


def _load_fact_line(line: str) -> dict[str, Any]:
    item = json.loads(line)
    for field in ("period_start", "period_end", "filed_at"):
        item[field] = date.fromisoformat(item[field]) if item.get(field) else None
    item["normalized_value"] = Decimal(item["normalized_value"])
    item.pop("priority", None)
    return item


def _upsert_company(session: Session, ticker: str) -> Company:
    definition = COMPANIES[ticker]
    company_values = {
        key: value
        for key, value in definition.items()
        if key not in {"fiscal_year_label_offset", "fiscal_year_end_month"}
    }
    statement = insert(Company).values(**company_values, currency="USD")
    statement = statement.on_conflict_do_update(
        index_elements=[Company.cik],
        set_={"name": definition["name"], "ticker": ticker, "fiscal_year_end": definition["fiscal_year_end"]},
    ).returning(Company.id)
    company_id = session.execute(statement).scalar_one()
    return session.get(Company, company_id)


def _load_mappings(session: Session, registry: ConceptRegistry, companies: dict[str, Company]) -> None:
    for alias in registry.aliases:
        company_id = companies[alias.company].id if alias.company else None
        statement = insert(ConceptMapping).values(
            company_id=company_id,
            scope=alias.company or "*",
            canonical_concept=alias.canonical,
            taxonomy=alias.taxonomy,
            source_concept=alias.concept,
            period_type=alias.period_type,
            priority=alias.priority,
            notes="Configured in config/concepts.yml",
        )
        statement = statement.on_conflict_do_nothing(constraint="uq_concept_mapping")
        session.execute(statement)
    for rule in load_inline_rules(PROJECT_ROOT / "config" / "inline_concepts.yml"):
        members = "dimensional-components" if rule.member_any else rule.dimensions or "consolidated"
        statement = insert(ConceptMapping).values(
            company_id=companies[rule.company].id,
            scope=rule.company,
            canonical_concept=rule.canonical,
            taxonomy=rule.taxonomy,
            source_concept=f"{rule.concept}@{members}",
            period_type="duration",
            priority=1,
            notes="Configured dimensional inline-XBRL mapping in config/inline_concepts.yml",
        ).on_conflict_do_nothing(constraint="uq_concept_mapping")
        session.execute(statement)


def _load_payloads(session: Session, settings: Settings, companies: dict[str, Company], run_id: uuid.UUID) -> None:
    manifest_path = settings.staged_data_dir / MANIFEST_NAME
    for item in json.loads(manifest_path.read_text(encoding="utf-8")):
        if item["ticker"] not in companies:
            continue
        path = Path(item["file_path"])
        if not path.exists():
            LOGGER.warning("Raw payload listed in manifest is missing: %s", path)
            continue
        statement = insert(SourcePayload).values(
            run_id=run_id,
            company_id=companies[item["ticker"]].id,
            endpoint=item["endpoint"],
            url=item["url"],
            fetched_at=datetime.fromisoformat(item["fetched_at"]),
            http_status=item["http_status"],
            response_headers=item["headers"],
            sha256=item["sha256"],
            content_encoding="gzip",
            body=path.read_bytes(),
            file_path=str(path),
        ).on_conflict_do_nothing(index_elements=[SourcePayload.sha256])
        session.execute(statement)


def _fact_natural_key(company_id: int, values: dict[str, Any]) -> str:
    parts = [
        str(company_id),
        values["accession_number"],
        values["canonical_concept"],
        values["source_concept"],
        values["period_start"].isoformat() if values["period_start"] else "",
        values["period_end"].isoformat(),
        values["unit"],
        values["dimension_hash"],
        "1" if values["is_derived"] else "0",
    ]
    # Reported facts are immutable within an accession. A derived value can
    # legitimately change when calculation logic is corrected, so its value is
    # part of the version key. This preserves the earlier calculation for audit
    # history while allowing the analytical views to select the newest version.
    if values["is_derived"]:
        parts.append(str(values["normalized_value"]))
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def load(settings: Settings, tickers: Iterable[str], run_id: uuid.UUID | None = None) -> uuid.UUID:
    selected_tickers = _normalize_tickers(tickers)
    engine = make_engine(settings.write_database_url)
    initialize_database(engine)
    factory = session_factory(engine)
    run_id = run_id or uuid.uuid4()
    registry = ConceptRegistry.from_yaml(PROJECT_ROOT / "config" / "concepts.yml")
    with factory.begin() as session:
        run = session.get(IngestionRun, run_id)
        if run is None:
            run = IngestionRun(id=run_id, status="loading", parameters={"companies": selected_tickers})
            session.add(run)
            session.flush()
        companies = {ticker: _upsert_company(session, ticker) for ticker in selected_tickers}
        _load_mappings(session, registry, companies)
        _load_payloads(session, settings, companies, run_id)

        filing_ids: dict[tuple[str, str], int] = {}
        for ticker in selected_tickers:
            filing_path = settings.staged_data_dir / f"{ticker.lower()}_filings.json"
            for raw in json.loads(filing_path.read_text(encoding="utf-8")):
                values = dict(raw)
                values["company_id"] = companies[ticker].id
                values["report_date"] = date.fromisoformat(values["report_date"]) if values["report_date"] else None
                values["filed_at"] = date.fromisoformat(values["filed_at"])
                values["accepted_at"] = (
                    datetime.fromisoformat(values["accepted_at"]) if values["accepted_at"] else None
                )
                statement = insert(Filing).values(**values)
                statement = statement.on_conflict_do_update(
                    constraint="uq_filing_company_accession",
                    set_={
                        "form": values["form"],
                        "report_date": values["report_date"],
                        "filed_at": values["filed_at"],
                        "accepted_at": values["accepted_at"],
                        "primary_document": values["primary_document"],
                        "source_url": values["source_url"],
                        "is_amendment": values["is_amendment"],
                    },
                ).returning(Filing.id)
                filing_ids[(ticker, values["accession_number"])] = session.execute(statement).scalar_one()

        for ticker in selected_tickers:
            facts_path = settings.staged_data_dir / f"{ticker.lower()}_facts.jsonl"
            with facts_path.open(encoding="utf-8") as stream:
                for line in stream:
                    values = _load_fact_line(line)
                    values["company_id"] = companies[ticker].id
                    values["filing_id"] = filing_ids.get((ticker, values["accession_number"]))
                    values["natural_key_hash"] = _fact_natural_key(companies[ticker].id, values)
                    statement = insert(FinancialFact).values(**values)
                    statement = statement.on_conflict_do_nothing(index_elements=[FinancialFact.natural_key_hash])
                    session.execute(statement)
        run.status = "loaded"
    return run_id


def validate(settings: Settings, run_id: uuid.UUID | None = None) -> dict[str, int]:
    engine = make_engine(settings.write_database_url)
    factory = session_factory(engine)
    effective_run_id = run_id or uuid.uuid4()
    with factory.begin() as session:
        run = session.get(IngestionRun, effective_run_id)
        if run is None:
            run = IngestionRun(
                id=effective_run_id,
                status="validating",
                parameters={"command": "validate"},
            )
            session.add(run)
            session.flush()
        counts = run_validations(session, effective_run_id)
        run.status = "completed" if counts.get("error", 0) == 0 else "completed_with_errors"
        run.finished_at = datetime.now(timezone.utc)
    return counts


def refresh(settings: Settings, tickers: Iterable[str], as_of: date | None = None) -> tuple[uuid.UUID, dict[str, int]]:
    tickers = _normalize_tickers(tickers)
    ingest(settings, tickers)
    transform(settings, tickers, as_of)
    run_id = load(settings, tickers)
    counts = validate(settings, run_id)
    return run_id, counts
