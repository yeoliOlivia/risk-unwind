"""
Builds example portfolios and outputs into data/portfolios/

To run:
1. python builds/build_portfolios.py --panel data/raw/crsp_synthetic.csv.gz
2. python builds/build_portfolios.py --panel data/raw/crsp_2020q1.csv.gz
OR choose the cascade sector
3. python builds/build_portfolios.py --panel data/raw/crsp_2020q1.csv.gz --heavy-sector "Pharma & Biotech"
"""
import argparse
from pathlib import Path
from riskunwind import builders
from riskunwind.market import MarketData

DATA_PORTFOLIOS_PATH = Path(__file__).resolve().parents[1] / "data" / "portfolios"

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--panel", type=Path, required=True)
    ap.add_argument("--entry-date", default="2020-02-03")
    ap.add_argument("--seed", type=int, default=0, help="same seed gives the same books")
    ap.add_argument("--heavy-sector", default=None,
                    help="cascade sector (default: sector with the most eligible stocks)")
    ap.add_argument("--out-dir", type=Path, default=DATA_PORTFOLIOS_PATH)
    a = ap.parse_args()

    # load maket data
    market = MarketData.from_csv(a.panel)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    for kind in builders.KINDS:
        pf = builders.build(market, kind, a.entry_date, a.seed, heavy_sector=a.heavy_sector)
        out = a.out_dir / f"{kind}.csv"
        pf.to_csv(out)

        # Print each book's entry-day numbers
        # ! if limit broken 
        s = builders.summarize(pf, market)
        print(f"{kind:9s} {s['names']} stocks ({s['longs']} long, {s['shorts']} short) | "
              f"gross {s['gross']:.0%} | net {s['net']:.0%} | max stock {s['max_name']:.1%} | "
              f"top sector {s['top_sector']} {s['top_sector_net']:.1%}\nwrote {out}")
        for v in builders.entry_violations(pf, market):
            print(f"  ! {v}")


if __name__ == "__main__":
    main()
