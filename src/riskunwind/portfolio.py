"""
Portfolio class for testing

Assumptions:
- No dividends
- Share counts fixed at entry
- Cash set so NAV = capital 
- No interest or borrow cost
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import pandas as pd

from riskunwind.config import CAPITAL

PORTFOLIO_COLS = ["permno", "ticker", "shares", "entry_price", "entry_date"]

@dataclass
class Portfolio:
    name: str
    positions: pd.DataFrame # PORTFOLIO_COLS shares < 0 for shorts
    capital: float = CAPITAL

    @property
    def cash(self) -> float:
        cost = self.positions["shares"] * self.positions["entry_price"]
        return self.capital - float(cost.sum())

    @classmethod
    def from_csv(cls, path: str | Path, capital: float = CAPITAL) -> Portfolio:
        """File name (no .csv) becomes the portfolio name"""
        path = Path(path)
        df = pd.read_csv(path, parse_dates=["entry_date"])
        missing = [c for c in PORTFOLIO_COLS if c not in df.columns]
        if missing:
            raise ValueError(f"{path.name} is missing columns {missing}")
        return cls(path.stem, df[PORTFOLIO_COLS], capital)

    def to_csv(self, path: str | Path) -> None:
        self.positions[PORTFOLIO_COLS].to_csv(path, index=False)
