"""
Creates the state of a portfolio 
- from entry day onward 
-  row per day

Assumptions:
- Same as Portfolio: fixed shares, flat cash
- Raw prices 
"""
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from riskunwind.market import MarketData
from riskunwind.portfolio import Portfolio

@dataclass(frozen=True)
class DailyState:
    values: pd.DataFrame        # $ by stock, shorts are negative
    nav: pd.Series              # cash + sum of values
    weights: pd.DataFrame       # value/nav by stock
    sector_weights: pd.DataFrame 

def daily_state(portfolio: Portfolio, market: MarketData) -> DailyState:
    pos = portfolio.positions.set_index("permno")
    entry_dates = pos["entry_date"].unique()
    if len(entry_dates) != 1:
        raise ValueError(f"{portfolio.name} has {len(entry_dates)} entry dates, expected 1")

    prices = market.prices.loc[entry_dates[0]:, pos.index]
    missing = prices.columns[prices.isna().any()].tolist()
    if missing:
        raise ValueError(f"{portfolio.name} holds stocks with missing prices: {missing}")

    # compute daily metrics
    values = prices * pos["shares"]
    nav = portfolio.cash + values.sum(axis=1)
    weights = values.div(nav, axis=0)
    sectors = market.sector.reindex(weights.columns).fillna("Unknown")
    sector_weights = weights.T.groupby(sectors).sum().T
    return DailyState(values, nav, weights, sector_weights)
