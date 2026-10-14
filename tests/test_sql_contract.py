from financial_analysis.config import PROJECT_ROOT


def test_dashboard_metrics_are_defined_in_sql_views():
    sql = (PROJECT_ROOT / "sql" / "002_analytics_views.sql").read_text()
    required = [
        "revenue_growth",
        "gross_margin",
        "operating_margin",
        "free_cash_flow",
        "inventory_turnover",
        "days_inventory_outstanding",
        "cash_conversion_cycle",
        "current_ratio",
        "quick_ratio",
        "total_debt",
    ]
    for metric in required:
        assert metric in sql
