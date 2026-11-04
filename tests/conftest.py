import pytest

from riskunwind import builders
from riskunwind.market import MarketData
from riskunwind.synthetic import make_panel


@pytest.fixture(scope="session")
def market():
    return MarketData(make_panel())


@pytest.fixture(scope="session")
def entry():
    return "2020-02-03"


@pytest.fixture(scope="session")
def baseline(market, entry):
    return builders.build(market, "baseline", entry)


@pytest.fixture(scope="session")
def cascade(market, entry):
    return builders.build(market, "cascade", entry)


@pytest.fixture(scope="session")
def highvol(market, entry):
    return builders.build(market, "highvol", entry)
