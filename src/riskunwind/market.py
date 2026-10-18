"""
Takes in panel to reshape into matrices: 
- 1 row per day, 1 col per stock
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from riskunwind.crsp_data import COLS
from riskunwind.config import sic_to_sector

class MarketData:
    def __init__(self, panel: pd.DataFrame):
        missing = [c for c in COLS if c not in panel.columns]
        if missing:
            raise ValueError(f"panel is missing columns {missing}")

        # pivot 
        self.prices = panel.pivot(index="date", columns="permno", values="price").sort_index()
        self.returns = panel.pivot(index="date", columns="permno", values="ret").sort_index()
        self.volume = panel.pivot(index="date", columns="permno", values="volume").sort_index()

        # recent ticker and SIC for each stock
        latest = panel.sort_values("date").groupby("permno").last()
        self.ticker = latest["ticker"]
        self.sector = latest["siccd"].map(sic_to_sector)

    @classmethod
    def from_csv(cls, path: str | Path) -> MarketData:
        return cls(pd.read_csv(path, parse_dates=["date"]))

    @property
    def dates(self) -> pd.DatetimeIndex:
        return self.prices.index

    def trading_day_on_or_after(self, day) -> pd.Timestamp:
        """First trading day on or after `day` (weekend -> Monday)"""
        later = self.dates[self.dates >= pd.Timestamp(day)]
        if later.empty:
            raise ValueError(f"no trading day on or after {pd.Timestamp(day).date()}")
        return later[0]

    def adv(self, window: int) -> pd.DataFrame:
        """Average daily volume (shares) over the last `window` days, including today"""
        return self.volume.rolling(window, min_periods=window).mean()
