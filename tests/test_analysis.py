import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis import cash_flow_steps, dupont_bridge, dupont_bridge_series  # noqa: E402


def _row(margin, turnover, leverage):
    return {"net_margin": margin, "asset_turnover": turnover, "equity_multiplier": leverage,
            "return_on_equity": margin * turnover * leverage}


def test_bridge_contributions_sum_exactly_to_the_change_in_roe():
    prior, current = _row(0.03, 2.5, 3.0), _row(0.04, 2.2, 3.6)
    bridge = dupont_bridge(prior, current)
    assert bridge["net_margin"] + bridge["asset_turnover"] + bridge["equity_multiplier"] == pytest.approx(bridge["change"])
    assert bridge["change"] == pytest.approx(0.04 * 2.2 * 3.6 - 0.03 * 2.5 * 3.0)


def test_bridge_signs_follow_each_terms_direction():
    bridge = dupont_bridge(_row(0.03, 2.5, 3.0), _row(0.04, 2.2, 3.6))
    assert bridge["net_margin"] > 0       # margin rose
    assert bridge["asset_turnover"] < 0   # turnover fell
    assert bridge["equity_multiplier"] > 0  # leverage rose


def test_bridge_handles_no_change_and_invalid_inputs():
    flat = dupont_bridge(_row(0.03, 2.0, 3.0), _row(0.03, 2.0, 3.0))
    assert flat["net_margin"] == pytest.approx(0) and flat["change"] == pytest.approx(0)
    assert dupont_bridge(_row(-0.01, 2.0, 3.0), _row(0.03, 2.0, 3.0)) is None   # negative margin: log undefined
    assert dupont_bridge({"net_margin": None}, _row(0.03, 2.0, 3.0)) is None


def test_series_has_one_row_per_year_after_the_first():
    frame = pd.DataFrame([
        {"period_end": "2023-01-31", **_row(0.03, 2.5, 3.0)},
        {"period_end": "2024-01-31", **_row(0.035, 2.4, 3.1)},
        {"period_end": "2025-01-31", **_row(0.04, 2.3, 3.4)},
    ])
    series = dupont_bridge_series(frame)
    assert len(series) == 2
    parts = series[["Net margin", "Asset turnover", "Leverage"]].sum(axis=1)
    assert parts.tolist() == pytest.approx(series["Change in ROE"].tolist())


def test_cash_flow_steps_reconcile_to_operating_cash_flow():
    row = pd.Series({
        "net_income": 40.0, "depreciation_amortization": 20.0, "working_capital_cash_effect": -10.0,
        "ocf_other_items": 28.0, "operating_cash_flow": 90.0, "restructuring_impairment_charges": 12.0,
    })
    steps = cash_flow_steps(row)
    flows = [value for _, value, kind in steps if kind != "total"]
    assert sum(flows) == pytest.approx(steps[-1][1])
    assert cash_flow_steps(row.drop("ocf_other_items")) is None
