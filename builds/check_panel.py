"""
Ensure syntehtic panel data is valid and compatible with CRSP 
for dataset creation purposes

To run:
1. python builds/check_panel.py data/raw/crsp_synthetic.csv.gz
2. python builds/check_panel.py data/raw/crsp_2020q1.csv.gz
"""
import argparse
from pathlib import Path
import pandas as pd
from riskunwind import crsp_data

def check(panel: pd.DataFrame) -> list[str]:
    """Returns a list of problems. Empty list = all good"""
    problems = []
    if list(panel.columns) != crsp_data.COLUMNS:
        problems.append(f"columns are {list(panel.columns)}, expected {crsp_data.COLUMNS}")
        return problems  # the checks below need the right columns
    if panel.duplicated(["date", "permno"]).any():
        problems.append("duplicate (date, permno) rows")
    if (panel["price"] <= 0).any():
        problems.append("some prices are zero or negative")
    if (panel["ret"] < -1).any():
        problems.append("some returns are below -100%")
    if (panel["volume"] < 0).any():
        problems.append("some volumes are negative")
    return problems

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("panel", type=Path)
    a = ap.parse_args()

    panel = pd.read_csv(a.panel, parse_dates=["date"])
    print(crsp_data.summarize(panel))
    print(panel.head())

    problems = check(panel)
    for p in problems:
        print(f"PROBLEM: {p}")
    print("OK" if not problems else f"{len(problems)} problem(s)")

if __name__ == "__main__":
    main()
