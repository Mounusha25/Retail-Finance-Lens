# Manual Reconciliation

This acceptance check ties one annual period and one recent quarter per company to the primary SEC filing used by the pipeline. Amounts are USD millions and were checked after the 2026-10-13 refresh.

## Annual revenue and cash flow

| Company | Period | Net sales | Membership / other | Total revenue | OCF | Capex | FCF | Source |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Walmart | 2026-01-31 | 706,413 | 6,750 | 713,163 | 41,565 | 26,642 | 14,923 | [10-K, accession 0000104169-26-000055](https://www.sec.gov/Archives/edgar/data/104169/000010416926000055/wmt-20260131.htm) |
| Target | 2026-01-31 | 102,717 | 2,063 | 104,780 | 6,562 | 3,727 | 2,835 | [10-K, accession 0000027419-26-000016](https://www.sec.gov/Archives/edgar/data/27419/000002741926000016/tgt-20260131.htm) |
| Costco | 2026-08-30 | 297,247 | 5,907 | 303,154 | 15,817 | 6,435 | 9,382 | [10-K, accession 0000909832-26-000093](https://www.sec.gov/Archives/edgar/data/909832/000090983226000093/cost-20260830.htm) |
| Kroger | 2026-01-31 | 147,642 | n/a (no separate line) | 147,642 | 7,311 | 3,855 | 3,456 | [10-K, accession 0001104659-26-037723](https://www.sec.gov/Archives/edgar/data/56873/000110465926037723/kr-20260131x10k.htm) |

Checks:

- Total revenue equals net sales plus membership/other revenue for all three companies.
- Free cash flow equals operating cash flow less positive capex for all three companies.
- Period dates, issuer fiscal labels, fiscal-day counts, accession numbers, and filing URLs are retained in the analytical views.

## Recent quarterly revenue

| Company | Period / issuer quarter | Net sales | Membership / other | Total revenue | Derivation | Source |
|---|---:|---:|---:|---:|---|---|
| Walmart | 2026-07-31 / FY2027 Q2 | 186,100 | 1,837 | 187,937 | Reported standalone quarter | [10-Q, accession 0000104169-26-000154](https://www.sec.gov/Archives/edgar/data/104169/000010416926000154/wmt-20260731.htm) |
| Target | 2026-08-01 / FY2026 Q2 | 25,947 | 592 | 26,539 | Derived from six months less Q1 where required | [10-Q, accession 0000027419-26-000042](https://www.sec.gov/Archives/edgar/data/27419/000002741926000042/tgt-20260801.htm) |
| Costco | 2026-08-30 / FY2026 Q4 | 93,873 | 1,850 | 95,723 | FY less Q3 YTD: net sales 297,247 − 203,374; membership 5,907 − 4,057 | [10-K, accession 0000909832-26-000093](https://www.sec.gov/Archives/edgar/data/909832/000090983226000093/cost-20260830.htm) |

The latest quality run recorded 133 passed checks, zero warnings, and zero errors across four companies. Kroger is reconciled line-by-line against the printed statements in its 10-K below. Walmart and Target do not tag total `Liabilities`, so the accounting-equation check for those issuers compares total assets with the reported `LiabilitiesAndStockholdersEquity` total (recorded as `basis: reported_liabilities_and_equity` in the check details) instead of deriving a liabilities plug. Target quarterly cash-conversion-cycle metrics remain null because a comparable quarterly receivables series is not disclosed; missing values are never treated as zero.

Idempotency is covered by the Postgres integration test (repeated schema/view installation); re-run `load` twice and compare row counts to confirm for a given dataset.

## Kroger line-by-line check

Kroger's fiscal year ended 2026-01-31 (issuer FY2025; 10-K accession 0001104659-26-037723). Each pipeline value
was compared with the figure printed on the statement in the filing document. Amounts are USD millions.

| Line | 10-K statement | Pipeline | Match |
|---|---:|---:|:---:|
| Sales | 147,642 | 147,642 | ✓ |
| Merchandise costs (excl. rent and D&A) | 113,240 | 113,240 | ✓ |
| Operating profit | 1,890 | 1,890 | ✓ |
| Net earnings attributable to Kroger | 1,016 | 1,016 | ✓ |
| Income tax expense | 176 | 176 | ✓ |
| Net cash from operating activities | 7,311 | 7,311 | ✓ |
| Payments for property and equipment | 3,855 | 3,855 | ✓ |
| Free cash flow (derived: 7,311 − 3,855) | — | 3,456 | ✓ |
| Inventory = FIFO inventory 9,445 − LIFO reserve 2,553 | 9,445 / (2,553) | 6,892 | ✓ |
| Prior-year inventory = 9,442 − 2,404 | 9,442 / (2,404) | 7,038 | ✓ |
| Cash and temporary cash investments | 3,334 | 3,334 | ✓ |
| Receivables | 2,192 | 2,192 | ✓ |
| Total current assets | 14,505 | 14,505 | ✓ |
| Total assets | 49,953 | 49,953 | ✓ |
| Accounts payable | 10,488 | 10,488 | ✓ |
| Total current liabilities | 18,108 | 18,108 | ✓ |
| Total shareowners' equity (Kroger) | 5,927 | 5,927 | ✓ |
| Total equity (incl. noncontrolling) | 5,936 | 5,936 | ✓ |

Total liabilities (44,017) plus total equity (5,936) equals total assets (49,953), which is the accounting-equation
check the pipeline runs.

Findings from the comparison:

- **Net inventory is the statement's own arithmetic.** Kroger's balance sheet prints FIFO inventory and the LIFO
  reserve as separate lines and no net line, so the derived figure is exactly what the statement implies.
- **Debt excludes finance leases.** The statement shows current debt of 1,802 and long-term debt of 15,764, both
  including finance leases. The pipeline's `total_debt` of 15,875 uses the debt-only tags (1,366 + 14,509) and
  excludes 1,691 of finance-lease liabilities. This is consistent with Walmart and Costco; Target's tag includes
  finance leases, so Target's debt is slightly overstated relative to the other three. ROIC is affected only
  through invested capital.
- **Cost of sales is not comparable to every peer.** Kroger's line excludes rent and depreciation and amortization.
