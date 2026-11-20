"""
Writes a text and an HTML risk report for each portfolio into data/reports/

To run (after build_portfolios.py):
1. python builds/risk_report.py --panel data/raw/crsp_2020q1.csv.gz
OR pick the books
2. python builds/risk_report.py --panel data/raw/crsp_2020q1.csv.gz --portfolios data/portfolios/cascade.csv
"""
import argparse
from pathlib import Path
from riskunwind.market import MarketData
from riskunwind.html_report import html_report
from riskunwind.portfolio import Portfolio
from riskunwind.report import text_report

DATA = Path(__file__).resolve().parents[1] / "data"

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--panel", type=Path, required=True, help="same panel the books were built from")
    ap.add_argument("--portfolios", type=Path, nargs="*", default=None,
                    help="portfolio CSVs (default: all in data/portfolios)")
    ap.add_argument("--out-dir", type=Path, default=DATA / "reports")
    a = ap.parse_args()

    paths = a.portfolios or sorted((DATA / "portfolios").glob("*.csv"))
    if not paths:
        raise SystemExit("no portfolio CSVs found, run builds/build_portfolios.py first")

    market = MarketData.from_csv(a.panel)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        pf = Portfolio.from_csv(path)
        report = text_report(pf, market)
        txt, html = a.out_dir / f"{path.stem}.txt", a.out_dir / f"{path.stem}.html"
        txt.write_text(report)
        html.write_text(html_report(pf, market))
        print(report)
        print(f"wrote {txt}\nwrote {html}\n")


if __name__ == "__main__":
    main()
