from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

import yaml

from .config import COMPANIES


FLOW_CONCEPTS = {
    "net_sales",
    "membership_other_revenue",
    "total_revenue",
    "cost_of_sales",
    "operating_income",
    "net_income",
    "operating_cash_flow",
    "capital_expenditures",
    "investing_cash_flow",
    "financing_cash_flow",
    "fx_effect_on_cash",
    "net_change_in_cash",
    "income_tax_expense",
    "dividends_paid",
    "share_repurchases",
    "debt_issued",
    "debt_repaid",
}


@dataclass(frozen=True)
class Alias:
    canonical: str
    taxonomy: str
    concept: str
    period_type: str
    priority: int
    company: str | None = None
    normalize: str | None = None


@dataclass(frozen=True)
class CanonicalFact:
    accession_number: str
    canonical_concept: str
    taxonomy: str
    source_concept: str
    raw_value: str
    normalized_value: Decimal
    unit: str
    decimals: str | None
    period_start: date | None
    period_end: date
    period_kind: str
    fiscal_days: int | None
    is_53_week: bool
    issuer_fiscal_year: int | None
    issuer_fiscal_period: str | None
    fiscal_end_year: int
    form: str
    filed_at: date
    frame: str | None
    dimensions: dict[str, Any]
    dimension_hash: str
    is_derived: bool
    derivation: str | None
    source_url: str
    priority: int = 100

    def to_json(self) -> dict[str, Any]:
        output = asdict(self)
        for key in ("period_start", "period_end", "filed_at"):
            output[key] = output[key].isoformat() if output[key] else None
        output["normalized_value"] = str(output["normalized_value"])
        return output


class ConceptRegistry:
    def __init__(self, aliases: list[Alias]) -> None:
        self.aliases = aliases

    @classmethod
    def from_yaml(cls, path: Path) -> "ConceptRegistry":
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        aliases: list[Alias] = []
        for canonical, definition in payload["concepts"].items():
            for item in definition["aliases"]:
                aliases.append(
                    Alias(
                        canonical=canonical,
                        taxonomy=item["taxonomy"],
                        concept=item["concept"],
                        period_type=definition["period_type"],
                        priority=int(item.get("priority", 100)),
                        company=item.get("company"),
                        normalize=definition.get("normalize"),
                    )
                )
        return cls(aliases)

    def for_company(self, ticker: str) -> list[Alias]:
        return [alias for alias in self.aliases if alias.company in (None, ticker)]


def parse_iso_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def classify_period(form: str, start: date | None, end: date) -> tuple[str, int | None, bool]:
    if start is None:
        return "instant", None, False
    days = (end - start).days + 1
    base_form = form.replace("/A", "")
    if base_form == "10-K" and 300 <= days <= 390:
        return "annual", days, days >= 369
    if base_form == "10-Q" and 60 <= days <= 120:
        return "quarterly", days, False
    if base_form == "10-Q" and 121 <= days <= 300:
        return "ytd", days, False
    return "other", days, False


def issuer_fiscal_year(ticker: str, form: str, end: date) -> int:
    definition = COMPANIES[ticker]
    offset = int(definition["fiscal_year_label_offset"])
    if form.replace("/A", "") == "10-K":
        return end.year + offset
    end_month = int(definition["fiscal_year_end_month"])
    rollover = 1 if end.month > end_month else 0
    return end.year + rollover + offset


def _dimensions(entry: dict[str, Any]) -> dict[str, Any]:
    ignored = {"start", "end", "val", "accn", "fy", "fp", "form", "filed", "frame", "decimals"}
    return {key: value for key, value in entry.items() if key not in ignored}


def _dimension_hash(dimensions: dict[str, Any]) -> str:
    encoded = json.dumps(dimensions, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _source_url(cik: str, accession: str) -> str:
    accession_plain = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_plain}/"


def extract_company_facts(
    payload: dict[str, Any], ticker: str, cik: str, registry: ConceptRegistry
) -> list[CanonicalFact]:
    candidates: list[CanonicalFact] = []
    facts = payload.get("facts", {})
    for alias in registry.for_company(ticker):
        concept = facts.get(alias.taxonomy, {}).get(alias.concept)
        if not concept:
            continue
        for unit, entries in concept.get("units", {}).items():
            if unit not in {"USD", "usd"}:
                continue
            for entry in entries:
                form = str(entry.get("form", ""))
                if form not in {"10-K", "10-K/A", "10-Q", "10-Q/A"}:
                    continue
                end = parse_iso_date(entry.get("end"))
                start = parse_iso_date(entry.get("start"))
                filed = parse_iso_date(entry.get("filed"))
                accession = entry.get("accn")
                if end is None or filed is None or not accession:
                    continue
                kind, days, is_53_week = classify_period(form, start, end)
                if alias.period_type == "instant" and kind != "instant":
                    continue
                if alias.period_type == "duration" and kind == "instant":
                    continue
                dimensions = _dimensions(entry)
                # Consolidated facts have no segment/dimensional members in Company Facts.
                if dimensions:
                    continue
                try:
                    value = Decimal(str(entry["val"]))
                except (KeyError, InvalidOperation):
                    continue
                normalized = abs(value) if alias.normalize == "absolute" else value
                candidates.append(
                    CanonicalFact(
                        accession_number=accession,
                        canonical_concept=alias.canonical,
                        taxonomy=alias.taxonomy,
                        source_concept=alias.concept,
                        raw_value=str(entry["val"]),
                        normalized_value=normalized,
                        unit="USD",
                        decimals=str(entry["decimals"]) if entry.get("decimals") is not None else None,
                        period_start=start,
                        period_end=end,
                        period_kind=kind,
                        fiscal_days=days,
                        is_53_week=is_53_week,
                        # SEC `fy` identifies the filing's fiscal year, including comparative facts.
                        # The issuer label is therefore derived from the fact period end and the
                        # documented company calendar instead of copied from a later filing.
                        issuer_fiscal_year=issuer_fiscal_year(ticker, form, end),
                        issuer_fiscal_period=entry.get("fp"),
                        fiscal_end_year=end.year,
                        form=form,
                        filed_at=filed,
                        frame=entry.get("frame"),
                        dimensions=dimensions,
                        dimension_hash=_dimension_hash(dimensions),
                        is_derived=False,
                        derivation=None,
                        source_url=_source_url(cik, accession),
                        priority=alias.priority,
                    )
                )

    selected: dict[tuple[Any, ...], CanonicalFact] = {}
    for fact in sorted(candidates, key=lambda item: item.priority):
        key = (
            fact.accession_number,
            fact.canonical_concept,
            fact.period_start,
            fact.period_end,
            fact.unit,
            fact.dimension_hash,
        )
        selected.setdefault(key, fact)
    return sorted(selected.values(), key=lambda item: (item.period_end, item.canonical_concept, item.filed_at))


def derive_q4_facts(facts: Iterable[CanonicalFact]) -> list[CanonicalFact]:
    items = list(facts)
    annuals = [fact for fact in items if fact.period_kind == "annual" and fact.canonical_concept in FLOW_CONCEPTS]
    ytds = [
        fact
        for fact in items
        if fact.period_kind == "ytd"
        and fact.canonical_concept in FLOW_CONCEPTS
        and fact.issuer_fiscal_period == "Q3"
    ]
    derived: list[CanonicalFact] = []
    for annual in annuals:
        matching = [
            ytd
            for ytd in ytds
            if ytd.canonical_concept == annual.canonical_concept
            and ytd.issuer_fiscal_year == annual.issuer_fiscal_year
            and ytd.period_end < annual.period_end
        ]
        if not matching:
            continue
        same_source = [item for item in matching if item.source_concept == annual.source_concept]
        same_priority = [item for item in matching if item.priority == annual.priority]
        comparable = same_source or same_priority or matching
        ytd = max(comparable, key=lambda item: (item.period_end, item.filed_at, -item.priority))
        q4_start = ytd.period_end.fromordinal(ytd.period_end.toordinal() + 1)
        q4_days = (annual.period_end - q4_start).days + 1
        derived.append(
            replace(
                annual,
                source_concept=f"derived:{annual.source_concept}:q4",
                raw_value=str(annual.normalized_value - ytd.normalized_value),
                normalized_value=annual.normalized_value - ytd.normalized_value,
                period_start=q4_start,
                period_kind="quarterly",
                fiscal_days=q4_days,
                is_53_week=False,
                issuer_fiscal_period="Q4",
                is_derived=True,
                derivation=f"annual {annual.accession_number} minus Q3 YTD {ytd.accession_number}",
                priority=annual.priority,
            )
        )
    return derived


def derive_standalone_quarters(facts: Iterable[CanonicalFact]) -> list[CanonicalFact]:
    """Derive missing Q2/Q3 flows from YTD facts and Q4 from the annual fact."""
    items = list(facts)
    derived: list[CanonicalFact] = []
    explicit = {
        (fact.canonical_concept, fact.issuer_fiscal_year, fact.issuer_fiscal_period, fact.period_end)
        for fact in items
        if fact.period_kind == "quarterly"
    }
    ytds = [fact for fact in items if fact.period_kind == "ytd" and fact.canonical_concept in FLOW_CONCEPTS]
    for current in ytds:
        if current.issuer_fiscal_period not in {"Q2", "Q3"}:
            continue
        key = (current.canonical_concept, current.issuer_fiscal_year, current.issuer_fiscal_period, current.period_end)
        if key in explicit:
            continue
        predecessor_period = "Q1" if current.issuer_fiscal_period == "Q2" else "Q2"
        predecessors = [
            fact
            for fact in items
            if fact.canonical_concept == current.canonical_concept
            and fact.issuer_fiscal_year == current.issuer_fiscal_year
            and fact.issuer_fiscal_period == predecessor_period
            and fact.period_end < current.period_end
            and fact.period_kind in ({"quarterly"} if predecessor_period == "Q1" else {"ytd"})
        ]
        if not predecessors:
            continue
        same_source = [item for item in predecessors if item.source_concept == current.source_concept]
        same_priority = [item for item in predecessors if item.priority == current.priority]
        comparable = same_source or same_priority or predecessors
        previous = max(comparable, key=lambda item: (item.period_end, item.filed_at, -item.priority))
        quarter_start = previous.period_end.fromordinal(previous.period_end.toordinal() + 1)
        derived.append(
            replace(
                current,
                source_concept=f"derived:{current.source_concept}:{current.issuer_fiscal_period.lower()}",
                raw_value=str(current.normalized_value - previous.normalized_value),
                normalized_value=current.normalized_value - previous.normalized_value,
                period_start=quarter_start,
                period_kind="quarterly",
                fiscal_days=(current.period_end - quarter_start).days + 1,
                is_derived=True,
                derivation=(
                    f"{current.issuer_fiscal_period} YTD {current.accession_number} minus "
                    f"{predecessor_period} cumulative {previous.accession_number}"
                ),
            )
        )
    derived.extend(derive_q4_facts(items))
    return derived


def derive_total_revenue(facts: Iterable[CanonicalFact]) -> list[CanonicalFact]:
    """Create a traceable total-revenue fact only when both components are reported."""
    items = list(facts)
    existing = {
        (fact.accession_number, fact.period_start, fact.period_end, fact.period_kind)
        for fact in items
        if fact.canonical_concept == "total_revenue"
    }
    memberships = {
        (fact.accession_number, fact.period_start, fact.period_end, fact.period_kind): fact
        for fact in items
        if fact.canonical_concept == "membership_other_revenue"
    }
    derived: list[CanonicalFact] = []
    for sales in [fact for fact in items if fact.canonical_concept == "net_sales"]:
        key = (sales.accession_number, sales.period_start, sales.period_end, sales.period_kind)
        membership = memberships.get(key)
        if key in existing or membership is None:
            continue
        total = sales.normalized_value + membership.normalized_value
        derived.append(
            replace(
                sales,
                canonical_concept="total_revenue",
                source_concept="derived:net_sales+membership_other_revenue",
                raw_value=str(total),
                normalized_value=total,
                is_derived=True,
                derivation=(
                    f"net sales {sales.source_concept} plus membership/other revenue "
                    f"{membership.source_concept} in {sales.accession_number}"
                ),
            )
        )
    return derived


def derive_net_inventory(facts: Iterable[CanonicalFact]) -> list[CanonicalFact]:
    """Net LIFO inventory = FIFO inventory - LIFO reserve, from facts at the same date and filing.

    Applied only when the issuer reports no net inventory fact. Both components are point-in-time
    values at the same balance-sheet date, so this is arithmetic on one statement, not period differencing.
    """
    items = list(facts)
    existing = {
        (fact.accession_number, fact.period_end)
        for fact in items
        if fact.canonical_concept == "inventory"
    }
    reserves = {
        (fact.accession_number, fact.period_end): fact
        for fact in items
        if fact.canonical_concept == "lifo_reserve"
    }
    derived: list[CanonicalFact] = []
    for fifo in [fact for fact in items if fact.canonical_concept == "fifo_inventory"]:
        key = (fifo.accession_number, fifo.period_end)
        reserve = reserves.get(key)
        if key in existing or reserve is None:
            continue
        net = fifo.normalized_value - reserve.normalized_value
        derived.append(
            replace(
                fifo,
                canonical_concept="inventory",
                source_concept="derived:fifo_inventory-lifo_reserve",
                raw_value=str(net),
                normalized_value=net,
                is_derived=True,
                derivation=(
                    f"FIFO inventory {fifo.source_concept} less LIFO reserve "
                    f"{reserve.source_concept} in {fifo.accession_number}"
                ),
            )
        )
    return derived


def write_staged_facts(path: Path, facts: Iterable[CanonicalFact]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for fact in facts:
            stream.write(json.dumps(fact.to_json(), sort_keys=True) + "\n")
