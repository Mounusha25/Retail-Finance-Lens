from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml
from lxml import html

from .transform import CanonicalFact, classify_period, issuer_fiscal_year


@dataclass(frozen=True)
class InlineRule:
    company: str
    canonical: str
    taxonomy: str
    concept: str
    dimensions: str | None = None
    member_any: tuple[str, ...] = ()
    aggregate_members: bool = False

    @property
    def qualified_name(self) -> str:
        return f"{self.taxonomy}:{self.concept}"


def load_inline_rules(path: Path) -> list[InlineRule]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        InlineRule(
            company=item["company"],
            canonical=item["canonical"],
            taxonomy=item["taxonomy"],
            concept=item["concept"],
            dimensions=item.get("dimensions"),
            member_any=tuple(item.get("member_any", [])),
            aggregate_members=bool(item.get("aggregate_members", False)),
        )
        for item in payload["rules"]
    ]


def _children_by_suffix(element: Any, suffix: str) -> list[Any]:
    return [child for child in element.iter() if str(child.tag).lower().endswith(suffix)]


def _context_index(root: Any) -> dict[str, dict[str, Any]]:
    contexts: dict[str, dict[str, Any]] = {}
    for element in root.xpath("//*[@id]"):
        if not str(element.tag).lower().endswith("context"):
            continue
        starts = _children_by_suffix(element, "startdate")
        ends = _children_by_suffix(element, "enddate")
        instants = _children_by_suffix(element, "instant")
        dimensions = {
            member.get("dimension", "unknown"): " ".join(member.itertext()).strip()
            for member in _children_by_suffix(element, "explicitmember")
        }
        contexts[element.get("id")] = {
            "start": date.fromisoformat(starts[0].text.strip()) if starts and starts[0].text else None,
            "end": date.fromisoformat(
                (ends[0].text if ends else instants[0].text).strip()
            ) if ends or instants else None,
            "dimensions": dimensions,
        }
    return contexts


def _numeric_value(element: Any) -> Decimal | None:
    if str(element.get("nil", "")).lower() == "true":
        return None
    raw = "".join(element.itertext()).strip()
    cleaned = re.sub(r"[^0-9.()-]", "", raw)
    if not cleaned or cleaned in {"-", "—", "–"}:
        return None
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    if negative or element.get("sign") == "-":
        value = -value
    scale = int(element.get("scale", "0"))
    return value * (Decimal(10) ** scale)


def _quarter_label(ticker: str, form: str, end: date, kind: str) -> str | None:
    if kind == "annual":
        return "FY"
    if form.replace("/A", "") != "10-Q":
        return None
    fiscal_end_month = {"WMT": 1, "TGT": 1, "COST": 8}[ticker]
    month_distance = (end.month - fiscal_end_month) % 12
    if 2 <= month_distance <= 4:
        return "Q1"
    if 5 <= month_distance <= 7:
        return "Q2"
    if 8 <= month_distance <= 10:
        return "Q3"
    return None


def _dimension_hash(dimensions: dict[str, Any]) -> str:
    encoded = json.dumps(dimensions, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def extract_inline_revenue_facts(
    content: bytes,
    ticker: str,
    cik: str,
    filing: dict[str, Any],
    rules: list[InlineRule],
) -> list[CanonicalFact]:
    root = html.fromstring(content)
    contexts = _context_index(root)
    company_rules = [rule for rule in rules if rule.company == ticker]
    matched: list[tuple[InlineRule, Any, dict[str, Any], Decimal, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for element in root.xpath("//*[contains(name(), 'nonfraction')]"):
        name = element.get("name", "")
        context_ref = element.get("contextref")
        context = contexts.get(context_ref)
        if context is None or context["end"] is None:
            continue
        value = _numeric_value(element)
        if value is None:
            continue
        members = set(context["dimensions"].values())
        for rule in company_rules:
            if name.lower() != rule.qualified_name.lower():
                continue
            if rule.dimensions == "none" and members:
                continue
            if rule.member_any and not members.intersection(rule.member_any):
                continue
            member_label = "+".join(sorted(members.intersection(rule.member_any)))
            unique = (rule.canonical, context_ref, str(value), member_label)
            if unique in seen:
                continue
            seen.add(unique)
            matched.append((rule, element, context, value, member_label))

    grouped: dict[tuple[Any, ...], list[tuple[InlineRule, Any, dict[str, Any], Decimal, str]]] = {}
    for item in matched:
        rule, _, context, _, member_label = item
        component = "aggregate" if rule.aggregate_members else member_label
        key = (rule.canonical, context["start"], context["end"], component)
        grouped.setdefault(key, []).append(item)

    facts: list[CanonicalFact] = []
    for (canonical, start, end, _), items in grouped.items():
        rule = items[0][0]
        values_by_member: dict[str, Decimal] = {}
        for _, _, _, value, member_label in items:
            values_by_member.setdefault(member_label or "consolidated", value)
        value = sum(values_by_member.values(), Decimal("0"))
        kind, days, is_53_week = classify_period(filing["form"], start, end)
        if kind not in {"annual", "quarterly", "ytd"}:
            continue
        dimensions = {"inline_components": sorted(values_by_member)} if rule.aggregate_members else items[0][2]["dimensions"]
        source_suffix = "+".join(sorted(values_by_member))
        facts.append(
            CanonicalFact(
                accession_number=filing["accession_number"],
                canonical_concept=canonical,
                taxonomy=rule.taxonomy,
                source_concept=f"inline:{rule.concept}|{source_suffix}",
                raw_value=str(value),
                normalized_value=value,
                unit="USD",
                decimals=items[0][1].get("decimals"),
                period_start=start,
                period_end=end,
                period_kind=kind,
                fiscal_days=days,
                is_53_week=is_53_week,
                issuer_fiscal_year=issuer_fiscal_year(ticker, filing["form"], end),
                issuer_fiscal_period=_quarter_label(ticker, filing["form"], end, kind),
                fiscal_end_year=end.year,
                form=filing["form"],
                filed_at=filing["filed_at"],
                frame=None,
                dimensions=dimensions,
                dimension_hash=_dimension_hash(dimensions),
                is_derived=False,
                derivation="Extracted from dimensional inline XBRL in the filing primary document",
                source_url=filing["source_url"],
                priority=1,
            )
        )
    return facts
