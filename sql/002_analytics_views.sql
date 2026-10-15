CREATE SCHEMA IF NOT EXISTS analytics;

-- Views are dropped first because CREATE OR REPLACE VIEW cannot add or reorder columns.
DROP VIEW IF EXISTS analytics.v_ltm_metrics;
DROP VIEW IF EXISTS analytics.v_peer_comparison;
DROP VIEW IF EXISTS analytics.v_annual_metrics;
DROP VIEW IF EXISTS analytics.v_quarterly_metrics;
DROP VIEW IF EXISTS analytics.v_data_quality;

CREATE OR REPLACE VIEW analytics.v_annual_metrics AS
WITH ranked AS (
    SELECT
        f.*,
        row_number() OVER (
            PARTITION BY f.company_id, f.canonical_concept, f.period_end
            ORDER BY f.filed_at DESC,
                     CASE WHEN f.source_concept LIKE 'inline:%' OR f.source_concept LIKE 'derived:inline:%' THEN 0 ELSE 1 END,
                     f.is_derived ASC,
                     f.id DESC
        ) AS version_rank
    FROM financial_facts f
    WHERE f.period_kind IN ('annual', 'instant')
), annual_periods AS (
    SELECT DISTINCT company_id, period_end
    FROM ranked
    WHERE canonical_concept = 'net_sales'
      AND period_kind = 'annual'
      AND version_rank = 1
), pivoted AS (
    SELECT
        c.id AS company_id,
        c.ticker,
        c.name AS company_name,
        p.period_end,
        max(r.period_start) FILTER (WHERE r.canonical_concept = 'net_sales') AS period_start,
        max(r.issuer_fiscal_year) FILTER (WHERE r.canonical_concept = 'net_sales') AS issuer_fiscal_year,
        max(r.fiscal_days) FILTER (WHERE r.canonical_concept = 'net_sales') AS fiscal_days,
        bool_or(r.is_53_week) FILTER (WHERE r.canonical_concept = 'net_sales') AS is_53_week,
        max(r.accession_number) FILTER (WHERE r.canonical_concept = 'net_sales') AS accession_number,
        max(r.source_url) FILTER (WHERE r.canonical_concept = 'net_sales') AS source_url,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'net_sales') AS net_sales,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'membership_other_revenue') AS membership_other_revenue,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'total_revenue') AS reported_total_revenue,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'cost_of_sales') AS cost_of_sales,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'operating_income') AS operating_income,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'net_income') AS net_income,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'cash_and_cash_equivalents') AS cash_and_cash_equivalents,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'short_term_investments') AS short_term_investments,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'accounts_receivable_net_current') AS accounts_receivable_net_current,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'inventory') AS inventory,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'current_assets') AS current_assets,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'accounts_payable_current') AS accounts_payable_current,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'current_debt') AS current_debt,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'current_liabilities') AS current_liabilities,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'long_term_debt_noncurrent') AS long_term_debt_noncurrent,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'operating_cash_flow') AS operating_cash_flow,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'capital_expenditures') AS capital_expenditures,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'short_term_borrowings') AS short_term_borrowings,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'total_assets') AS total_assets,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'stockholders_equity') AS stockholders_equity,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'total_equity') AS total_equity,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'income_tax_expense') AS income_tax_expense,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'dividends_paid') AS dividends_paid,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'share_repurchases') AS share_repurchases,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'debt_issued') AS debt_issued,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'debt_repaid') AS debt_repaid
    FROM annual_periods p
    JOIN companies c ON c.id = p.company_id
    LEFT JOIN ranked r
      ON r.company_id = p.company_id
     AND r.period_end = p.period_end
     AND r.version_rank = 1
    GROUP BY c.id, c.ticker, c.name, p.period_end
), capital AS (
    SELECT
        *,
        current_debt + long_term_debt_noncurrent + COALESCE(short_term_borrowings, 0) AS total_debt,
        current_debt + long_term_debt_noncurrent + COALESCE(short_term_borrowings, 0)
          + total_equity - cash_and_cash_equivalents AS invested_capital
    FROM pivoted
), with_revenue AS (
    SELECT
        *,
        COALESCE(reported_total_revenue,
                 CASE WHEN net_sales IS NOT NULL AND membership_other_revenue IS NOT NULL
                      THEN net_sales + membership_other_revenue END) AS total_revenue,
        lag(net_sales) OVER (PARTITION BY company_id ORDER BY period_end) AS prior_net_sales,
        lag(inventory) OVER (PARTITION BY company_id ORDER BY period_end) AS prior_inventory,
        lag(accounts_receivable_net_current) OVER (PARTITION BY company_id ORDER BY period_end) AS prior_receivables,
        lag(accounts_payable_current) OVER (PARTITION BY company_id ORDER BY period_end) AS prior_accounts_payable,
        lag(invested_capital) OVER (PARTITION BY company_id ORDER BY period_end) AS prior_invested_capital,
        lag(total_assets) OVER (PARTITION BY company_id ORDER BY period_end) AS prior_total_assets,
        lag(stockholders_equity) OVER (PARTITION BY company_id ORDER BY period_end) AS prior_stockholders_equity
    FROM capital
), returns AS (
    SELECT
        *,
        income_tax_expense / NULLIF(net_income + income_tax_expense, 0) AS effective_tax_rate
    FROM with_revenue
)
SELECT
    *,
    net_sales / NULLIF(prior_net_sales, 0) - 1 AS revenue_growth,
    (net_sales - cost_of_sales) / NULLIF(net_sales, 0) AS gross_margin,
    operating_income / NULLIF(total_revenue, 0) AS operating_margin,
    net_income / NULLIF(total_revenue, 0) AS net_margin,
    operating_cash_flow / NULLIF(net_income, 0) AS ocf_to_net_income,
    CASE WHEN net_income < 0 THEN true ELSE false END AS ocf_ratio_caution,
    operating_cash_flow - capital_expenditures AS free_cash_flow,
    inventory / NULLIF(prior_inventory, 0) - 1 AS inventory_growth,
    (inventory / NULLIF(prior_inventory, 0) - 1) - (net_sales / NULLIF(prior_net_sales, 0) - 1) AS inventory_growth_gap,
    cost_of_sales / NULLIF((inventory + prior_inventory) / 2, 0) AS inventory_turnover,
    ((inventory + prior_inventory) / 2) / NULLIF(cost_of_sales, 0) * fiscal_days AS days_inventory_outstanding,
    ((accounts_receivable_net_current + prior_receivables) / 2) / NULLIF(net_sales, 0) * fiscal_days AS receivable_days,
    ((accounts_payable_current + prior_accounts_payable) / 2) / NULLIF(cost_of_sales, 0) * fiscal_days AS payable_days,
    (((accounts_receivable_net_current + prior_receivables) / 2) / NULLIF(net_sales, 0) * fiscal_days)
      + (((inventory + prior_inventory) / 2) / NULLIF(cost_of_sales, 0) * fiscal_days)
      - (((accounts_payable_current + prior_accounts_payable) / 2) / NULLIF(cost_of_sales, 0) * fiscal_days)
      AS cash_conversion_cycle,
    current_assets / NULLIF(current_liabilities, 0) AS current_ratio,
    (cash_and_cash_equivalents + short_term_investments + accounts_receivable_net_current)
      / NULLIF(current_liabilities, 0) AS quick_ratio,
    operating_income * (1 - effective_tax_rate) AS nopat,
    operating_income * (1 - effective_tax_rate)
      / NULLIF((invested_capital + prior_invested_capital) / 2, 0) AS roic,
    net_income / NULLIF((stockholders_equity + prior_stockholders_equity) / 2, 0) AS return_on_equity,
    total_revenue / NULLIF((total_assets + prior_total_assets) / 2, 0) AS asset_turnover,
    ((total_assets + prior_total_assets) / 2)
      / NULLIF((stockholders_equity + prior_stockholders_equity) / 2, 0) AS equity_multiplier,
    dividends_paid + share_repurchases AS shareholder_payouts,
    CASE WHEN operating_cash_flow - capital_expenditures > 0
         THEN (dividends_paid + share_repurchases) / (operating_cash_flow - capital_expenditures) END AS payout_ratio_fcf,
    capital_expenditures / NULLIF(operating_cash_flow, 0) AS capex_to_ocf,
    debt_issued - debt_repaid AS net_debt_issuance,
    operating_cash_flow - capital_expenditures - dividends_paid - share_repurchases AS fcf_after_payouts
FROM returns;

CREATE OR REPLACE VIEW analytics.v_quarterly_metrics AS
WITH ranked AS (
    SELECT
        f.*,
        row_number() OVER (
            PARTITION BY f.company_id, f.canonical_concept, f.period_end
            ORDER BY f.filed_at DESC,
                     CASE WHEN f.source_concept LIKE 'inline:%' OR f.source_concept LIKE 'derived:inline:%' THEN 0 ELSE 1 END,
                     f.is_derived ASC,
                     f.id DESC
        ) AS version_rank
    FROM financial_facts f
    WHERE f.period_kind IN ('quarterly', 'instant')
), quarter_periods AS (
    SELECT DISTINCT company_id, period_end
    FROM ranked
    WHERE canonical_concept = 'net_sales'
      AND period_kind = 'quarterly'
      AND version_rank = 1
), pivoted AS (
    SELECT
        c.id AS company_id,
        c.ticker,
        c.name AS company_name,
        p.period_end,
        max(r.period_start) FILTER (WHERE r.canonical_concept = 'net_sales') AS period_start,
        max(r.issuer_fiscal_year) FILTER (WHERE r.canonical_concept = 'net_sales') AS issuer_fiscal_year,
        max(r.issuer_fiscal_period) FILTER (WHERE r.canonical_concept = 'net_sales') AS issuer_fiscal_period,
        max(r.fiscal_days) FILTER (WHERE r.canonical_concept = 'net_sales') AS fiscal_days,
        max(r.accession_number) FILTER (WHERE r.canonical_concept = 'net_sales') AS accession_number,
        max(r.source_url) FILTER (WHERE r.canonical_concept = 'net_sales') AS source_url,
        bool_or(r.is_derived) FILTER (WHERE r.canonical_concept = 'net_sales') AS is_derived,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'net_sales') AS net_sales,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'membership_other_revenue') AS membership_other_revenue,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'total_revenue') AS reported_total_revenue,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'cost_of_sales') AS cost_of_sales,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'operating_income') AS operating_income,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'net_income') AS net_income,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'cash_and_cash_equivalents') AS cash_and_cash_equivalents,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'short_term_investments') AS short_term_investments,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'accounts_receivable_net_current') AS accounts_receivable_net_current,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'inventory') AS inventory,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'current_assets') AS current_assets,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'accounts_payable_current') AS accounts_payable_current,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'current_debt') AS current_debt,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'current_liabilities') AS current_liabilities,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'long_term_debt_noncurrent') AS long_term_debt_noncurrent,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'operating_cash_flow') AS operating_cash_flow,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'capital_expenditures') AS capital_expenditures,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'short_term_borrowings') AS short_term_borrowings,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'total_assets') AS total_assets,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'stockholders_equity') AS stockholders_equity,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'total_equity') AS total_equity,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'income_tax_expense') AS income_tax_expense,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'dividends_paid') AS dividends_paid,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'share_repurchases') AS share_repurchases,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'debt_issued') AS debt_issued,
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'debt_repaid') AS debt_repaid
    FROM quarter_periods p
    JOIN companies c ON c.id = p.company_id
    LEFT JOIN ranked r
      ON r.company_id = p.company_id
     AND r.period_end = p.period_end
     AND r.version_rank = 1
    GROUP BY c.id, c.ticker, c.name, p.period_end
), lagged AS (
    SELECT
        *,
        COALESCE(reported_total_revenue,
                 CASE WHEN net_sales IS NOT NULL AND membership_other_revenue IS NOT NULL
                      THEN net_sales + membership_other_revenue END) AS total_revenue,
        lag(net_sales, 4) OVER (PARTITION BY company_id ORDER BY period_end) AS prior_year_net_sales,
        lag(inventory) OVER (PARTITION BY company_id ORDER BY period_end) AS prior_inventory,
        lag(accounts_receivable_net_current) OVER (PARTITION BY company_id ORDER BY period_end) AS prior_receivables,
        lag(accounts_payable_current) OVER (PARTITION BY company_id ORDER BY period_end) AS prior_accounts_payable
    FROM pivoted
)
SELECT
    *,
    net_sales / NULLIF(prior_year_net_sales, 0) - 1 AS revenue_growth,
    (net_sales - cost_of_sales) / NULLIF(net_sales, 0) AS gross_margin,
    operating_income / NULLIF(total_revenue, 0) AS operating_margin,
    net_income / NULLIF(total_revenue, 0) AS net_margin,
    operating_cash_flow / NULLIF(net_income, 0) AS ocf_to_net_income,
    operating_cash_flow - capital_expenditures AS free_cash_flow,
    cost_of_sales / NULLIF((inventory + prior_inventory) / 2, 0) AS inventory_turnover,
    ((inventory + prior_inventory) / 2) / NULLIF(cost_of_sales, 0) * fiscal_days AS days_inventory_outstanding,
    ((accounts_receivable_net_current + prior_receivables) / 2) / NULLIF(net_sales, 0) * fiscal_days AS receivable_days,
    ((accounts_payable_current + prior_accounts_payable) / 2) / NULLIF(cost_of_sales, 0) * fiscal_days AS payable_days,
    (((accounts_receivable_net_current + prior_receivables) / 2) / NULLIF(net_sales, 0) * fiscal_days)
      + (((inventory + prior_inventory) / 2) / NULLIF(cost_of_sales, 0) * fiscal_days)
      - (((accounts_payable_current + prior_accounts_payable) / 2) / NULLIF(cost_of_sales, 0) * fiscal_days)
      AS cash_conversion_cycle,
    current_assets / NULLIF(current_liabilities, 0) AS current_ratio,
    (cash_and_cash_equivalents + short_term_investments + accounts_receivable_net_current)
      / NULLIF(current_liabilities, 0) AS quick_ratio,
    current_debt + long_term_debt_noncurrent + COALESCE(short_term_borrowings, 0) AS total_debt
FROM lagged;

CREATE OR REPLACE VIEW analytics.v_peer_comparison AS
SELECT annual.*
FROM analytics.v_annual_metrics annual
JOIN (
    SELECT company_id, max(period_end) AS period_end
    FROM analytics.v_annual_metrics
    GROUP BY company_id
) latest USING (company_id, period_end);

CREATE OR REPLACE VIEW analytics.v_data_quality AS
WITH latest_validation_run AS (
    SELECT run_id
    FROM validation_results
    WHERE run_id IS NOT NULL
    GROUP BY run_id
    ORDER BY max(created_at) DESC
    LIMIT 1
)
SELECT
    v.id,
    c.ticker,
    v.period_end,
    v.check_name,
    v.severity,
    v.status,
    v.observed_value,
    v.expected_value,
    v.tolerance,
    v.details,
    v.created_at
FROM validation_results v
LEFT JOIN companies c ON c.id = v.company_id
WHERE v.run_id = (SELECT run_id FROM latest_validation_run);

-- Trailing twelve months: the latest four standalone quarters per company. A flow is reported only when all
-- four quarters are present, and the window must span 52-53 weeks, so a gap yields NULL instead of a partial sum.
-- Balance-sheet items use the latest quarter end and the quarter end one year earlier for averages.
CREATE OR REPLACE VIEW analytics.v_ltm_metrics AS
WITH q AS (
    SELECT
        *,
        row_number() OVER (PARTITION BY company_id ORDER BY period_end DESC) AS rn
    FROM analytics.v_quarterly_metrics
), windowed AS (
    SELECT
        company_id,
        ticker,
        company_name,
        max(period_end) FILTER (WHERE rn = 1) AS period_end,
        max(issuer_fiscal_year) FILTER (WHERE rn = 1) AS issuer_fiscal_year,
        max(issuer_fiscal_period) FILTER (WHERE rn = 1) AS issuer_fiscal_period,
        max(accession_number) FILTER (WHERE rn = 1) AS accession_number,
        max(source_url) FILTER (WHERE rn = 1) AS source_url,
        count(*) FILTER (WHERE rn BETWEEN 1 AND 4) AS quarters_in_window,
        sum(fiscal_days) FILTER (WHERE rn BETWEEN 1 AND 4) AS fiscal_days,
        CASE WHEN count(net_sales) FILTER (WHERE rn BETWEEN 1 AND 4) = 4 THEN sum(net_sales) FILTER (WHERE rn BETWEEN 1 AND 4) END AS net_sales,
        CASE WHEN count(membership_other_revenue) FILTER (WHERE rn BETWEEN 1 AND 4) = 4 THEN sum(membership_other_revenue) FILTER (WHERE rn BETWEEN 1 AND 4) END AS membership_other_revenue,
        CASE WHEN count(total_revenue) FILTER (WHERE rn BETWEEN 1 AND 4) = 4 THEN sum(total_revenue) FILTER (WHERE rn BETWEEN 1 AND 4) END AS total_revenue,
        CASE WHEN count(cost_of_sales) FILTER (WHERE rn BETWEEN 1 AND 4) = 4 THEN sum(cost_of_sales) FILTER (WHERE rn BETWEEN 1 AND 4) END AS cost_of_sales,
        CASE WHEN count(operating_income) FILTER (WHERE rn BETWEEN 1 AND 4) = 4 THEN sum(operating_income) FILTER (WHERE rn BETWEEN 1 AND 4) END AS operating_income,
        CASE WHEN count(net_income) FILTER (WHERE rn BETWEEN 1 AND 4) = 4 THEN sum(net_income) FILTER (WHERE rn BETWEEN 1 AND 4) END AS net_income,
        CASE WHEN count(operating_cash_flow) FILTER (WHERE rn BETWEEN 1 AND 4) = 4 THEN sum(operating_cash_flow) FILTER (WHERE rn BETWEEN 1 AND 4) END AS operating_cash_flow,
        CASE WHEN count(capital_expenditures) FILTER (WHERE rn BETWEEN 1 AND 4) = 4 THEN sum(capital_expenditures) FILTER (WHERE rn BETWEEN 1 AND 4) END AS capital_expenditures,
        CASE WHEN count(income_tax_expense) FILTER (WHERE rn BETWEEN 1 AND 4) = 4 THEN sum(income_tax_expense) FILTER (WHERE rn BETWEEN 1 AND 4) END AS income_tax_expense,
        CASE WHEN count(dividends_paid) FILTER (WHERE rn BETWEEN 1 AND 4) = 4 THEN sum(dividends_paid) FILTER (WHERE rn BETWEEN 1 AND 4) END AS dividends_paid,
        CASE WHEN count(share_repurchases) FILTER (WHERE rn BETWEEN 1 AND 4) = 4 THEN sum(share_repurchases) FILTER (WHERE rn BETWEEN 1 AND 4) END AS share_repurchases,
        CASE WHEN count(debt_issued) FILTER (WHERE rn BETWEEN 1 AND 4) = 4 THEN sum(debt_issued) FILTER (WHERE rn BETWEEN 1 AND 4) END AS debt_issued,
        CASE WHEN count(debt_repaid) FILTER (WHERE rn BETWEEN 1 AND 4) = 4 THEN sum(debt_repaid) FILTER (WHERE rn BETWEEN 1 AND 4) END AS debt_repaid,
        CASE WHEN count(net_sales) FILTER (WHERE rn BETWEEN 5 AND 8) = 4 THEN sum(net_sales) FILTER (WHERE rn BETWEEN 5 AND 8) END AS prior_net_sales,
        CASE WHEN count(total_revenue) FILTER (WHERE rn BETWEEN 5 AND 8) = 4 THEN sum(total_revenue) FILTER (WHERE rn BETWEEN 5 AND 8) END AS prior_total_revenue,
        max(inventory) FILTER (WHERE rn = 1) AS inventory,
        max(inventory) FILTER (WHERE rn = 5) AS prior_inventory,
        max(accounts_receivable_net_current) FILTER (WHERE rn = 1) AS accounts_receivable_net_current,
        max(accounts_receivable_net_current) FILTER (WHERE rn = 5) AS prior_accounts_receivable_net_current,
        max(accounts_payable_current) FILTER (WHERE rn = 1) AS accounts_payable_current,
        max(accounts_payable_current) FILTER (WHERE rn = 5) AS prior_accounts_payable_current,
        max(cash_and_cash_equivalents) FILTER (WHERE rn = 1) AS cash_and_cash_equivalents,
        max(cash_and_cash_equivalents) FILTER (WHERE rn = 5) AS prior_cash_and_cash_equivalents,
        max(short_term_investments) FILTER (WHERE rn = 1) AS short_term_investments,
        max(short_term_investments) FILTER (WHERE rn = 5) AS prior_short_term_investments,
        max(current_assets) FILTER (WHERE rn = 1) AS current_assets,
        max(current_assets) FILTER (WHERE rn = 5) AS prior_current_assets,
        max(current_liabilities) FILTER (WHERE rn = 1) AS current_liabilities,
        max(current_liabilities) FILTER (WHERE rn = 5) AS prior_current_liabilities,
        max(total_assets) FILTER (WHERE rn = 1) AS total_assets,
        max(total_assets) FILTER (WHERE rn = 5) AS prior_total_assets,
        max(stockholders_equity) FILTER (WHERE rn = 1) AS stockholders_equity,
        max(stockholders_equity) FILTER (WHERE rn = 5) AS prior_stockholders_equity,
        max(total_equity) FILTER (WHERE rn = 1) AS total_equity,
        max(total_equity) FILTER (WHERE rn = 5) AS prior_total_equity,
        max(total_debt) FILTER (WHERE rn = 1) AS total_debt,
        max(total_debt) FILTER (WHERE rn = 5) AS prior_total_debt
    FROM q
    GROUP BY company_id, ticker, company_name
), clean AS (
    SELECT
        *,
        quarters_in_window = 4 AND fiscal_days BETWEEN 357 AND 378 AS is_complete
    FROM windowed
), with_flows AS (
    SELECT
        *,
        income_tax_expense / NULLIF(net_income + income_tax_expense, 0) AS effective_tax_rate,
        total_debt + total_equity - cash_and_cash_equivalents AS invested_capital,
        prior_total_debt + prior_total_equity - prior_cash_and_cash_equivalents AS prior_invested_capital
    FROM clean
)
SELECT
    *,
    net_sales / NULLIF(prior_net_sales, 0) - 1 AS revenue_growth,
    (net_sales - cost_of_sales) / NULLIF(net_sales, 0) AS gross_margin,
    operating_income / NULLIF(total_revenue, 0) AS operating_margin,
    net_income / NULLIF(total_revenue, 0) AS net_margin,
    operating_cash_flow / NULLIF(net_income, 0) AS ocf_to_net_income,
    operating_cash_flow - capital_expenditures AS free_cash_flow,
    (operating_cash_flow - capital_expenditures) / NULLIF(total_revenue, 0) AS fcf_margin,
    cost_of_sales / NULLIF((inventory + prior_inventory) / 2, 0) AS inventory_turnover,
    ((inventory + prior_inventory) / 2) / NULLIF(cost_of_sales, 0) * fiscal_days AS days_inventory_outstanding,
    ((accounts_receivable_net_current + prior_accounts_receivable_net_current) / 2) / NULLIF(net_sales, 0) * fiscal_days AS receivable_days,
    ((accounts_payable_current + prior_accounts_payable_current) / 2) / NULLIF(cost_of_sales, 0) * fiscal_days AS payable_days,
    (((accounts_receivable_net_current + prior_accounts_receivable_net_current) / 2) / NULLIF(net_sales, 0) * fiscal_days)
      + (((inventory + prior_inventory) / 2) / NULLIF(cost_of_sales, 0) * fiscal_days)
      - (((accounts_payable_current + prior_accounts_payable_current) / 2) / NULLIF(cost_of_sales, 0) * fiscal_days)
      AS cash_conversion_cycle,
    current_assets / NULLIF(current_liabilities, 0) AS current_ratio,
    (cash_and_cash_equivalents + short_term_investments + accounts_receivable_net_current)
      / NULLIF(current_liabilities, 0) AS quick_ratio,
    operating_income * (1 - effective_tax_rate) AS nopat,
    operating_income * (1 - effective_tax_rate)
      / NULLIF((invested_capital + prior_invested_capital) / 2, 0) AS roic,
    net_income / NULLIF((stockholders_equity + prior_stockholders_equity) / 2, 0) AS return_on_equity,
    total_revenue / NULLIF((total_assets + prior_total_assets) / 2, 0) AS asset_turnover,
    ((total_assets + prior_total_assets) / 2)
      / NULLIF((stockholders_equity + prior_stockholders_equity) / 2, 0) AS equity_multiplier,
    dividends_paid + share_repurchases AS shareholder_payouts,
    CASE WHEN operating_cash_flow - capital_expenditures > 0
         THEN (dividends_paid + share_repurchases) / (operating_cash_flow - capital_expenditures) END AS payout_ratio_fcf,
    capital_expenditures / NULLIF(operating_cash_flow, 0) AS capex_to_ocf,
    debt_issued - debt_repaid AS net_debt_issuance,
    operating_cash_flow - capital_expenditures - dividends_paid - share_repurchases AS fcf_after_payouts
FROM with_flows;

-- Recreating views drops their grants. Re-grant read access to the dashboard role when it exists
-- (managed hosts such as Neon create it separately), so a refresh never silently breaks the app.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dashboard_reader') THEN
        GRANT USAGE ON SCHEMA analytics TO dashboard_reader;
        GRANT SELECT ON analytics.v_annual_metrics, analytics.v_quarterly_metrics,
                        analytics.v_peer_comparison, analytics.v_data_quality, analytics.v_ltm_metrics
                        TO dashboard_reader;
    END IF;
END
$$;
