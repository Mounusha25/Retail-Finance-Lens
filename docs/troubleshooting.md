# Troubleshooting

- **SEC rejects the request:** confirm `SEC_USER_AGENT` contains a descriptive project name and a monitored email. Do not raise the configured rate above 10 requests per second.
- **No dashboard rows:** run `financial-analysis refresh --companies all`; then inspect `analytics.v_data_quality` for missing concepts.
- **A metric is null:** open the methodology page. Null is intentional when an input is not reported or has not been mapped.
- **Duplicate-looking source facts:** facts from separate filings are retained deliberately. Analytical views rank them by filing date and accession.
- **Quarterly values look cumulative:** inspect `period_kind`. Only 60–120 day duration facts enter the quarterly view; Q4 values explicitly show `is_derived=true`.
- **Neon connection errors:** use the pooled connection for Streamlit, enable TLS in the connection string, and keep migrations on the owner connection.
- **Fiscal-year labels differ:** comparisons align on the calendar year of period end while preserving the issuer's own fiscal-year label.
