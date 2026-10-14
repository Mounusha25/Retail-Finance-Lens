from __future__ import annotations

import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import case, delete, select, text
from sqlalchemy.orm import Session

from .models import Company, FinancialFact, ValidationResult


REQUIRED_CONCEPTS = {
    "net_sales",
    "total_revenue",
    "cost_of_sales",
    "operating_income",
    "net_income",
    "inventory",
    "current_assets",
    "accounts_payable_current",
    "current_liabilities",
    "total_assets",
    "total_liabilities",
    "total_equity",
    "operating_cash_flow",
    "capital_expenditures",
}


def accounting_tolerance(total: Decimal | None) -> Decimal:
    if total is None:
        return Decimal("5000000")
    return max(Decimal("5000000"), abs(total) * Decimal("0.0001"))


def _latest_annual_values(session: Session) -> dict[tuple[int, object], dict[str, Decimal]]:
    facts = session.scalars(
        select(FinancialFact)
        .where(FinancialFact.period_kind.in_(["annual", "instant"]))
        .order_by(
            FinancialFact.filed_at.desc(),
            case(
                (
                    FinancialFact.source_concept.like("inline:%")
                    | FinancialFact.source_concept.like("derived:inline:%"),
                    0,
                ),
                else_=1,
            ).asc(),
            FinancialFact.is_derived.asc(),
            FinancialFact.id.desc(),
        )
    ).all()
    seen: set[tuple[int, str, object]] = set()
    values: dict[tuple[int, object], dict[str, Decimal]] = defaultdict(dict)
    annual_ends = {
        (fact.company_id, fact.period_end)
        for fact in facts
        if fact.period_kind == "annual" and fact.canonical_concept == "net_sales"
    }
    retained_ends = {
        (company_id, period_end)
        for company_id in {company_id for company_id, _ in annual_ends}
        for period_end in sorted(
            [end for candidate_company, end in annual_ends if candidate_company == company_id],
            reverse=True,
        )[:6]
    }
    for fact in facts:
        key = (fact.company_id, fact.canonical_concept, fact.period_end)
        if key in seen or (fact.company_id, fact.period_end) not in retained_ends:
            continue
        seen.add(key)
        values[(fact.company_id, fact.period_end)][fact.canonical_concept] = Decimal(fact.normalized_value)
    return values


def run_validations(session: Session, run_id: uuid.UUID | None = None) -> dict[str, int]:
    if run_id:
        session.execute(delete(ValidationResult).where(ValidationResult.run_id == run_id))
    values_by_period = _latest_annual_values(session)
    counts = {"passed": 0, "warning": 0, "error": 0}
    for (company_id, period_end), values in values_by_period.items():
        missing = sorted(REQUIRED_CONCEPTS - values.keys())
        missing_status = "passed" if not missing else "warning"
        session.add(
            ValidationResult(
                run_id=run_id,
                company_id=company_id,
                period_end=period_end,
                check_name="required_annual_fields",
                severity="warning",
                status=missing_status,
                details={"missing": missing},
            )
        )
        counts[missing_status] += 1

        assets = values.get("total_assets")
        liabilities = values.get("total_liabilities")
        equity = values.get("total_equity")
        if None not in (assets, liabilities, equity):
            expected = liabilities + equity
            tolerance = accounting_tolerance(assets)
            status = "passed" if abs(assets - expected) <= tolerance else "error"
            session.add(
                ValidationResult(
                    run_id=run_id,
                    company_id=company_id,
                    period_end=period_end,
                    check_name="accounting_equation",
                    severity="error",
                    status=status,
                    observed_value=assets,
                    expected_value=expected,
                    tolerance=tolerance,
                    details={},
                )
            )
            counts[status] += 1

        net_sales = values.get("net_sales")
        membership = values.get("membership_other_revenue")
        total_revenue = values.get("total_revenue")
        if None not in (net_sales, membership, total_revenue):
            expected = net_sales + membership
            tolerance = accounting_tolerance(total_revenue)
            status = "passed" if abs(total_revenue - expected) <= tolerance else "error"
            session.add(
                ValidationResult(
                    run_id=run_id,
                    company_id=company_id,
                    period_end=period_end,
                    check_name="revenue_reconciliation",
                    severity="error",
                    status=status,
                    observed_value=total_revenue,
                    expected_value=expected,
                    tolerance=tolerance,
                    details={"identity": "total revenue = net sales + membership/other revenue"},
                )
            )
            counts[status] += 1

        cash_parts = [
            values.get("operating_cash_flow"),
            values.get("investing_cash_flow"),
            values.get("financing_cash_flow"),
        ]
        net_change = values.get("net_change_in_cash")
        if all(value is not None for value in cash_parts) and net_change is not None:
            expected = sum(cash_parts, Decimal("0")) + (values.get("fx_effect_on_cash") or Decimal("0"))
            tolerance = accounting_tolerance(net_change)
            status = "passed" if abs(net_change - expected) <= tolerance else "warning"
            session.add(
                ValidationResult(
                    run_id=run_id,
                    company_id=company_id,
                    period_end=period_end,
                    check_name="cash_flow_reconciliation",
                    severity="warning",
                    status=status,
                    observed_value=net_change,
                    expected_value=expected,
                    tolerance=tolerance,
                    details={"fx_missing_treated_as_zero": "fx_effect_on_cash" not in values},
                )
            )
            counts[status] += 1

    for company_id in session.scalars(select(Company.id)).all():
        annual_count = len(
            set(
                session.scalars(
                    select(FinancialFact.period_end).where(
                        FinancialFact.company_id == company_id,
                        FinancialFact.canonical_concept == "net_sales",
                        FinancialFact.period_kind == "annual",
                    )
                ).all()
            )
        )
        quarter_count = len(
            set(
                session.scalars(
                    select(FinancialFact.period_end).where(
                        FinancialFact.company_id == company_id,
                        FinancialFact.canonical_concept == "net_sales",
                        FinancialFact.period_kind == "quarterly",
                    )
                ).all()
            )
        )
        for check_name, observed, expected in (
            ("annual_period_coverage", annual_count, 6),
            ("quarterly_period_coverage", quarter_count, 12),
        ):
            status = "passed" if observed >= expected else "error"
            session.add(
                ValidationResult(
                    run_id=run_id,
                    company_id=company_id,
                    check_name=check_name,
                    severity="error",
                    status=status,
                    observed_value=Decimal(observed),
                    expected_value=Decimal(expected),
                    tolerance=Decimal("0"),
                    details={"requirement": f"at least {expected} comparable periods"},
                )
            )
            counts[status] += 1

    quarterly_rows = session.execute(
        text(
            """
            WITH ranked AS (
                SELECT q.*, row_number() OVER (PARTITION BY company_id ORDER BY period_end DESC) AS rn
                FROM analytics.v_quarterly_metrics q
            )
            SELECT company_id, period_end, net_sales, membership_other_revenue, total_revenue
            FROM ranked
            WHERE rn <= 12
            """
        )
    ).mappings()
    for row in quarterly_rows:
        if None in (row["net_sales"], row["membership_other_revenue"], row["total_revenue"]):
            continue
        observed = Decimal(row["total_revenue"])
        expected = Decimal(row["net_sales"]) + Decimal(row["membership_other_revenue"])
        tolerance = accounting_tolerance(observed)
        status = "passed" if abs(observed - expected) <= tolerance else "error"
        session.add(
            ValidationResult(
                run_id=run_id,
                company_id=row["company_id"],
                period_end=row["period_end"],
                check_name="quarterly_revenue_reconciliation",
                severity="error",
                status=status,
                observed_value=observed,
                expected_value=expected,
                tolerance=tolerance,
                details={"identity": "total revenue = net sales + membership/other revenue"},
            )
        )
        counts[status] += 1
    return counts
