"""
Daily risk metrics from DailyState
- 1 row per day
- 1 col per metric

Assumptions:
- VaR, shortfall, volatility: historical, today's weights on past returns
- Missing returns count as 0
- Liquidity: can trade `participation` of ADV per day
- Cash buffer: longs only (selling shorts uses cash)
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from riskunwind.config import Params
from riskunwind.market import MarketData
from riskunwind.portfolio import Portfolio
from riskunwind.state import DailyState, daily_state

MIN_VAR_DAYS = 20       # NaN if less history

def historical_risk(state: DailyState, market: MarketData, params: Params = Params()) -> pd.DataFrame:
    """VaR, expected shortfall and volatility, all 1-day and as a fraction of NAV"""
    returns = market.returns[state.weights.columns].fillna(0.0)
    rows = {}
    for day, w in state.weights.iterrows():
        past = returns.loc[:day].tail(params.var_window)
        if len(past) < MIN_VAR_DAYS:
            rows[day] = [np.nan] * 3
            continue
        pnl = past @ w  # what today's book would have made each past day
        cutoff = pnl.quantile(1 - params.var_confidence)
        # VaR = loss at the cutoff, shortfall = avg loss beyond it
        rows[day] = [-cutoff, -pnl[pnl <= cutoff].mean(), pnl.std()]
    return pd.DataFrame.from_dict(rows, orient="index", columns=["var", "expected_shortfall", "volatility"])

def historical_var(state: DailyState, market: MarketData, params: Params = Params()) -> pd.Series:
    """1-day loss as a fraction of NAV, exceeded on (1 - confidence) of past days"""
    return historical_risk(state, market, params)["var"]

def drawdown(state: DailyState) -> pd.Series:
    """Fall from the highest NAV since entry"""
    return 1 - state.nav / state.nav.cummax()

def days_to_liquidate(portfolio: Portfolio, state: DailyState, market: MarketData,
                      params: Params = Params()) -> pd.DataFrame:
    """Days to close each position trading `participation` of ADV per day"""
    shares = portfolio.positions.set_index("permno")["shares"].abs()
    adv = market.adv(params.adv_window).loc[state.nav.index, shares.index]
    return shares / (params.participation * adv)

def cash_buffer(state: DailyState, market: MarketData, params: Params = Params()) -> pd.Series:
    """Long value sellable within 1 day, as a fraction of NAV"""
    longs = state.values.clip(lower=0)
    prices = market.prices.loc[state.nav.index, longs.columns]
    one_day = params.participation * market.adv(params.adv_window).loc[state.nav.index, longs.columns] * prices
    return longs.clip(upper=one_day).sum(axis=1) / state.nav

def daily_metrics(portfolio: Portfolio, market: MarketData, params: Params = Params()) -> pd.DataFrame:
    """All metrics, compare against config.Limits"""
    state = daily_state(portfolio, market)
    metrics = pd.DataFrame({
        "nav": state.nav,
        "gross": state.weights.abs().sum(axis=1),   # longs + |shorts|
        "net": state.weights.sum(axis=1),           # longs - |shorts|
        "drawdown": drawdown(state),
        "max_name": state.weights.abs().max(axis=1),
        "max_sector": state.sector_weights.abs().max(axis=1),
        "days_to_liquidate": days_to_liquidate(portfolio, state, market, params).max(axis=1),
        "cash_buffer": cash_buffer(state, market, params),
    })
    return metrics.join(historical_risk(state, market, params))
