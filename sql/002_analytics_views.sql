CREATE SCHEMA IF NOT EXISTS analytics;

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
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'capital_expenditures') AS capital_expenditures
    FROM annual_periods p
    JOIN companies c ON c.id = p.company_id
    LEFT JOIN ranked r
      ON r.company_id = p.company_id
     AND r.period_end = p.period_end
     AND r.version_rank = 1
    GROUP BY c.id, c.ticker, c.name, p.period_end
), with_revenue AS (
    SELECT
        *,
        COALESCE(reported_total_revenue,
                 CASE WHEN net_sales IS NOT NULL AND membership_other_revenue IS NOT NULL
                      THEN net_sales + membership_other_revenue END) AS total_revenue,
        lag(net_sales) OVER (PARTITION BY company_id ORDER BY period_end) AS prior_net_sales,
        lag(inventory) OVER (PARTITION BY company_id ORDER BY period_end) AS prior_inventory,
        lag(accounts_receivable_net_current) OVER (PARTITION BY company_id ORDER BY period_end) AS prior_receivables,
        lag(accounts_payable_current) OVER (PARTITION BY company_id ORDER BY period_end) AS prior_accounts_payable
    FROM pivoted
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
    current_debt + long_term_debt_noncurrent AS total_debt
FROM with_revenue;

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
        max(r.normalized_value) FILTER (WHERE r.canonical_concept = 'capital_expenditures') AS capital_expenditures
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
    current_debt + long_term_debt_noncurrent AS total_debt
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
