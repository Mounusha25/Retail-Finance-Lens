from decimal import Decimal

import pytest

from financial_analysis.config import Settings
from financial_analysis.validate import accounting_tolerance


def test_sec_identity_requires_contact_email():
    with pytest.raises(ValueError):
        Settings(sec_user_agent="anonymous bot").require_sec_identity()


def test_accounting_tolerance_uses_materiality_floor():
    assert accounting_tolerance(Decimal("1000000000")) == Decimal("5000000")
    assert accounting_tolerance(Decimal("100000000000")) == Decimal("10000000.0000")
