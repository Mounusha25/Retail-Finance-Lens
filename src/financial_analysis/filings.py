from __future__ import annotations

from datetime import date, datetime
from typing import Any


def parse_recent_filings(payload: dict[str, Any], cik: str) -> list[dict[str, Any]]:
    recent = payload.get("filings", {}).get("recent", {})
    keys = [
        "accessionNumber",
        "filingDate",
        "reportDate",
        "acceptanceDateTime",
        "form",
        "primaryDocument",
    ]
    row_count = len(recent.get("accessionNumber", []))
    rows: list[dict[str, Any]] = []
    for index in range(row_count):
        row = {key: recent.get(key, [None] * row_count)[index] for key in keys}
        if row["form"] not in {"10-K", "10-K/A", "10-Q", "10-Q/A"}:
            continue
        accession = row["accessionNumber"]
        primary = row["primaryDocument"]
        accession_plain = accession.replace("-", "")
        source_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_plain}/{primary}"
        accepted = row.get("acceptanceDateTime")
        if accepted and accepted.endswith("Z"):
            accepted = accepted[:-1] + "+00:00"
        rows.append(
            {
                "accession_number": accession,
                "form": row["form"],
                "report_date": date.fromisoformat(row["reportDate"]) if row.get("reportDate") else None,
                "filed_at": date.fromisoformat(row["filingDate"]),
                "accepted_at": datetime.fromisoformat(accepted) if accepted else None,
                "primary_document": primary,
                "source_url": source_url,
                "is_amendment": row["form"].endswith("/A"),
            }
        )
    return rows
