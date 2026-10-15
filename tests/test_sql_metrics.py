"""Seeds synthetic facts and asserts the analytics views compute hand-checked metrics."""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from financial_analysis.db import initialize_database, make_engine

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is not configured"
)

YEAR_1 = date(2024, 12, 31)
YEAR_2 = date(2025, 12, 31)

FACTS = {
    YEAR_1: {
        "net_sales": 1000, "membership_other_revenue": 100, "cost_of_sales": 800,
        "inventory": 100, "accounts_receivable_net_current": 50, "accounts_payable_current": 80,
        "current_debt": 10, "long_term_debt_noncurrent": 40, "cash_and_cash_equivalents": 40,
        "total_assets": 600, "total_equity": 200, "stockholders_equity": 190,
    },
    YEAR_2: {
        "net_sales": 1100, "membership_other_revenue": 100, "cost_of_sales": 880,
        "operating_income": 60, "net_income": 40, "inventory": 120,
        "accounts_receivable_net_current": 60, "accounts_payable_current": 100,
        "operating_cash_flow": 90, "capital_expenditures": 30,
        "current_assets": 300, "current_liabilities": 200,
        "cash_and_cash_equivalents": 50, "short_term_investments": 25,
        "current_debt": 10, "long_term_debt_noncurrent": 40, "short_term_borrowings": 5,
        "total_assets": 700, "total_equity": 220, "stockholders_equity": 210,
        "income_tax_expense": 15,
        "dividends_paid": 12, "share_repurchases": 8, "debt_issued": 30, "debt_repaid": 10,
    },
}
DURATION = {
    "net_sales", "membership_other_revenue", "cost_of_sales", "operating_income",
    "net_income", "operating_cash_flow", "capital_expenditures", "income_tax_expense",
    "dividends_paid", "share_repurchases", "debt_issued", "debt_repaid",
}
FISCAL_DAYS = {YEAR_1: 366, YEAR_2: 365}


@pytest.fixture()
def seeded():
    engine = make_engine(os.environ["TEST_DATABASE_URL"])
    initialize_database(engine)
    connection = engine.connect()
    transaction = connection.begin()
    try:
        # ZZA has every fact; ZZB omits short-term investments to test null propagation.
        for ticker, omit in (("ZZA", set()), ("ZZB", {"short_term_investments"})):
            company_id = connection.execute(
                text(
                    "INSERT INTO companies (cik, ticker, name, currency) "
                    "VALUES (:cik, :t, :n, 'USD') RETURNING id"
                ),
                {"cik": f"99{ticker}"[:10], "t": ticker, "n": f"Test {ticker}"},
            ).scalar_one()
            for period_end, concepts in FACTS.items():
                for concept, value in concepts.items():
                    if concept in omit:
                        continue
                    kind = "annual" if concept in DURATION else "instant"
                    connection.execute(
                        text(
                            """
                            INSERT INTO financial_facts (
                                company_id, accession_number, natural_key_hash, canonical_concept,
                                taxonomy, source_concept, raw_value, normalized_value, unit,
                                period_start, period_end, period_kind, fiscal_days, is_53_week,
                                fiscal_end_year, form, filed_at, dimensions, dimension_hash,
                                is_derived, source_url
                            ) VALUES (
                                :cid, :acc, :hash, :concept, 'us-gaap', :concept, :v, :v, 'USD',
                                :start, :end, :kind, :days, false, :fy, '10-K', :end, '{}', '',
                                false, 'https://example.test/filing'
                            )
                            """
                        ),
                        {
                            "cid": company_id,
                            "acc": f"{ticker}-{period_end.year}",
                            "hash": f"{ticker}-{concept}-{period_end}",
                            "concept": concept,
                            "v": value,
                            "start": date(period_end.year, 1, 1) if kind == "annual" else None,
                            "end": period_end,
                            "kind": kind,
                            "days": FISCAL_DAYS[period_end],
                            "fy": period_end.year,
                        },
                    )
        yield connection
    finally:
        transaction.rollback()
        connection.close()


def _latest(connection, ticker: str) -> dict:
    row = connection.execute(
        text(
            "SELECT * FROM analytics.v_annual_metrics WHERE ticker = :t ORDER BY period_end DESC LIMIT 1"
        ),
        {"t": ticker},
    ).mappings().one()
    return {k: float(v) if isinstance(v, Decimal) else v for k, v in row.items()}


def test_annual_metrics_match_hand_calculation(seeded):
    row = _latest(seeded, "ZZA")
    assert row["period_end"] == YEAR_2
    assert row["total_revenue"] == 1200
    assert row["revenue_growth"] == pytest.approx(0.10)
    assert row["gross_margin"] == pytest.approx(0.20)
    assert row["operating_margin"] == pytest.approx(60 / 1200)
    assert row["net_margin"] == pytest.approx(40 / 1200)
    assert row["free_cash_flow"] == 60
    assert row["ocf_to_net_income"] == pytest.approx(2.25)
    assert row["inventory_turnover"] == pytest.approx(880 / 110)
    assert row["days_inventory_outstanding"] == pytest.approx(110 / 880 * 365)
    assert row["receivable_days"] == pytest.approx(55 / 1100 * 365)
    assert row["payable_days"] == pytest.approx(90 / 880 * 365)
    assert row["cash_conversion_cycle"] == pytest.approx(
        55 / 1100 * 365 + 110 / 880 * 365 - 90 / 880 * 365
    )
    assert row["inventory_growth"] == pytest.approx(0.20)
    assert row["inventory_growth_gap"] == pytest.approx(0.10)
    assert row["current_ratio"] == pytest.approx(1.5)
    assert row["quick_ratio"] == pytest.approx((50 + 25 + 60) / 200)
    assert row["total_debt"] == 55  # current 10 + long-term 40 + short-term borrowings 5


def test_first_period_has_no_growth_or_average_balance_metrics(seeded):
    row = seeded.execute(
        text(
            "SELECT * FROM analytics.v_annual_metrics WHERE ticker = 'ZZA' AND period_end = :d"
        ),
        {"d": YEAR_1},
    ).mappings().one()
    assert row["revenue_growth"] is None
    assert row["inventory_turnover"] is None
    assert row["cash_conversion_cycle"] is None


def test_missing_short_term_investments_is_not_zero_filled(seeded):
    row = _latest(seeded, "ZZB")
    assert row["short_term_investments"] is None
    assert row["quick_ratio"] is None
    assert row["current_ratio"] == pytest.approx(1.5)


def test_roic_and_dupont_decomposition(seeded):
    row = _latest(seeded, "ZZA")
    # Invested capital = total debt + total equity - cash, averaged with the prior year.
    prior_ic = 10 + 40 + 200 - 40
    current_ic = 10 + 40 + 5 + 220 - 50
    tax_rate = 15 / (40 + 15)
    assert row["effective_tax_rate"] == pytest.approx(tax_rate)
    assert row["invested_capital"] == current_ic
    assert row["nopat"] == pytest.approx(60 * (1 - tax_rate))
    assert row["roic"] == pytest.approx(60 * (1 - tax_rate) / ((prior_ic + current_ic) / 2))
    assert row["return_on_equity"] == pytest.approx(40 / ((190 + 210) / 2))
    assert row["asset_turnover"] == pytest.approx(1200 / ((600 + 700) / 2))
    assert row["equity_multiplier"] == pytest.approx(((600 + 700) / 2) / ((190 + 210) / 2))
    # DuPont identity: margin x turnover x leverage reproduces ROE exactly.
    assert row["net_margin"] * row["asset_turnover"] * row["equity_multiplier"] == pytest.approx(
        row["return_on_equity"]
    )


def test_returns_are_null_without_prior_period(seeded):
    row = seeded.execute(
        text("SELECT * FROM analytics.v_annual_metrics WHERE ticker = 'ZZA' AND period_end = :d"),
        {"d": YEAR_1},
    ).mappings().one()
    assert row["roic"] is None
    assert row["return_on_equity"] is None


def test_capital_allocation_metrics(seeded):
    row = _latest(seeded, "ZZA")
    assert row["shareholder_payouts"] == 20
    assert row["payout_ratio_fcf"] == pytest.approx(20 / 60)
    assert row["capex_to_ocf"] == pytest.approx(30 / 90)
    assert row["net_debt_issuance"] == 20
    assert row["fcf_after_payouts"] == 40


# --- trailing twelve months -------------------------------------------------------------------

QUARTER_ENDS = [
    (date(2024, 1, 1), date(2024, 3, 31), 91),
    (date(2024, 4, 1), date(2024, 6, 30), 91),
    (date(2024, 7, 1), date(2024, 9, 30), 92),
    (date(2024, 10, 1), date(2024, 12, 31), 92),
    (date(2025, 1, 1), date(2025, 3, 31), 90),
    (date(2025, 4, 1), date(2025, 6, 30), 91),
    (date(2025, 7, 1), date(2025, 9, 30), 92),
    (date(2025, 10, 1), date(2025, 12, 31), 92),
]
PRIOR_SALES, LATEST_SALES = [100, 100, 100, 100], [110, 110, 120, 120]
LATEST_FLOWS = {
    "operating_income": 10, "net_income": 8, "income_tax_expense": 2, "operating_cash_flow": 15,
    "capital_expenditures": 5, "dividends_paid": 3, "share_repurchases": 2,
}
BALANCES = {
    date(2025, 12, 31): {
        "inventory": 50, "cash_and_cash_equivalents": 30, "current_debt": 100, "long_term_debt_noncurrent": 0,
        "total_equity": 300, "stockholders_equity": 290, "total_assets": 700,
    },
    date(2024, 12, 31): {
        "inventory": 40, "cash_and_cash_equivalents": 20, "current_debt": 90, "long_term_debt_noncurrent": 0,
        "total_equity": 260, "stockholders_equity": 250, "total_assets": 600,
    },
}


def _insert(connection, company_id, ticker, concept, value, start, end, kind, days):
    connection.execute(
        text(
            """
            INSERT INTO financial_facts (
                company_id, accession_number, natural_key_hash, canonical_concept, taxonomy, source_concept,
                raw_value, normalized_value, unit, period_start, period_end, period_kind, fiscal_days,
                is_53_week, fiscal_end_year, form, filed_at, dimensions, dimension_hash, is_derived, source_url
            ) VALUES (
                :cid, :acc, :hash, :concept, 'us-gaap', :concept, :v, :v, 'USD', :start, :end, :kind, :days,
                false, :fy, '10-Q', :end, '{}', '', false, 'https://example.test/filing'
            )
            """
        ),
        {
            "cid": company_id, "acc": f"{ticker}-{end}", "hash": f"{ticker}-{concept}-{end}-{kind}",
            "concept": concept, "v": value, "start": start, "end": end, "kind": kind, "days": days, "fy": end.year,
        },
    )


@pytest.fixture()
def ltm_connection():
    engine = make_engine(os.environ["TEST_DATABASE_URL"])
    initialize_database(engine)
    connection = engine.connect()
    transaction = connection.begin()
    try:
        # ZZL is complete; ZZG lacks capex in one of the four latest quarters.
        for ticker, skip_capex_in in (("ZZL", None), ("ZZG", date(2025, 6, 30))):
            company_id = connection.execute(
                text("INSERT INTO companies (cik, ticker, name, currency) VALUES (:c, :t, :n, 'USD') RETURNING id"),
                {"c": f"88{ticker}"[:10], "t": ticker, "n": f"Test {ticker}"},
            ).scalar_one()
            for index, (start, end, days) in enumerate(QUARTER_ENDS):
                latest = index >= 4
                sales = (LATEST_SALES if latest else PRIOR_SALES)[index % 4]
                values = {"net_sales": sales, "total_revenue": sales, "cost_of_sales": sales * 0.8}
                if latest:
                    values.update(LATEST_FLOWS)
                for concept, value in values.items():
                    if concept == "capital_expenditures" and end == skip_capex_in:
                        continue
                    _insert(connection, company_id, ticker, concept, value, start, end, "quarterly", days)
            for end, balances in BALANCES.items():
                for concept, value in balances.items():
                    _insert(connection, company_id, ticker, concept, value, None, end, "instant", None)
        yield connection
    finally:
        transaction.rollback()
        connection.close()


def _ltm(connection, ticker):
    row = connection.execute(
        text("SELECT * FROM analytics.v_ltm_metrics WHERE ticker = :t"), {"t": ticker}
    ).mappings().one()
    return {k: float(v) if isinstance(v, Decimal) else v for k, v in row.items()}


def test_ltm_sums_the_latest_four_quarters(ltm_connection):
    row = _ltm(ltm_connection, "ZZL")
    assert row["period_end"] == date(2025, 12, 31)
    assert row["is_complete"] is True
    assert row["fiscal_days"] == 365
    assert row["net_sales"] == 460
    assert row["prior_net_sales"] == 400
    assert row["revenue_growth"] == pytest.approx(0.15)
    assert row["cost_of_sales"] == pytest.approx(368)
    assert row["gross_margin"] == pytest.approx(0.20)
    assert row["operating_margin"] == pytest.approx(40 / 460)
    assert row["free_cash_flow"] == 40
    assert row["fcf_margin"] == pytest.approx(40 / 460)
    assert row["shareholder_payouts"] == 20
    assert row["payout_ratio_fcf"] == pytest.approx(0.5)


def test_ltm_balance_sheet_metrics_average_with_the_year_ago_quarter(ltm_connection):
    row = _ltm(ltm_connection, "ZZL")
    assert row["inventory_turnover"] == pytest.approx(368 / 45)
    assert row["days_inventory_outstanding"] == pytest.approx(45 / 368 * 365)
    tax_rate = 8 / (32 + 8)
    assert row["effective_tax_rate"] == pytest.approx(tax_rate)
    average_capital = ((100 + 300 - 30) + (90 + 260 - 20)) / 2
    assert row["roic"] == pytest.approx(40 * (1 - tax_rate) / average_capital)
    assert row["return_on_equity"] == pytest.approx(32 / ((290 + 250) / 2))


def test_ltm_is_null_rather_than_partial_when_a_quarter_is_missing(ltm_connection):
    row = _ltm(ltm_connection, "ZZG")
    assert row["net_sales"] == 460          # complete flows still report
    assert row["capital_expenditures"] is None
    assert row["free_cash_flow"] is None
    assert row["fcf_margin"] is None
    assert row["payout_ratio_fcf"] is None
