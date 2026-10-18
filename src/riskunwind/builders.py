"""
Creates example long/short portfolios from MarketData (~$10M, 20 longs, 10 shorts)

Returns Portfolio:
- baseline
- cascade
- highvol

Each book has: longs = 80% of NAV, shorts = 40% of NAV
gross = 120% (longs + |shorts|)
net = 40% (longs - |shorts|)
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from riskunwind.config import CAPITAL, Limits
from riskunwind.market import MarketData
from riskunwind.portfolio import PORTFOLIO_COLS, Portfolio

KINDS = ("baseline", "cascade", "highvol")

LONG_GROSS = 0.80
SHORT_GROSS = 0.40
N_LONG = 20
N_SHORT = 10
MAX_PER_SECTOR = 3   
VOL_WINDOW = 250
MIN_VOL_DAYS = 20 # 2020 data has missing ret

# create a cascade
#   --> 1 stock at 7.8% + 4 peers at 4.8% = 27% in one sector
# stock is 2.8% ($280k) over the 5% limit, sector is 2% ($200k) over the 25% limit
CASCADE_STOCK = 0.078
CASCADE_PEER = 0.048
N_CASCADE_PEERS = 4
# trimming the stock by 2.8% drops the sector to 24.2%, so one trade clears both

def trailing_vol(returns: pd.DataFrame) -> pd.Series:
    """SD of daily returns per stock"""
    window = returns.tail(VOL_WINDOW)
    vol = window.std()
    return vol.where(window.notna().sum() >= MIN_VOL_DAYS)

def eligible(market: MarketData, entry: pd.Timestamp, top_n: int = 300,
             min_price: float = 5.0, adv_window: int = 20) -> pd.DataFrame:
    """ at `entry`: price >= $5, top_n by dollar volume """
    price = market.prices.loc[entry]
    dollar_volume = market.prices * market.volume # dollar ADV = avg (price * shares traded) for last 20d
    dollar_adv = dollar_volume.rolling(adv_window, min_periods=adv_window).mean().loc[entry]
    vol = trailing_vol(market.returns.loc[:entry])

    pool = pd.DataFrame({
        "price": price,
        "dollar_adv": dollar_adv,
        "vol": vol,
        "sector": market.sector.reindex(price.index),
    })
    keep = (pool["price"] >= min_price) & pool["dollar_adv"].notna() & pool["vol"].notna()
    return pool[keep].nlargest(top_n, "dollar_adv")

def pick_in_order(order, pool: pd.DataFrame, n: int, exclude_sectors=()) -> list[int]:
    """Skips excluded and sectors w MAX_PER_SECTOR picks"""
    chosen = []
    per_sector = {}
    for permno in order:
        sector = pool.at[permno, "sector"]
        if sector in exclude_sectors or per_sector.get(sector, 0) >= MAX_PER_SECTOR:
            continue
        chosen.append(int(permno))
        per_sector[sector] = per_sector.get(sector, 0) + 1
        if len(chosen) == n:
            return chosen
    raise RuntimeError(f"only found {len(chosen)} of {n} stocks within the sector cap, use a wider panel")

def pick_random(pool: pd.DataFrame, n: int, rng, exclude_sectors=()) -> list[int]:
    order = rng.permutation(pool.index.to_numpy())
    return pick_in_order(order, pool, n, exclude_sectors)

def make_weights(n: int, gross: float, rng) -> np.ndarray:
    w = rng.uniform(0.85, 1.10, n)
    return w / w.sum() * gross

def cascade_longs(pool: pd.DataFrame, rng, heavy_sector: str) -> dict[int, float]:
    """
    5 stocks from the heavy  = 27%
    15 more from other =  53%
    """
    heavy = pool[pool["sector"] == heavy_sector]
    n_heavy = 1 + N_CASCADE_PEERS
    if len(heavy) < n_heavy:
        raise RuntimeError(f"sector {heavy_sector!r} has {len(heavy)} eligible stocks, cascade needs {n_heavy}; "
                           f"pick another with --heavy-sector")

    names = [int(p) for p in rng.permutation(heavy.index.to_numpy())[:n_heavy]]
    longs = {names[0]: CASCADE_STOCK}
    for permno in names[1:]:
        longs[permno] = CASCADE_PEER

    rest = pick_random(pool.drop(index=names), N_LONG - n_heavy, rng, exclude_sectors=(heavy_sector,))
    rest_gross = LONG_GROSS - sum(longs.values())
    longs.update(zip(rest, make_weights(len(rest), rest_gross, rng)))
    return longs

def build(market: MarketData, kind: str, entry_date, seed: int = 0,
          capital: float = CAPITAL, heavy_sector: str | None = None) -> Portfolio:
    rng = np.random.default_rng(seed)
    entry = market.trading_day_on_or_after(entry_date)
    pool = eligible(market, entry)

    # permno -> signed weight (fraction of NAV)
    if kind == "cascade":
        if heavy_sector is None:
            heavy_sector = pool["sector"].value_counts().index[0]  # sector with the most stocks
        weights = cascade_longs(pool, rng, heavy_sector)
        # shorts kept out of the heavy sector so they don't offset the planted 27%
        short_exclude = (heavy_sector,)
    elif kind == "baseline":
        longs = pick_random(pool, N_LONG, rng)
        weights = dict(zip(longs, make_weights(N_LONG, LONG_GROSS, rng)))
        short_exclude = ()
    elif kind == "highvol":
        # most volatile first, still max 3 per sector
        by_vol = pool["vol"].sort_values(ascending=False).index
        longs = pick_in_order(by_vol, pool, N_LONG)
        weights = dict(zip(longs, make_weights(N_LONG, LONG_GROSS, rng)))
        short_exclude = ()
    else:
        raise ValueError(f"unknown portfolio kind {kind!r}, expected one of {KINDS}")

    shorts = pick_random(pool.drop(index=list(weights)), N_SHORT, rng, short_exclude)
    weights.update(zip(shorts, -make_weights(N_SHORT, SHORT_GROSS, rng)))

    # weight = share count at entry price
    permnos = list(weights)
    price = market.prices.loc[entry, permnos]
    shares = (pd.Series(weights) * capital / price).round().astype(int)
    positions = pd.DataFrame({
        "permno": permnos,
        "ticker": market.ticker.reindex(permnos).values,
        "shares": shares.values,
        "entry_price": price.values,
        "entry_date": entry,
    })[PORTFOLIO_COLS]
    return Portfolio(kind, positions, capital)

def entry_weights(portfolio: Portfolio, market: MarketData) -> pd.DataFrame:
    """Weight of each position on entry day"""
    pos = portfolio.positions
    return pd.DataFrame({
        "permno": pos["permno"],
        "ticker": pos["ticker"],
        "sector": market.sector.reindex(pos["permno"]).fillna("Unknown").values,
        "weight": pos["shares"] * pos["entry_price"] / portfolio.capital,
    })

def entry_violations(portfolio: Portfolio, market: MarketData, limits: Limits = Limits()) -> list[str]:
    """
    Limits broken during entry day
        - cascade > 2
        - baseline = 0
    """
    w = entry_weights(portfolio, market)
    problems = []
    too_big = w[w["weight"].abs() > limits.single_name]
    for _, row in too_big.iterrows():
        problems.append(f"single-name: {row['ticker']} {abs(row['weight']):.1%} vs limit {limits.single_name:.0%}")

    sector_net = w.groupby("sector")["weight"].sum()
    for sector, net in sector_net[sector_net.abs() > limits.sector].items():
        problems.append(f"sector: {sector} {abs(net):.1%} vs limit {limits.sector:.0%}")
    return problems

def summarize(portfolio: Portfolio, market: MarketData) -> dict:
    w = entry_weights(portfolio, market)
    sector_net = w.groupby("sector")["weight"].sum()
    return {
        "names": len(w),
        "longs": int((w["weight"] > 0).sum()),
        "shorts": int((w["weight"] < 0).sum()),
        "gross": w["weight"].abs().sum(),
        "net": w["weight"].sum(),
        "max_name": w["weight"].abs().max(),
        "top_sector": sector_net.abs().idxmax(),
        "top_sector_net": sector_net.abs().max(),
    }
