"""
Create fake data set. 
Includes daily stocks with the same columns as the CRSP pull

Contains: one market factor + per-stock noise
"""
from __future__ import annotations
import numpy as np
import pandas as pd

# bring in col names for consistency 
from riskunwind.crsp_data import COLUMNS

SIC_MIX = [         # code, count
    (3674, 20),     # semiconductors - most # here for cascade and sector tests
    (7372, 10),     # software
    (2834, 10),     # pharma
    (6022, 10),     # banks
    (1311, 10),     # oil & gas
    (4911, 10),     # utilities
    (5311, 10),     # retail
    (3571, 10),     # computer hardware
    (3711, 10),     # autos
]

# economic turmoil Feb - March 2020 
# to test VaR and other risk metrics
CRASH_START = "2020-02-24"
CRASH_END = "2020-03-23"

def make_market_factor(rng, dates: pd.DatetimeIndex) -> np.ndarray:
    """
    One market return per day. 
    For CRASH dates, adds extra negative + volatile returns
    """
    factor = rng.normal(0.0004, 0.01, len(dates))
    crash = (dates >= CRASH_START) & (dates <= CRASH_END)
    factor[crash] += rng.normal(-0.012, 0.03, crash.sum())
    return factor

def make_returns(rng, factor: np.ndarray, n_stocks: int) -> np.ndarray:
    """
    Each row gets random beta * market + noise
    Returns matrix, 1 row per day, 1 col per stock
     """
    beta = rng.uniform(0.6, 1.6, n_stocks)
    noise_vol = rng.uniform(0.008, 0.025, n_stocks)
    noise = rng.normal(0, 1, (len(factor), n_stocks)) * noise_vol
    rets = factor[:, None] * beta + noise
    return np.clip(rets, -0.5, 0.5)

def make_prices(rng, rets: np.ndarray) -> np.ndarray:
    """Compound stock returns randomly"""
    start_price = rng.uniform(15, 200, rets.shape[1])
    return start_price * np.cumprod(1 + rets, axis=0)


def make_volume(rng, n_days: int, n_stocks: int) -> np.ndarray:
    """Assigns shares traded per day"""
    typical = rng.uniform(5e5, 5e6, n_stocks)
    return rng.lognormal(np.log(typical), 0.3, (n_days, n_stocks)).round()


def make_panel(start: str = "2019-01-01", end: str = "2020-05-29", seed: int = 0) -> pd.DataFrame:
    """
    Build the fake panel for publishing. 
    1 row per (date, permno)
    """
    # uses seed if reproducibility needed
    rng = np.random.default_rng(seed)  
    dates = pd.bdate_range(start, end) # Default = 2019+ so 250-day VaR has history before crash
    sics = [sic for sic, count in SIC_MIX for _ in range(count)]
    n_days, n_stocks = len(dates), len(sics)

    factor = make_market_factor(rng, dates)
    rets = make_returns(rng, factor, n_stocks)
    prices = make_prices(rng, rets)
    volume = make_volume(rng, n_days, n_stocks)
    shares_out = rng.uniform(5e4, 5e6, n_stocks)  # thousands

    # matrices are (day, stock)
    # each date repeats n_stocks times 
    # each stock list repeats n_days times
    permnos = 10000 + np.arange(n_stocks)
    tickers = [f"S{i:03d}" for i in range(n_stocks)]
    panel = pd.DataFrame({
        "date": np.repeat(dates, n_stocks),
        "permno": np.tile(permnos, n_days),
        "ticker": np.tile(tickers, n_days),
        "siccd": np.tile(sics, n_days).astype(float),
        "price": prices.ravel(),
        "ret": rets.ravel(),
        "volume": volume.ravel(),
        "shares_out": np.tile(shares_out, n_days),
    })
    return panel[COLUMNS]
