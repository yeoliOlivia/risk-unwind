"""
Takes CRSP data from WRDS and puts it into data/raw/

To run:
    python builds/pull_crsp.py --tag 2020q1 --start 2020-01-02 --end 2020-03-31
"""
import argparse
from datetime import date
from pathlib import Path
from riskunwind import crsp_data

DATA_RAW_PATH = Path(__file__).resolve().parents[1] / "data" / "raw"

def main() -> None:
    # command line parse for dates, number of stocks, and output tag
    ap = argparse.ArgumentParser(description=__doc__, 
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", 
                    default="2020q1", 
                    help="output file is data/raw/crsp_<tag>.csv.gz")
    # grab dates
    ap.add_argument("--start", type=date.fromisoformat, default=date(2020, 1, 2))
    ap.add_argument("--end", type=date.fromisoformat, default=date(2020, 3, 31))
    ap.add_argument("--stockcount", 
                    type=int, 
                    default=100, help="largest N stocks by market cap at --start")
    a = ap.parse_args()

    db = crsp_data.connect()
    try:
        panel, table = crsp_data.pull(db, a.start, a.end, a.stockcount)
    finally:
        db.close()

    # save data to output
    out = DATA_RAW_PATH / f"crsp_{a.tag}.csv.gz"
    panel.to_csv(out, index=False)
    print(f"source: crsp.{table}\n{crsp_data.summarize(panel)}\nwrote {out}")


if __name__ == "__main__":
    main()
