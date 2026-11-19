"""
Testing the state metrics 
"""
import pandas as pd
import pytest
# importing from other files
from riskunwind import builders
from riskunwind.market import MarketData
from riskunwind.portfolio import PORTFOLIO_COLS, Portfolio
from riskunwind.state import daily_state

# Test bank
# Decision of what type of tests to create and help with generating test scenarios were done in conjunction/consultation with Claude.
def tiny_market(prices_a, prices_b):
    # A = Banks (6022)
    # B = Software (7372)
    dates = pd.bdate_range("2020-02-03", periods=len(prices_a))
    rows = []
    for permno, ticker, sic, prices in [(1, "A", 6022, prices_a), (2, "B", 7372, prices_b)]:
        for day, price in zip(dates, prices):
            rows.append({"date": day, "permno": permno, "ticker": ticker, "siccd": sic, "price": price,
                         "ret": 0.0, "volume": 1000.0, "shares_out": 1000})
    return MarketData(pd.DataFrame(rows))

def tiny_book(entry="2020-02-03"):
    # long 100 A at $10 
    # short 50 B at $20 
    # cash = 10000 - 1000 + 1000 = 10000
    positions = pd.DataFrame({
        "permno": [1, 2],
        "ticker": ["A", "B"],
        "shares": [100, -50],
        "entry_price": [10.0, 20.0],
        "entry_date": pd.Timestamp(entry),
    })[PORTFOLIO_COLS]
    return Portfolio("tiny", positions, capital=10_000.0)

def test_hand_worked_book():
    market = tiny_market([10.0, 12.0], [20.0, 30.0])
    state = daily_state(tiny_book(), market)
    # day 2: long 1200, short -1500, cash 10000 --> nav 9700
    assert state.values.iloc[1].tolist() == [1200.0, -1500.0]
    assert state.nav.tolist() == [10_000.0, 9_700.0]
    assert state.weights.iloc[1, 0] == pytest.approx(1200 / 9700)
    assert state.weights.iloc[1, 1] == pytest.approx(-1500 / 9700)
    assert state.sector_weights.iloc[1]["Banks"] == pytest.approx(1200 / 9700)
    assert state.sector_weights.iloc[1]["Software & IT Services"] == pytest.approx(-1500 / 9700)

def test_starts_on_entry_day(baseline, market, entry):
    state = daily_state(baseline, market)
    first = market.trading_day_on_or_after(entry)
    assert state.nav.index[0] == first
    assert state.nav.index[-1] == market.dates[-1]

def test_entry_day_matches_builder(cascade, market):
    state = daily_state(cascade, market)
    assert state.nav.iloc[0] == pytest.approx(cascade.capital)

    w = builders.entry_weights(cascade, market).set_index("permno")
    pd.testing.assert_series_equal(state.weights.iloc[0], w["weight"], check_names=False)
    sector_net = w.groupby("sector")["weight"].sum()
    pd.testing.assert_series_equal(state.sector_weights.iloc[0], sector_net, check_names=False)

def test_sector_weights_add_up_to_stock_weights(highvol, market):
    state = daily_state(highvol, market)
    pd.testing.assert_series_equal(state.sector_weights.sum(axis=1), state.weights.sum(axis=1))

def test_nav_change_is_position_pnl(baseline, market):
    state = daily_state(baseline, market)
    pnl = state.values.diff().sum(axis=1).iloc[1:]
    pd.testing.assert_series_equal(state.nav.diff().iloc[1:], pnl)

def test_missing_price_raises():
    market = tiny_market([10.0, float("nan")], [20.0, 30.0])
    with pytest.raises(ValueError, match="missing prices"):
        daily_state(tiny_book(), market)

def test_mixed_entry_dates_raise():
    market = tiny_market([10.0, 12.0], [20.0, 30.0])
    book = tiny_book()
    book.positions.loc[0, "entry_date"] = pd.Timestamp("2020-02-04")
    with pytest.raises(ValueError, match="entry dates"):
        daily_state(book, market)

def test_csv_round_trip_gives_same_state(cascade, market, tmp_path):
    path = tmp_path / "cascade.csv"
    cascade.to_csv(path)
    back = daily_state(Portfolio.from_csv(path), market)
    pd.testing.assert_series_equal(back.nav, daily_state(cascade, market).nav)
