"""
Testing the risk metrics
"""
import pandas as pd
import pytest
# importing from other files
from riskunwind import builders
from riskunwind.config import Params
from riskunwind.market import MarketData
from riskunwind.metrics import MIN_VAR_DAYS, cash_buffer, daily_metrics, days_to_liquidate, historical_var
from riskunwind.portfolio import PORTFOLIO_COLS, Portfolio
from riskunwind.state import daily_state

# one stock, price fixed at $10, returns and volume set by hand
def one_stock_market(rets, volume=1000.0):
    dates = pd.bdate_range("2020-01-01", periods=len(rets))
    return MarketData(pd.DataFrame({
        "date": dates, "permno": 1, "ticker": "A", "siccd": 6022, "price": 10.0,
        "ret": rets, "volume": volume, "shares_out": 1000,
    }))

def one_stock_book(market, shares):
    positions = pd.DataFrame({
        "permno": [1],
        "ticker": ["A"],
        "shares": [shares],
        "entry_price": [10.0],
        "entry_date": market.dates[-1],
    })[PORTFOLIO_COLS]
    return Portfolio("one", positions, capital=10.0 * abs(shares))

def test_var_hand_worked():
    # all in one stock (weight 1), past returns -0.1% to -2.0%
    # 5th percentile of 20 days = -0.020 + 0.95 * 0.001 --> VaR 1.905%
    market = one_stock_market([-k / 1000 for k in range(1, 21)])
    pf = one_stock_book(market, 100)
    var = historical_var(daily_state(pf, market), market)
    assert var.iloc[-1] == pytest.approx(0.01905)

def test_var_needs_enough_history():
    market = one_stock_market([0.01] * (MIN_VAR_DAYS - 1))
    pf = one_stock_book(market, 100)
    assert historical_var(daily_state(pf, market), market).isna().all()

def test_var_uses_window():
    # only the last 20 days count: all 0 --> VaR 0
    market = one_stock_market([-0.5] * 10 + [0.0] * 20)
    pf = one_stock_book(market, 100)
    var = historical_var(daily_state(pf, market), market, Params(var_window=20))
    assert var.iloc[-1] == pytest.approx(0.0)

def test_days_to_liquidate_hand_worked():
    # 500 shares, 20% of 1000 a day = 200 a day 
    # --> 2.5 days, same for a short
    market = one_stock_market([0.0] * 20)
    for shares in (500, -500):
        pf = one_stock_book(market, shares)
        dtl = days_to_liquidate(pf, daily_state(pf, market), market)
        assert dtl.iloc[-1, 0] == pytest.approx(2.5)

def test_cash_buffer_hand_worked():
    # long 500 shares ($5000), 200 sellable a day ($2000) 
    #  --> 40% of NAV
    market = one_stock_market([0.0] * 20)
    pf = one_stock_book(market, 500)
    assert cash_buffer(daily_state(pf, market), market).iloc[-1] == pytest.approx(0.4)

def test_cash_buffer_ignores_shorts():
    market = one_stock_market([0.0] * 20)
    pf = one_stock_book(market, -500)
    assert cash_buffer(daily_state(pf, market), market).iloc[-1] == 0.0

def test_cascade_entry_day_matches_builder(cascade, market):
    m = daily_metrics(cascade, market).iloc[0]
    assert m["max_name"] == pytest.approx(0.078, abs=0.002)
    assert m["max_sector"] == pytest.approx(0.27, abs=0.005)

def test_highvol_has_higher_var(baseline, highvol, market):
    assert daily_metrics(highvol, market)["var"].mean() > daily_metrics(baseline, market)["var"].mean()

def test_metrics_cover_every_day(baseline, market):
    m = daily_metrics(baseline, market)
    assert m.index.equals(daily_state(baseline, market).nav.index)
    assert m.notna().all().all()  # synthetic panel has a year of history before entry
