import pytest
from decimal import Decimal
from pydantic import ValidationError

from platform_py.types import AssetSpec, WETH_ETHEREUM


def test_asset_spec_requires_exactly_one_amount_field():
    # None specified -> error
    with pytest.raises(ValidationError):
        AssetSpec(asset=WETH_ETHEREUM)

    # Two specified -> error
    with pytest.raises(ValidationError):
        AssetSpec(asset=WETH_ETHEREUM, amount=Decimal("1"), percentage=Decimal("0.1"))

    # Valid cases (no error)
    AssetSpec(asset=WETH_ETHEREUM, amount=Decimal("1"))
    AssetSpec(asset=WETH_ETHEREUM, percentage=Decimal("0.5"))
    AssetSpec(asset=WETH_ETHEREUM, target_weight=Decimal("0.25"))
