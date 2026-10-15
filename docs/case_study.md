# Case study: Which U.S. retailer converts growth into returns?

*Walmart, Target, Costco and Kroger, from SEC filings. Live dashboard: <https://retailfinance-analytics.streamlit.app/>*

## The question
Four large retailers report similar-looking profit margins, between 1% and 6%. Which of them turns growth and invested
capital into durable returns, which are returning more cash than they generate, and what would the fundamentals support
as a valuation?

## Approach
- **Source:** audited facts and filing documents from the SEC (10-K and 10-Q), five fiscal years plus the latest twelve
  quarters. Every figure on the dashboard links to its filing.
- **Comparability first:** fiscal years end in January (Walmart, Target, Kroger) and August (Costco), and Kroger's first
  quarter is 16 weeks. Peers are compared on an aligned **trailing-twelve-month** basis, with 53-week years flagged.
- **One metric layer:** every ratio is defined once, in SQL, and tested against hand-computed values. The dashboard
  reads those views and contains no financial formulas.
- **Reconciled:** Kroger was checked line by line against its 10-K (18 figures, all matching); the other issuers were
  reconciled on revenue and cash flow.
- **Honest nulls:** a missing input yields a missing metric, never a zero. Ratios built on tiny changes are suppressed
  rather than shown as noise.

## What the analysis found

**1. Costco is the only company whose advantage is widening.** Its return on invested capital is 41%, and the
three-year incremental return on new capital is 71%, so each new dollar earns more than the base. Extra revenue also
adds profit at 4.7 cents per dollar against a 3.9% average margin. It holds $14.0B of net cash and spends 2.4× its
depreciation on capex, so it is investing for growth from a position of strength.

**2. Walmart's latest year was dilutive.** It added about $13B of invested capital (from $127B to $140B) and after-tax
operating profit rose only $0.15B, an incremental return near 1% against a 17% average. Net reinvestment is 52% of
after-tax operating profit, and shareholder payouts of $15.6B slightly exceeded free cash flow of $14.9B. The three-year
incremental return (34%) is healthy, which makes the latest year the point to watch, not a trend.

**3. Target's recovery is real but flattered.** Its three-year incremental return of 43% sits well above its 15%
average, but most of that is recovery from a depressed FY2022 starting point: the latest single year is negative.
Over five years it paid out 141% of free cash flow and spent $6.0B more than its operating cash flow on capex and
payouts, so it has been funding returns from cash and borrowing.

**4. Kroger's weak earnings are mostly a one-time charge, but its balance sheet is the thinner one.** Reported operating
margin was 1.3%; before $2.7B of tagged impairment and restructuring charges it was 3.1%. Its free-cash-flow
conversion of 340% is not unusually strong cash generation: $6.0B of the gap between net income and operating cash
flow is depreciation ($3.3B) and impairments ($2.7B). After a large buyback programme its equity multiplier is 7.2×
(peers 2.6× to 3.8×), net debt is 2.4× EBITDA and interest coverage is 2.3×.

**5. The ranking is robust where it matters.** Costco leads in 93% of 513 alternative weightings of the six scoring
pillars, and it leads every named scenario. Target takes the lead only when profitability is weighted heavily.

## What the fundamentals support (illustrative)
A ten-year driver-based DCF, using each company's own trailing growth, margin, capex and working capital, with a 7.5%
cost of capital and 2.5% terminal growth, gives base-case enterprise values of **12.5× EBITDA for Costco, 9.9× Kroger,
8.8× Walmart and 7.7× Target**, with bear-to-bull spreads of roughly 3 to 5 turns of EBITDA. Terminal value is 57% to 71% of each
result. These are scenario outputs under stated assumptions, not price targets: the analysis holds no market prices.
A reverse-DCF tool shows how much growth a given market value would require.

## Choices worth defending
- **Aligned trailing twelve months** rather than latest fiscal years, because a five-month gap between Costco and the
  rest changed the comparison.
- **Rank-based scoring** so one outlier (Costco's 113× interest coverage) cannot dominate a pillar, plus a sensitivity
  panel so the ranking is never presented as more certain than it is.
- **LIFO inventory:** Kroger reports FIFO inventory and a LIFO reserve separately, so net inventory is derived as the
  statement's own arithmetic and flagged as derived.
- **Lease adjustment** uses each company's own disclosed discount rate, not an assumed one. It lowers every ROIC; it
  does not change who leads.
- **Incremental returns** are shown only when invested capital grew enough for the ratio to be meaningful.

## Limitations
- Four companies in one sector; scores are relative to this set, not to the market.
- No market prices, so no market-based valuation; the DCF is conditional on assumptions you can change.
- Adjusted margins capture only charges the issuers tag as a single restructuring or impairment line. Untagged items,
  such as litigation settlements, remain in reported operating income.
- Kroger's cost of sales excludes depreciation and rent-type items, so its gross margin is not strictly comparable.
- Working-capital movements are inferred from balance-sheet changes, not taken from the cash-flow statement.

## Reproduce it
`docker compose up -d db`, `docker compose --profile pipeline run --rm pipeline`, `docker compose up -d dashboard`; or
see the README. Definitions are in `docs/data_dictionary.md` and the reconciliation in `docs/manual_reconciliation.md`.
