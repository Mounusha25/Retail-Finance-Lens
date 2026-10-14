# Data Dictionary

## Canonical facts

| Group | Concepts |
|---|---|
| Income statement | `net_sales`, `membership_other_revenue`, `total_revenue`, `cost_of_sales`, `operating_income`, `net_income` |
| Balance sheet | `cash_and_cash_equivalents`, `short_term_investments`, `accounts_receivable_net_current`, `inventory`, `current_assets`, `accounts_payable_current`, `current_debt`, `current_liabilities`, `long_term_debt_noncurrent`, `total_assets`, `total_liabilities`, `total_equity` |
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
| Total debt | Current debt + noncurrent long-term debt |

Missing inputs produce a null metric. The pipeline does not infer an undisclosed component as zero.

Standalone Q2 and Q3 flows are obtained from cumulative disclosures when a direct quarter is unavailable. Q4 flows are annual values less the first nine months. Instant balance-sheet facts are never differenced.
