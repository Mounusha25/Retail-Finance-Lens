# Deployment

## Local Docker Compose

1. Copy `.env.example` to `.env` and replace `SEC_USER_AGENT` with a real project name and contact email.
2. Run `docker compose up -d db`.
3. Run `docker compose --profile pipeline run --rm pipeline`.
4. Run `docker compose up -d dashboard` and open <http://localhost:8501>.

## Neon and Streamlit Community Cloud

1. Create a Neon PostgreSQL project and apply `alembic upgrade head` with the owner connection.
2. Create a write user for GitHub Actions and a read-only user limited to the `analytics` schema for Streamlit.
3. Add `DATABASE_WRITE_URL` and `SEC_USER_AGENT` as GitHub Actions secrets.
4. Deploy `app/streamlit_app.py` from the repository in Streamlit Community Cloud.
5. Add the pooled read-only Neon URL as the Streamlit `DATABASE_URL` secret.
6. Trigger the refresh workflow manually once. It subsequently runs Mondays at 13:00 UTC, which is 06:00 in Arizona.

Never commit `.env`, `.streamlit/secrets.toml`, or connection strings.

## Read-only role example

Run as a Neon database owner after replacing the placeholder password:

```sql
CREATE ROLE dashboard_reader LOGIN PASSWORD '<generated-password>';
GRANT CONNECT ON DATABASE neondb TO dashboard_reader;
GRANT USAGE ON SCHEMA analytics TO dashboard_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO dashboard_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT SELECT ON TABLES TO dashboard_reader;
```
