"""
Rule detectors and first handlers
- detectors: one exception per day per stock or sector over a limit
- handlers: trim a stock or sector back to its limit, VaR and liquidity escalate

Assumptions:
- Trade at that day's close, selling turns stock into cash, so NAV is unchanged
- Shares rounded up so the trade clears the limit
- Sector trim only touches the side driving it (longs if net long), in proportion to size
- Each proposal fixes its own breach only, a stock and sector trim on the same day can overlap
"""
from __future__ import annotations
from functools import partial
import numpy as np
import pandas as pd
from riskunwind.config import Limits, Params
from riskunwind.exceptions import (Action, LiquidityBreach, Pipeline, Response, SectorBreach,
                                   SingleNameBreach, VarBreach, escalate)
from riskunwind.market import MarketData
from riskunwind.metrics import daily_metrics, days_to_liquidate
from riskunwind.portfolio import Portfolio
from riskunwind.state import daily_state

class Book:
    """Portfolio plus everything the rules need, computed once"""
    def __init__(self, portfolio: Portfolio, market: MarketData,
                 limits: Limits = Limits(), params: Params = Params()):
        self.portfolio, self.market, self.limits = portfolio, market, limits
        self.state = daily_state(portfolio, market)
        self.metrics = daily_metrics(portfolio, market, params)
        self.dtl = days_to_liquidate(portfolio, self.state, market, params)
        pos = portfolio.positions
        self.permno = pd.Series(pos["permno"].values, index=pos["ticker"])
        self.sector = market.sector.reindex(self.state.weights.columns).fillna("Unknown")

    def ticker(self, permno) -> str:
        return self.market.ticker[permno]

def over(table: pd.DataFrame, limit: float) -> list[tuple]:
    """(day, column) pairs where |value| > limit, in day order"""
    hits = (table.abs() > limit).stack()
    return list(hits[hits].index)

def single_name(book: Book):
    w, limit = book.state.weights, book.limits.single_name
    for day, permno in over(w, limit):
        yield SingleNameBreach(day, abs(w.at[day, permno]), limit, book.ticker(permno))

def sector(book: Book):
    sw, limit = book.state.sector_weights, book.limits.sector
    for day, name in over(sw, limit):
        yield SectorBreach(day, abs(sw.at[day, name]), limit, name)

def var(book: Book):
    v, limit = book.metrics["var"], book.limits.var
    for day in v.index[v > limit]:
        yield VarBreach(day, v[day], limit)

def liquidity(book: Book):
    limit = book.limits.days_to_liquidate
    for day, permno in over(book.dtl, limit):
        yield LiquidityBreach(day, book.dtl.at[day, permno], limit, book.ticker(permno))

DETECTORS = [single_name, sector, var, liquidity]

def to_shares(book: Book, day, cut: pd.Series) -> pd.Series:
    """Weight to remove (signed like the position) -> shares to trade, rounded up"""
    nav = book.state.nav[day]
    prices = book.market.prices.loc[day, cut.index]
    return (-np.sign(cut) * np.ceil(cut.abs() * nav / prices)).astype(int)

def trim_name(book: Book, exc: SingleNameBreach) -> Response:
    permno = book.permno[exc.subject]
    w = book.state.weights.at[exc.day, permno]
    cut = pd.Series({permno: np.sign(w) * (abs(w) - exc.limit)})
    side = "sell" if w > 0 else "cover"
    return Response(exc, Action.REPAIR, f"{side} {exc.subject} to {exc.limit:.0%}",
                    trades=to_shares(book, exc.day, cut))

def trim_sector(book: Book, exc: SectorBreach) -> Response:
    w = book.state.weights.loc[exc.day]
    in_sector = w[book.sector == exc.subject]
    net = in_sector.sum()
    side = in_sector[np.sign(in_sector) == np.sign(net)]
    cut = (abs(net) - exc.limit) * side / abs(side.sum())
    return Response(exc, Action.REPAIR, f"trim {exc.subject} to {exc.limit:.0%}",
                    trades=to_shares(book, exc.day, cut))

def needs_solver(exc) -> Response:
    return escalate(exc, "no single-trade fix, needs the solver")

def rule_pipeline(book: Book) -> Pipeline:
    p = Pipeline()
    p.register(SingleNameBreach, partial(trim_name, book))
    p.register(SectorBreach, partial(trim_sector, book))
    p.register(VarBreach, needs_solver)
    p.register(LiquidityBreach, needs_solver)
    return p

def check(book: Book) -> list[Response]:
    return rule_pipeline(book).run(DETECTORS, book)
