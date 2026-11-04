import math

import pandas as pd
import pytest

from riskunwind import builders
from riskunwind.config import CAPITAL, Limits
from riskunwind.portfolio import Portfolio
from riskunwind.config import sic_to_sector


@pytest.mark.parametrize("sic, sector", [
    (3674, "Semiconductors"),
    (3679, "Electronic Components"),
    (7372, "Software & IT Services"),
    (2834, "Pharma & Biotech"),
    (6022, "Banks"),
    (3999, "SIC39"),
    (math.nan, "Unknown"),
])
def test_sic_to_sector(sic, sector):
    assert sic_to_sector(sic) == sector


def test_every_book_is_120_gross_40_net(baseline, cascade, highvol, market):
    for pf in (baseline, cascade, highvol):
        d = builders.summarize(pf, market)
        assert (d["longs"], d["shorts"]) == (20, 10)
        assert d["gross"] == pytest.approx(1.2, abs=0.01)
        assert d["net"] == pytest.approx(0.4, abs=0.01)
        assert pf.positions["permno"].is_unique


def test_nav_equals_capital_at_entry(baseline):
    # cash + value of positions at entry prices = capital (self-financing)
    value = (baseline.positions["shares"] * baseline.positions["entry_price"]).sum()
    assert baseline.cash + value == pytest.approx(CAPITAL)


def test_baseline_is_clean_at_entry(baseline, highvol, market):
    assert builders.entry_violations(baseline, market) == []
    assert builders.entry_violations(highvol, market) == []


def test_cascade_is_one_stock_plus_its_sector(cascade, market):
    w = builders.entry_weights(cascade, market)
    limits = Limits()
    over_name = w[w["weight"].abs() > limits.single_name]
    sector_net = w.groupby("sector")["weight"].sum()
    over_sector = sector_net[sector_net.abs() > limits.sector]
    assert len(over_name) == 1 and len(over_sector) == 1
    stock_w, sector_w = over_name["weight"].iloc[0], over_sector.iloc[0]
    assert over_name["sector"].iloc[0] == over_sector.index[0]  # the big stock is in the big sector
    assert stock_w == pytest.approx(0.078, abs=0.002)
    assert sector_w == pytest.approx(0.27, abs=0.005)
    # proposal's worked example: $280k over on the stock, $200k over on the sector,
    # trimming the stock by its excess leaves the sector at ~24.2%, so one trade clears both
    stock_excess = stock_w - limits.single_name
    assert stock_excess * CAPITAL == pytest.approx(280_000, rel=0.05)
    assert (sector_w - limits.sector) * CAPITAL == pytest.approx(200_000, rel=0.15)
    assert sector_w - stock_excess == pytest.approx(0.242, abs=0.005)
    assert len(builders.entry_violations(cascade, market)) == 2


def test_cascade_heavy_sector_can_be_chosen(market, entry):
    pf = builders.build(market, "cascade", entry, heavy_sector="Banks")
    w = builders.entry_weights(pf, market)
    assert w.groupby("sector")["weight"].sum()["Banks"] == pytest.approx(0.27, abs=0.005)


def test_cascade_rejects_small_sector(market, entry):
    with pytest.raises(RuntimeError, match="cascade needs"):
        builders.build(market, "cascade", entry, heavy_sector="Not A Sector")


def test_highvol_longs_are_more_volatile(baseline, highvol, market, entry):
    pool = builders.eligible(market, market.trading_day_on_or_after(entry))

    def long_vol(pf):
        longs = pf.positions.loc[pf.positions["shares"] > 0, "permno"]
        return pool.loc[longs, "vol"].mean()

    assert long_vol(highvol) > long_vol(baseline)


def test_at_most_three_per_sector_per_side(baseline, highvol, market):
    for pf in (baseline, highvol):
        w = builders.entry_weights(pf, market)
        side = w["weight"] > 0
        assert w[side].groupby("sector").size().max() <= builders.MAX_PER_SECTOR
        assert w[~side].groupby("sector").size().max() <= builders.MAX_PER_SECTOR


def test_builds_are_deterministic(market, entry):
    for kind in builders.KINDS:
        a = builders.build(market, kind, entry, seed=3).positions
        b = builders.build(market, kind, entry, seed=3).positions
        assert a.equals(b)


def test_csv_round_trip(cascade, tmp_path):
    path = tmp_path / "cascade.csv"
    cascade.to_csv(path)
    back = Portfolio.from_csv(path)
    assert back.name == "cascade"
    pd.testing.assert_frame_equal(back.positions, cascade.positions, check_dtype=False)
