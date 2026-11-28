"""
Testing the rule detectors and handlers
"""
import pandas as pd
import pytest
from riskunwind.config import Limits
from riskunwind.exceptions import Action, LiquidityBreach, SectorBreach, SingleNameBreach, VarBreach
from riskunwind.market import MarketData
from riskunwind.portfolio import PORTFOLIO_COLS, Portfolio
from riskunwind.rules import Book, check

# Decision of what type of tests to create were done in conjunction/consultation with Claude.
def one_day_book(stocks, limits):
    # stocks: (permno, ticker, sic, price, shares), NAV = $10,000
    day = pd.Timestamp("2020-02-03")
    market = MarketData(pd.DataFrame([
        {"date": day, "permno": p, "ticker": t, "siccd": sic, "price": px, "ret": 0.0,
         "volume": 1000.0, "shares_out": 1000} for p, t, sic, px, _ in stocks]))
    positions = pd.DataFrame({
        "permno": [s[0] for s in stocks],
        "ticker": [s[1] for s in stocks],
        "shares": [s[4] for s in stocks],
        "entry_price": [s[3] for s in stocks],
        "entry_date": day,
    })[PORTFOLIO_COLS]
    return Book(Portfolio("tiny", positions, capital=10_000.0), market, limits)

def test_hand_worked_stock_trims():
    # long A $1,000 (10%), short B $800 (-8%), limit 5%
    book = one_day_book([(1, "A", 6022, 10.0, 100), (2, "B", 7372, 20.0, -40)], Limits(single_name=0.05))
    responses = check(book)
    assert [type(r.exc) for r in responses] == [SingleNameBreach, SingleNameBreach]
    # sell 5% of $10,000 / $10 = 50 A, cover 3% of $10,000 / $20 = 15 B
    assert responses[0].trades.to_dict() == {1: -50}
    assert responses[1].trades.to_dict() == {2: 15}
    assert responses[0].reason == "sell A to 5%"

def test_hand_worked_sector_trim():
    # banks: long A 10%, long C 25%, short D -5% -> net 30%, 5% over
    book = one_day_book([(1, "A", 6022, 10.0, 100), (3, "C", 6022, 25.0, 100), (4, "D", 6022, 10.0, -50)],
                        Limits(single_name=1.0, sector=0.25))
    [r] = check(book)
    assert isinstance(r.exc, SectorBreach) and r.exc.subject == "Banks"
    # longs only, split 10:25 -> $142.86 of A, $357.14 of C, rounded up to whole shares
    assert r.trades.to_dict() == {1: -15, 3: -15}

def test_baseline_is_clean(baseline, market):
    assert check(Book(baseline, market)) == []

def test_detects_every_breach_day(cascade, market):
    book = Book(cascade, market)
    flagged = {r.exc.day for r in check(book) if isinstance(r.exc, SingleNameBreach)}
    m = book.metrics
    assert flagged == set(m.index[m["max_name"] > book.limits.single_name])

def test_repairs_clear_the_limit(cascade, market):
    book = Book(cascade, market)
    shares = cascade.positions.set_index("permno")["shares"]
    for r in check(book):
        prices = market.prices.loc[r.exc.day]
        nav = book.state.nav[r.exc.day]
        new = (shares + r.trades.reindex(shares.index, fill_value=0)) * prices[shares.index] / nav
        if isinstance(r.exc, SingleNameBreach):
            assert abs(new[r.trades.index[0]]) <= r.exc.limit
        else:
            assert abs(new[book.sector == r.exc.subject].sum()) <= r.exc.limit
            assert r.exc.limit > abs(new[book.sector == r.exc.subject].sum()) - 0.001  # not over-trimmed

def test_var_and_liquidity_escalate(highvol, market):
    responses = check(Book(highvol, market, Limits(var=0.001, days_to_liquidate=0.0)))
    hard = [r for r in responses if isinstance(r.exc, (VarBreach, LiquidityBreach))]
    assert {type(r.exc) for r in hard} == {VarBreach, LiquidityBreach}
    assert all(r.action is Action.ESCALATE for r in hard)
