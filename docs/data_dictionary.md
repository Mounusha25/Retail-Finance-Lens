# Data Dictionary

## Canonical facts

| Group | Concepts |
|---|---|
| Income statement | `net_sales`, `membership_other_revenue`, `total_revenue`, `cost_of_sales`, `operating_income`, `net_income`, `income_tax_expense` |
| Balance sheet | `cash_and_cash_equivalents`, `short_term_investments`, `accounts_receivable_net_current`, `inventory`, `current_assets`, `accounts_payable_current`, `current_debt`, `current_liabilities`, `long_term_debt_noncurrent`, `total_assets`, `total_liabilities`, `total_liabilities_and_equity`, `total_equity`, `stockholders_equity`, `short_term_borrowings`, `fifo_inventory`, `lifo_reserve` |
| Cash flow | `operating_cash_flow`, `capital_expenditures`, `investing_cash_flow`, `financing_cash_flow`, `fx_effect_on_cash`, `net_change_in_cash` |

Every fact includes the accession number, taxonomy and source concept, raw and normalized values, unit, decimals, period boundaries, actual period length, 52/53-week flag, issuer fiscal labels, form, filed date, dimensions, source URL, and derivation status.

`net_sales` is the comparable merchandising measure. `membership_other_revenue` contains Costco membership fees, Target advertising/credit-card/other revenue, and Walmart other revenue. `total_revenue` is the audited consolidated total. Dimensional component rules live in `config/inline_concepts.yml` and retain their member names in lineage.

## Metric definitions

| Metric | Definition |
|---|---|
| Revenue growth | Current net sales ÷ prior comparable net sales − 1 |
| Gross margin | (Net sales − cost of sales) ÷ net sales |
| Operating margin | Operating income ÷ total revenue |
| Net margin | Net income ÷ total revenue |
| Cash conversion | Operating cash flow ÷ net income |
| Free cash flow | Operating cash flow − capital expenditures |
| Inventory turnover | Cost of sales ÷ average inventory |
| DIO | Average inventory ÷ cost of sales × actual fiscal days |
| Receivable days | Average receivables ÷ net sales × actual fiscal days |
| Payable days | Average accounts payable ÷ cost of sales × actual fiscal days |
| Cash conversion cycle | Receivable days + DIO − payable days |
| Current ratio | Current assets ÷ current liabilities |
| Quick ratio | (Cash + short-term investments + receivables) ÷ current liabilities |
| Total debt | Current debt + noncurrent long-term debt + short-term borrowings (when reported) |
| Invested capital | Total debt + total equity − cash and cash equivalents |
| Effective tax rate | Income tax expense ÷ (net income + income tax expense); an approximation, because pre-tax income is not consistently tagged |
| NOPAT | Operating income × (1 − effective tax rate) |
| ROIC | NOPAT ÷ average invested capital |
| Return on equity | Net income attributable to the parent ÷ average parent stockholders' equity |
| Asset turnover | Total revenue ÷ average total assets |
| Equity multiplier | Average total assets ÷ average parent stockholders' equity |

| Shareholder payouts | Dividends paid + share repurchases |
| Payout / FCF | Shareholder payouts ÷ free cash flow; null when free cash flow is not positive |
| Capex / OCF | Capital expenditures ÷ operating cash flow |
| Net debt issuance | Long-term debt issued − long-term debt repaid (excludes short-term borrowing and lease principal) |
| FCF after payouts | Operating cash flow − capex − dividends − buybacks |

| EBITDA | Operating income + depreciation and amortization (cash-flow statement line) |
| Net debt | Total debt − cash and cash equivalents (short-term investments are not netted) |
| Net debt / EBITDA | Net debt ÷ EBITDA; null when EBITDA is not positive; negative means net cash |
| Interest coverage | Operating income ÷ cash interest paid (gross `InterestPaid` where tagged, otherwise `InterestPaidNet`) |
| Lease-adjusted debt | Total debt + operating lease liability |
| Implied lease interest | Average operating lease liability × the weighted-average operating-lease discount rate the company discloses |
| Lease-adjusted ROIC | (Operating income + implied lease interest) × (1 − tax rate) ÷ average (invested capital + operating lease liability) |

| Restructuring & impairment charges | One tagged line per period (restructuring-and-impairment total, else asset impairment, else goodwill impairment); never summed across concepts |
| Adjusted operating income | Operating income + tagged restructuring and impairment charges; unadjusted when none are tagged (`has_tagged_charges` is false) |
| Adjusted operating margin | Adjusted operating income ÷ total revenue |

On the trailing-twelve-month basis the charge is the sum of the quarters that report one (such charges are sparse by
nature), so an untagged quarter contributes nothing and is not an error.

| Incremental ROIC (1 yr / 3 yr) | Change in NOPAT ÷ change in year-end invested capital over one / three fiscal years; reported only when capital grew by at least 2% / 5% |
| Incremental operating margin | Change in operating income ÷ change in total revenue; reported only when revenue grew by at least 1% |
| Operating leverage | % change in operating income ÷ % change in total revenue; reported only when revenue moved by at least 1% and prior operating income was positive |
| Working-capital cash effect | −Δinventory − Δreceivables + Δpayables, from balance-sheet changes (positive releases cash) |
| Other operating cash items | Operating cash flow − net income − D&A − working-capital effect − tagged impairment and restructuring charges (deferred taxes, stock compensation and other) |
| Accruals ratio | (Net income − operating cash flow) ÷ average total assets; negative means cash flow exceeds earnings |
| FCF conversion | Free cash flow ÷ net income; reported only when net income is positive |
| Capex / D&A, Capex / revenue | Capital expenditures relative to depreciation and amortization, and to revenue |
| PP&E turnover | Total revenue ÷ average net PP&E (Target and Kroger use the combined PP&E and finance-lease asset tag) |
| Net reinvestment, reinvestment rate | Capex − D&A − working-capital cash effect; divided by NOPAT when NOPAT is positive |

The ROE change attribution on the dashboard uses the logarithmic-mean Divisia decomposition of net margin × asset turnover
× equity multiplier, so the three contributions sum exactly to the year's change in ROE.

DuPont identity: net margin × asset turnover × equity multiplier = return on equity. Invested capital excludes operating-lease liabilities; Target's debt tag includes finance leases.

Missing inputs produce a null metric. The pipeline does not infer an undisclosed component as zero.

Standalone Q2 and Q3 flows are obtained from cumulative disclosures when a direct quarter is unavailable. Q4 flows are annual values less the first nine months. Instant balance-sheet facts are never differenced.

## Issuer-specific mapping notes

| Issuer | Note |
|---|---|
| Kroger (KR) | No separate membership revenue: reported sales are both `net_sales` and `total_revenue`. Cost of sales is tagged `CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization`, which excludes depreciation and rent-type items, so gross margin is not strictly comparable with peers. Net inventory is derived as `fifo_inventory` − `lifo_reserve` at the same balance-sheet date (flagged `is_derived`). Accounts payable falls back to `AccountsPayableTradeCurrent` before FY2023. Capex uses `PaymentsToAcquireProductiveAssets`. Debt uses the debt-only tags and therefore excludes finance-lease liabilities (Target's debt tag includes them). The first fiscal quarter is 16 weeks; the others are 12 weeks. |

## Trailing twelve months (`analytics.v_ltm_metrics`)

One row per company covering the latest four standalone quarters, so companies with different fiscal year-ends are
measured over the same twelve months.

- A flow (sales, cost of sales, operating income, cash flows, payouts) is the sum of four quarters and is reported
  only when all four are present; otherwise it is null, never a partial sum.
- `is_complete` is true when four quarters span 357-378 fiscal days.
- Growth compares the window with the four quarters before it.
- Balance-sheet items use the latest quarter end, and averages use the quarter end one year earlier.
- Ratios (margins, turnover, days, ROIC, ROE) use the same formulas as the annual view on these inputs.

## Forecast and valuation (illustrative)

The Valuation page and report finding 11 use a driver-based ten-year discounted-cash-flow model
(`app/valuation.py`). It is a scenario analysis, not a price target: the application holds no market prices or share counts.

| Driver | Default |
|---|---|
| Starting revenue | Trailing-twelve-month total revenue |
| Year-1 growth | Average of trailing-twelve-month growth and three-year revenue CAGR, capped at 12%, fading linearly to terminal growth by year 10 |
| Operating margin | Trailing-twelve-month operating margin before tagged restructuring and impairment charges, held flat |
| Tax rate | Trailing-twelve-month effective rate, limited to 18-30% (24% if unreported) |
| Depreciation and capex | D&A at its trailing share of revenue; capex at its three-year average share of revenue |
| Working capital | Latest fiscal year (inventory + receivables − payables) ÷ revenue, applied to revenue growth |
| Cost of capital | 7.5% (a judgement; adjustable) |
| Terminal growth | 2.5% (adjustable) |
| Return on new capital in perpetuity | Halfway between cost of capital and the company's ROIC, between WACC and 2× WACC |

Terminal value uses the value-driver formula NOPAT(T+1) × (1 − g ÷ RONIC) ÷ (WACC − g). Scenarios: **bear** lowers year-1
growth by 2 points and margin by 15%; **bull** raises growth by 1.5 points and margin by 10%. Equity value is enterprise
value less net debt (debt − cash; operating lease expense is already inside operating profit). The reverse DCF solves for
the near-term growth that reproduces a market value you enter.
