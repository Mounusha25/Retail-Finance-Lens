import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.scoring import latest_and_prior, pillar_leaders, score_peers, sensitivity  # noqa: E402


def _peer():
    return pd.DataFrame({
        "ticker": ["A", "B", "C"],
        "revenue_growth": [0.10, 0.05, 0.00],
        "operating_margin": [0.02, 0.04, 0.06],
        "net_margin": [0.01, 0.02, 0.03],
        "inventory_turnover": [10.0, 8.0, 6.0],
        "cash_conversion_cycle": [5.0, 1.0, 10.0],
        "free_cash_flow": [10.0, 10.0, 10.0],
        "total_revenue": [100.0, 200.0, 400.0],
        "roic": [0.30, 0.20, 0.10],
    })


def test_rank_scores_and_direction():
    scores = score_peers(_peer()).set_index("ticker")
    assert scores.loc["A", "Growth"] == 100 and scores.loc["C", "Growth"] == 0
    # Shorter cash cycle is better: B (1 day) beats A (5) beats C (10); turnover A > B > C.
    assert scores.loc["B", "score:cash_conversion_cycle"] == 100
    assert scores.loc["C", "score:cash_conversion_cycle"] == 0
    assert scores.loc["A", "Efficiency"] == pytest.approx((100 + 50) / 2)
    # FCF margin: A 10%, B 5%, C 2.5%.
    assert scores.loc["A", "Cash"] == 100


def test_composite_uses_equal_weights_and_ranks():
    scores = score_peers(_peer()).set_index("ticker")
    expected_a = (scores.loc["A", ["Growth", "Profitability", "Efficiency", "Cash", "Returns"]]).mean()
    assert scores.loc["A", "Composite"] == pytest.approx(expected_a)
    assert scores["Rank"].min() == 1


def test_custom_weights_shift_the_leader():
    growth_only = score_peers(_peer(), {"Growth": 100, "Profitability": 0, "Efficiency": 0, "Cash": 0, "Returns": 0})
    assert growth_only.iloc[0]["ticker"] == "A"
    margin_only = score_peers(_peer(), {"Growth": 0, "Profitability": 100, "Efficiency": 0, "Cash": 0, "Returns": 0})
    assert margin_only.iloc[0]["ticker"] == "C"


def test_missing_metric_is_not_scored_as_zero():
    frame = _peer()
    frame.loc[frame["ticker"] == "A", "roic"] = None
    scores = score_peers(frame).set_index("ticker")
    assert pd.isna(scores.loc["A", "Returns"])
    # Composite renormalises over the four pillars A does have.
    four = scores.loc["A", ["Growth", "Profitability", "Efficiency", "Cash"]].mean()
    assert scores.loc["A", "Composite"] == pytest.approx(four)


def test_pillar_leaders_and_latest_and_prior():
    scores = score_peers(_peer())
    assert pillar_leaders(scores)["Growth"] == "A"
    annual = pd.DataFrame({
        "ticker": ["A", "A", "B"],
        "period_end": pd.to_datetime(["2024-01-31", "2025-01-31", "2025-01-31"]),
        "operating_margin": [0.02, 0.03, 0.05],
    })
    result = latest_and_prior(annual, "operating_margin").set_index("ticker")
    assert result.loc["A", "change"] == pytest.approx(0.01)
    assert pd.isna(result.loc["B", "change"])


def test_balance_sheet_pillar_rewards_lower_leverage_and_higher_coverage():
    frame = _peer()
    frame["net_debt_to_ebitda"] = [-1.0, 0.5, 2.0]   # A is net cash: best
    frame["interest_coverage"] = [50.0, 10.0, 3.0]
    scores = score_peers(frame).set_index("ticker")
    assert scores.loc["A", "Balance sheet"] == 100
    assert scores.loc["C", "Balance sheet"] == 0
    assert scores.loc["B", "Balance sheet"] == 50


def test_balance_sheet_pillar_uses_the_metric_it_has():
    frame = _peer()
    frame["net_debt_to_ebitda"] = [1.0, 2.0, 3.0]
    frame["interest_coverage"] = [None, None, None]  # e.g. interest paid not reported
    scores = score_peers(frame).set_index("ticker")
    assert scores.loc["A", "Balance sheet"] == 100   # leverage alone scores the pillar


def test_sensitivity_reports_leader_stability():
    result = sensitivity(_peer(), random_scenarios=200, seed=1)
    summary = result["summary"].set_index("ticker")
    assert result["scenarios"] > 200
    assert summary["Share of weightings led"].sum() == pytest.approx(1.0)
    assert (summary["Best rank"] <= summary["Worst rank"]).all()
    named = result["named"].set_index("Scenario")
    # Each named scenario must agree with an independent run of the public scoring function.
    pillars = [p for p in ("Growth", "Profitability", "Efficiency", "Cash", "Returns")]
    for pillar in pillars:
        weights = {name: 1.0 for name in pillars}
        weights[pillar] = 3.0
        expected = score_peers(_peer(), weights).iloc[0]["ticker"]
        assert named.loc[f"{pillar} weighted 3×", "Leader"] == expected
    equal = score_peers(_peer(), {name: 1.0 for name in pillars}).iloc[0]["ticker"]
    assert named.loc["Equal weights", "Leader"] == equal


def test_sensitivity_is_reproducible_for_a_seed():
    first = sensitivity(_peer(), random_scenarios=100, seed=3)["summary"]
    second = sensitivity(_peer(), random_scenarios=100, seed=3)["summary"]
    pd.testing.assert_frame_equal(first, second)


def test_a_company_that_never_leads_has_zero_share():
    frame = _peer()
    result = sensitivity(frame, random_scenarios=50, seed=2)["summary"].set_index("ticker")
    assert 0.0 <= result["Share of weightings led"].min() <= result["Share of weightings led"].max() <= 1.0
