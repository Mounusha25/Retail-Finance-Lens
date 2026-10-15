import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.valuation import (  # noqa: E402
    Assumptions, apply_scenario, base_assumptions, dcf, default_ronic, fade, implied_growth_shift, inputs_from_history,
    project, sensitivity_grid,
)


def flat(**overrides) -> Assumptions:
    values = dict(
        start_revenue=100.0, growth_path=(0.0,) * 5, operating_margin_path=(0.10,) * 5, tax_rate=0.25,
        da_pct_revenue=0.04, capex_pct_revenue=0.04, nwc_pct_revenue=0.0, wacc=0.10, terminal_growth=0.0,
        terminal_ronic=0.10,
    )
    values.update(overrides)
    return Assumptions(**values)


def test_flat_business_is_a_perpetuity_of_nopat():
    # NOPAT = 100 x 10% x 75% = 7.5 every year; with g = 0 the value is NOPAT / WACC = 75.
    result = dcf(flat())
    assert result["enterprise_value"] == pytest.approx(75.0)
    assert result["pv_explicit"] + result["pv_terminal"] == pytest.approx(75.0)


def test_equity_value_subtracts_net_debt_and_adds_net_cash():
    assert dcf(flat(), net_debt=20.0)["equity_value"] == pytest.approx(55.0)
    assert dcf(flat(), net_debt=-10.0)["equity_value"] == pytest.approx(85.0)


def test_projection_cash_flow_identity():
    a = flat(growth_path=(0.10, 0.08, 0.06, 0.04, 0.02), nwc_pct_revenue=0.05)
    table = project(a)
    expected = table["nopat"] + table["da"] - table["capex"] - table["delta_nwc"]
    assert table["fcf"].tolist() == pytest.approx(expected.tolist())
    assert table.loc[0, "revenue"] == pytest.approx(110.0)
    assert table.loc[0, "delta_nwc"] == pytest.approx(0.05 * 10.0)


def test_negative_working_capital_releases_cash_as_the_business_grows():
    table = project(flat(growth_path=(0.10,) * 5, nwc_pct_revenue=-0.05))
    assert (table["delta_nwc"] < 0).all()
    assert table.loc[0, "fcf"] > project(flat(growth_path=(0.10,) * 5))["fcf"][0]


def test_growth_creates_no_value_when_new_capital_only_earns_wacc():
    with_growth = dcf(flat(terminal_growth=0.03, terminal_ronic=0.10, growth_path=(0.03,) * 5))
    no_growth = dcf(flat(terminal_growth=0.0, terminal_ronic=0.10, growth_path=(0.03,) * 5))
    # Terminal value is identical in NOPAT/WACC terms only if RONIC == WACC and margins are unchanged.
    assert with_growth["terminal_value"] == pytest.approx(
        100 * 1.03**5 * 1.03 * 0.10 * 0.75 * (1 - 0.03 / 0.10) / (0.10 - 0.03)
    )
    assert with_growth["terminal_value"] / no_growth["terminal_value"] == pytest.approx(1.03, rel=1e-6)


def test_higher_returns_on_new_capital_raise_value():
    low = dcf(flat(terminal_growth=0.03, terminal_ronic=0.10))["enterprise_value"]
    high = dcf(flat(terminal_growth=0.03, terminal_ronic=0.20))["enterprise_value"]
    assert high > low


def test_invalid_discount_rate_is_rejected():
    with pytest.raises(ValueError):
        dcf(flat(wacc=0.03, terminal_growth=0.04))


def test_scenarios_order_value_bear_below_base_below_bull():
    inputs = {
        "total_revenue": 100.0, "revenue_growth": 0.05, "cagr_3y": 0.05, "adjusted_operating_margin": 0.05,
        "effective_tax_rate": 0.24, "da_pct_revenue": 0.03, "capex_pct_revenue": 0.035, "nwc_pct_revenue": 0.0,
    }
    base = base_assumptions(inputs, wacc=0.075, terminal_growth=0.025)
    values = {name: dcf(apply_scenario(base, name))["enterprise_value"] for name in ("Bear", "Base", "Bull")}
    assert values["Bear"] < values["Base"] < values["Bull"]


def test_growth_fades_linearly_to_terminal_growth():
    path = fade(0.08, 0.02)
    assert path[0] == pytest.approx(0.08) and path[-1] == pytest.approx(0.02)
    assert all(a > b for a, b in zip(path, path[1:]))


def test_default_growth_is_clipped_and_tax_defaults_when_missing():
    inputs = {"total_revenue": 100.0, "revenue_growth": 0.40, "cagr_3y": 0.30, "adjusted_operating_margin": 0.05,
              "effective_tax_rate": None, "da_pct_revenue": 0.03, "capex_pct_revenue": 0.03}
    a = base_assumptions(inputs, wacc=0.08, terminal_growth=0.02)
    assert a.growth_path[0] == pytest.approx(0.12)   # capped
    assert a.tax_rate == pytest.approx(0.24)         # default when unreported


def test_missing_growth_history_is_an_error_not_a_guess():
    with pytest.raises(ValueError):
        base_assumptions({"total_revenue": 100.0, "revenue_growth": None, "cagr_3y": None,
                          "adjusted_operating_margin": 0.05, "da_pct_revenue": 0.03, "capex_pct_revenue": 0.03},
                         wacc=0.08, terminal_growth=0.02)


def test_sensitivity_grid_is_monotonic_and_marks_invalid_pairs():
    grid = sensitivity_grid(flat(growth_path=(0.03,) * 5), 0.0, [0.06, 0.08, 0.10], [0.01, 0.02, 0.06])
    assert grid.loc[0.06, 0.01] > grid.loc[0.10, 0.01]          # lower WACC, higher value
    assert pd.isna(grid.loc[0.06, 0.06])                       # WACC not above terminal growth


def test_inputs_from_history_derives_ratios():
    annual = pd.DataFrame({
        "period_end": pd.to_datetime(["2022-12-31", "2023-12-31", "2024-12-31", "2025-12-31"]),
        "total_revenue": [100.0, 110.0, 121.0, 133.1],
        "capital_expenditures": [4.0, 4.4, 4.84, 5.324],
        "inventory": [10.0, 11.0, 12.0, 13.0], "accounts_receivable_net_current": [2.0, 2.0, 2.0, 2.0],
        "accounts_payable_current": [8.0, 9.0, 10.0, 11.0],
    })
    ltm = pd.Series({"total_revenue": 140.0, "revenue_growth": 0.05, "adjusted_operating_margin": 0.06,
                     "effective_tax_rate": 0.25, "depreciation_amortization": 5.6, "ebitda": 14.0,
                     "net_income": 6.0, "net_debt": 10.0})
    inputs = inputs_from_history(ltm, annual)
    assert inputs["cagr_3y"] == pytest.approx(0.10)
    assert inputs["capex_pct_revenue"] == pytest.approx(0.04)
    assert inputs["da_pct_revenue"] == pytest.approx(0.04)
    assert inputs["nwc_pct_revenue"] == pytest.approx((13 + 2 - 11) / 133.1)


def test_default_return_on_new_capital_credits_half_the_advantage_within_a_cap():
    assert default_ronic(0.075, 0.415) == pytest.approx(0.15)       # capped at 2x WACC
    assert default_ronic(0.075, 0.175) == pytest.approx(0.125)      # midpoint
    assert default_ronic(0.075, 0.03) == pytest.approx(0.075)       # never below WACC
    assert default_ronic(0.075, None) == pytest.approx(0.075)


def test_ten_year_horizon_is_the_default():
    inputs = {"total_revenue": 100.0, "revenue_growth": 0.05, "cagr_3y": 0.05, "adjusted_operating_margin": 0.05,
              "effective_tax_rate": 0.24, "da_pct_revenue": 0.03, "capex_pct_revenue": 0.035, "roic": 0.20}
    a = base_assumptions(inputs, wacc=0.075, terminal_growth=0.025)
    assert len(a.growth_path) == 10 and len(project(a)) == 10
    assert a.terminal_ronic == pytest.approx(0.1375)
    assert len(base_assumptions(inputs, 0.075, 0.025, years=5).growth_path) == 5


def test_reverse_dcf_recovers_a_known_growth_shift():
    a = flat(growth_path=fade(0.04, 0.02, 10), operating_margin_path=(0.08,) * 10, terminal_growth=0.02)
    shifted = a.__class__(**{**a.__dict__, "growth_path": fade(0.04 + 0.03, 0.02, 10)})
    target = dcf(shifted)["enterprise_value"]
    assert implied_growth_shift(a, target) == pytest.approx(0.03, abs=1e-4)


def test_reverse_dcf_returns_none_when_unreachable():
    a = flat(growth_path=fade(0.04, 0.02, 10), operating_margin_path=(0.08,) * 10, terminal_growth=0.02)
    assert implied_growth_shift(a, dcf(a)["enterprise_value"] * 1000) is None


def test_mismatched_paths_are_rejected():
    with pytest.raises(ValueError):
        flat(growth_path=(0.02,) * 5, operating_margin_path=(0.08,) * 4)
