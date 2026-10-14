from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from financial_analysis.config import PROJECT_ROOT
from financial_analysis.inline_xbrl import extract_inline_revenue_facts, load_inline_rules
from financial_analysis.transform import (
    ConceptRegistry,
    classify_period,
    derive_net_inventory,
    derive_q4_facts,
    derive_standalone_quarters,
    derive_total_revenue,
    extract_company_facts,
)


FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY = ConceptRegistry.from_yaml(PROJECT_ROOT / "config" / "concepts.yml")
INLINE_RULES = load_inline_rules(PROJECT_ROOT / "config" / "inline_concepts.yml")


@pytest.mark.parametrize(
    ("ticker", "cik", "expected_sales", "issuer_fy"),
    [
        ("WMT", "0000104169", Decimal("706413000000"), 2026),
        ("TGT", "0000027419", Decimal("104780000000"), 2025),
        ("COST", "0000909832", Decimal("297247000000"), 2026),
    ],
)
def test_extracts_company_specific_and_standard_concepts(ticker, cik, expected_sales, issuer_fy):
    payload = json.loads((FIXTURES / f"{ticker.lower()}_companyfacts.json").read_text())
    facts = extract_company_facts(payload, ticker, cik, REGISTRY)
    annual_sales = [fact for fact in facts if fact.canonical_concept == "net_sales" and fact.period_kind == "annual"]
    assert len(annual_sales) == 1
    assert annual_sales[0].normalized_value == expected_sales
    assert annual_sales[0].issuer_fiscal_year == issuer_fy
    assert annual_sales[0].fiscal_end_year == 2026
    assert any(fact.canonical_concept == "inventory" for fact in facts)


def test_derives_q4_from_annual_less_q3_ytd():
    payload = {"facts": {"us-gaap": {"SalesRevenueNet": {"units": {"USD": [
        {"start": "2025-02-01", "end": "2025-10-31", "val": 750, "accn": "q3", "fy": 2026, "fp": "Q3", "form": "10-Q", "filed": "2025-12-01"},
        {"start": "2025-02-01", "end": "2026-01-31", "val": 1000, "accn": "fy", "fy": 2026, "fp": "FY", "form": "10-K", "filed": "2026-03-13"}
    ]}}}}}
    facts = extract_company_facts(payload, "WMT", "0000104169", REGISTRY)
    q4 = [fact for fact in derive_q4_facts(facts) if fact.canonical_concept == "net_sales"]
    assert len(q4) == 1
    assert q4[0].normalized_value == Decimal("250")
    assert q4[0].period_start == date(2025, 11, 1)
    assert q4[0].period_end == date(2026, 1, 31)
    assert q4[0].is_derived is True


def test_q4_derivation_keeps_source_concept_families_separate():
    payload = {"facts": {"cost": {
        "NetSales": {"units": {"USD": [
            {"start": "2025-09-01", "end": "2026-05-10", "val": 203374, "accn": "q3", "fy": 2026, "fp": "Q3", "form": "10-Q", "filed": "2026-06-03"},
            {"start": "2025-09-01", "end": "2026-08-30", "val": 297247, "accn": "fy", "fy": 2026, "fp": "FY", "form": "10-K", "filed": "2026-10-07"},
        ]}},
    }}}
    product_facts = extract_company_facts(payload, "COST", "0000909832", REGISTRY)
    product_ytd = next(fact for fact in product_facts if fact.period_kind == "ytd")
    product_annual = next(fact for fact in product_facts if fact.period_kind == "annual")
    total_ytd = replace(
        product_ytd,
        source_concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        normalized_value=Decimal("207431"),
        priority=20,
    )
    total_annual = replace(
        product_annual,
        source_concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        normalized_value=Decimal("303154"),
        priority=20,
    )
    facts = [product_ytd, product_annual, total_ytd, total_annual]
    q4 = {
        fact.source_concept: fact.normalized_value
        for fact in derive_q4_facts(facts)
        if fact.canonical_concept == "net_sales"
    }
    assert q4["derived:RevenueFromContractWithCustomerExcludingAssessedTax:q4"] == Decimal("95723")
    assert q4["derived:NetSales:q4"] == Decimal("93873")


def test_period_classification_flags_53_week_year():
    kind, days, flag = classify_period("10-K", date(2023, 1, 29), date(2024, 2, 3))
    assert (kind, days, flag) == ("annual", 371, True)


def test_capex_sign_is_normalized_without_changing_missing_values():
    payload = {
        "facts": {
            "us-gaap": {
                "PaymentsToAcquirePropertyPlantAndEquipment": {
                    "units": {"USD": [{
                        "start": "2025-01-01", "end": "2025-12-31", "val": -100,
                        "accn": "0000000000-25-000001", "fy": 2025, "fp": "FY",
                        "form": "10-K", "filed": "2026-02-01"
                    }]}
                }
            }
        }
    }
    facts = extract_company_facts(payload, "WMT", "0000104169", REGISTRY)
    assert facts[0].raw_value == "-100"
    assert facts[0].normalized_value == Decimal("100")


def test_derives_q2_cash_flow_from_cumulative_values():
    payload = {
        "facts": {"us-gaap": {"NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
            {"start": "2025-02-01", "end": "2025-04-30", "val": 100, "accn": "a", "fy": 2026, "fp": "Q1", "form": "10-Q", "filed": "2025-05-15"},
            {"start": "2025-02-01", "end": "2025-07-31", "val": 240, "accn": "b", "fy": 2026, "fp": "Q2", "form": "10-Q", "filed": "2025-08-15"}
        ]}}}}
    }
    facts = extract_company_facts(payload, "WMT", "0000104169", REGISTRY)
    derived = derive_standalone_quarters(facts)
    q2 = [fact for fact in derived if fact.issuer_fiscal_period == "Q2"]
    assert len(q2) == 1
    assert q2[0].normalized_value == Decimal("140")
    assert q2[0].period_kind == "quarterly"


def test_total_revenue_requires_both_reported_components():
    payload = json.loads((FIXTURES / "cost_companyfacts.json").read_text())
    facts = extract_company_facts(payload, "COST", "0000909832", REGISTRY)
    totals = derive_total_revenue(facts)
    assert len(totals) == 1
    assert totals[0].normalized_value == Decimal("303154000000")
    assert totals[0].is_derived is True

    target = json.loads((FIXTURES / "tgt_companyfacts.json").read_text())
    target_facts = extract_company_facts(target, "TGT", "0000027419", REGISTRY)
    assert derive_total_revenue(target_facts) == []


def test_inline_xbrl_splits_target_sales_and_aggregates_other_revenue():
    document = b"""
    <html><body>
      <xbrli:context id="total"><xbrli:entity/><xbrli:period><xbrli:startDate>2025-02-02</xbrli:startDate><xbrli:endDate>2026-01-31</xbrli:endDate></xbrli:period></xbrli:context>
      <xbrli:context id="sales"><xbrli:entity><xbrli:segment><xbrldi:explicitMember dimension="srt:ProductOrServiceAxis">us-gaap:ProductMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>2025-02-02</xbrli:startDate><xbrli:endDate>2026-01-31</xbrli:endDate></xbrli:period></xbrli:context>
      <xbrli:context id="ads"><xbrli:entity><xbrli:segment><xbrldi:explicitMember dimension="srt:ProductOrServiceAxis">tgt:AdvertisingRevenueMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>2025-02-02</xbrli:startDate><xbrli:endDate>2026-01-31</xbrli:endDate></xbrli:period></xbrli:context>
      <xbrli:context id="cards"><xbrli:entity><xbrli:segment><xbrldi:explicitMember dimension="srt:ProductOrServiceAxis">tgt:CreditCardProfitSharingMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>2025-02-02</xbrli:startDate><xbrli:endDate>2026-01-31</xbrli:endDate></xbrli:period></xbrli:context>
      <ix:nonFraction name="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax" contextRef="total" unitRef="usd" scale="6">104,780</ix:nonFraction>
      <ix:nonFraction name="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax" contextRef="sales" unitRef="usd" scale="6">102,717</ix:nonFraction>
      <ix:nonFraction name="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax" contextRef="ads" unitRef="usd" scale="6">915</ix:nonFraction>
      <ix:nonFraction name="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax" contextRef="cards" unitRef="usd" scale="6">522</ix:nonFraction>
    </body></html>
    """
    filing = {
        "accession_number": "0000027419-26-000016",
        "form": "10-K",
        "filed_at": date(2026, 3, 11),
        "source_url": "https://www.sec.gov/example",
    }
    facts = extract_inline_revenue_facts(document, "TGT", "0000027419", filing, INLINE_RULES)
    values = {fact.canonical_concept: fact.normalized_value for fact in facts}
    assert values["total_revenue"] == Decimal("104780000000")
    assert values["net_sales"] == Decimal("102717000000")
    assert values["membership_other_revenue"] == Decimal("1437000000")
    assert all(fact.source_concept.startswith("inline:") for fact in facts)


def _kroger_payload(extra: dict | None = None) -> dict:
    instant = {"end": "2026-01-31", "accn": "0000056873-26-000010", "fy": 2025, "fp": "FY", "form": "10-K", "filed": "2026-03-31"}
    facts = {
        "FIFOInventoryAmount": {"units": {"USD": [{**instant, "val": 9445000000}]}},
        "InventoryLIFOReserve": {"units": {"USD": [{**instant, "val": 2553000000}]}},
    }
    facts.update(extra or {})
    return {"facts": {"us-gaap": facts}}


def test_net_inventory_is_fifo_less_lifo_reserve_when_not_reported():
    facts = extract_company_facts(_kroger_payload(), "KR", "0000056873", REGISTRY)
    derived = derive_net_inventory(facts)
    assert len(derived) == 1
    assert derived[0].canonical_concept == "inventory"
    assert derived[0].normalized_value == Decimal("6892000000")
    assert derived[0].is_derived is True
    assert "LIFO reserve" in (derived[0].derivation or "")


def test_net_inventory_not_derived_when_issuer_reports_inventory():
    reported = {
        "InventoryNet": {"units": {"USD": [
            {"end": "2026-01-31", "val": 6800000000, "accn": "0000056873-26-000010", "fy": 2025, "fp": "FY", "form": "10-K", "filed": "2026-03-31"}
        ]}}
    }
    facts = extract_company_facts(_kroger_payload(reported), "KR", "0000056873", REGISTRY)
    assert derive_net_inventory(facts) == []


def test_kroger_fiscal_labels_and_sixteen_week_first_quarter():
    from datetime import date

    from financial_analysis.transform import classify_period, issuer_fiscal_year

    assert issuer_fiscal_year("KR", "10-K", date(2026, 1, 31)) == 2025
    # Kroger's first quarter is 16 weeks (112 days) and must classify as a standalone quarter.
    kind, days, _ = classify_period("10-Q", date(2025, 2, 2), date(2025, 5, 24))
    assert (kind, days) == ("quarterly", 112)
