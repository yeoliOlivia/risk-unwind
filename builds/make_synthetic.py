"""
One-time use file!

Create dataset in data/raw/crsp_synthetic.csv.gz

To run:
1. python builds/make_synthetic.py
OR use specific dates 
2. python builds/make_synthetic.py --start 2020-01-02 --end 2020-03-31 --seed 1

"""
import argparse
from pathlib import Path
from riskunwind import crsp_data, synthetic

DATA_RAW_PATH = Path(__file__).resolve().parents[1] / "data" / "raw"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default="2020-05-29")
    ap.add_argument("--seed", type=int, default=0, help="same seed gives the same data")
    a = ap.parse_args()
    # build panel with 1 row per (date, permno)
    panel = synthetic.make_panel(a.start, a.end, a.seed)

    out = DATA_RAW_PATH / "crsp_synthetic.csv.gz"
    panel.to_csv(out, index=False)
    print(f"source: synthetic (seed {a.seed})\n{crsp_data.summarize(panel)}\nwrote {out}")


if __name__ == "__main__":
    main()
