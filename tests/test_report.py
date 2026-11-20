"""
Testing the text risk report
"""
import pandas as pd
# importing from other files
from riskunwind.report import runs, text_report

# Decision of what type of tests to create were done in conjunction/consultation with Claude.
def test_runs_groups_consecutive_days():
    days = pd.bdate_range("2020-02-03", periods=6)
    over = pd.Series([True, True, False, True, False, True], index=days)
    assert [len(r) for r in runs(over)] == [2, 1, 1]
    assert runs(over)[0][0] == days[0]

def test_cascade_report_shows_both_breaches(cascade, market):
    report = text_report(cascade, market)
    assert report.startswith("RISK REPORT: cascade")
    assert "- Max stock weight over 5.0%" in report
    assert "- Max sector weight over 25.0%" in report
    assert "Semiconductors" in report  # names the sector driving the breach

def test_report_lists_every_metric(baseline, market):
    report = text_report(baseline, market)
    for label in ["1-day VaR (95%)", "Days to liquidate", "Gross exposure", "Drawdown",
                  "Exp. shortfall (95%)", "1-day volatility", "Cash buffer"]:
        assert label in report
