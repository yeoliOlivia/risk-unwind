"""
Plotting raw data

To run: python scripts/plot_panel.py data/raw/crsp_2020q1.csv.gz
"""
import argparse
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

from riskunwind import crsp_data


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("panel", type=Path)
    a = ap.parse_args()

    # print header
    panel = pd.read_csv(a.panel, parse_dates=["date"])
    print(crsp_data.summarize(panel))
    print(panel.head())

    # Reshape: 1 col per stock, 1 row per day
    returns = panel.pivot(index="date", columns="permno", values="ret")
    # avg returns across all stocks
    avg = returns.mean(axis=1)
    # compute growth of $1 invested
    growth = (1 + avg).cumprod()

    # plot
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(growth.index, growth.values)
    ax.axhline(1.0, color="grey", linewidth=0.8)
    ax.set_title(f"Growth of $1, equal-weighted across {returns.shape[1]} stocks")
    ax.set_ylabel("value of $1")
    fig.autofmt_xdate()
    fig.tight_layout()

    out = a.panel.with_name(a.panel.name.replace(".csv.gz", ".png"))
    fig.savefig(out, dpi=120)
    print(f"saved {out}")
    plt.show()


if __name__ == "__main__":
    main()
