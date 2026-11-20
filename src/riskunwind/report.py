"""
Generates a plain-text risk report for one portfolio
- summary vs limits
- other metrics
- each stretch of days over a limit
"""
from __future__ import annotations
import pandas as pd
from riskunwind.config import Limits, Params
from riskunwind.market import MarketData
from riskunwind.metrics import daily_metrics, days_to_liquidate
from riskunwind.portfolio import Portfolio
from riskunwind.state import daily_state

# metric col, label, Limits field
LIMITED = [
    ("max_name", "Max stock weight", "single_name"),
    ("max_sector", "Max sector weight", "sector"),
    ("var", "1-day VaR (95%)", "var"),
    ("days_to_liquidate", "Days to liquidate", "days_to_liquidate"),
]

# metric col, label (no limit yet)
OTHER = [
    ("gross", "Gross exposure"),
    ("net", "Net exposure"),
    ("drawdown", "Drawdown"),
    ("expected_shortfall", "Exp. shortfall (95%)"),
    ("volatility", "1-day volatility"),
    ("cash_buffer", "Cash buffer"),
]

def format_to_report(col: str, x: float) -> str:
    if pd.isna(x):
        return "n/a"
    return f"{x:.2f}d" if col == "days_to_liquidate" else f"{x:.1%}"

def runs(over: pd.Series) -> list[pd.DatetimeIndex]:
    """Finds stretches of consecutive True days"""
    run_id = (over != over.shift()).cumsum()
    return [g.index for _, g in over[over].groupby(run_id[over])]

def text_report(portfolio: Portfolio, market: MarketData,
                limits: Limits = Limits(), params: Params = Params()) -> str:
    m = daily_metrics(portfolio, market, params)
    state = daily_state(portfolio, market)
    dtl = days_to_liquidate(portfolio, state, market, params)

    # which stock / sector drives the number on a given day
    def who(col: str, day) -> str:
        if col == "max_name":
            return market.ticker[state.weights.loc[day].abs().idxmax()]
        if col == "max_sector":
            return state.sector_weights.loc[day].abs().idxmax()
        if col == "days_to_liquidate":
            return market.ticker[dtl.loc[day].idxmax()]
        return ""

    start, end = m.index[0], m.index[-1]
    nav0, nav1 = m["nav"].iloc[0], m["nav"].iloc[-1]
    worst_dd = m["drawdown"].idxmax()
    lines = [
        f"RISK REPORT: {portfolio.name}",
        f"Period: {start.date()} to {end.date()} ({len(m)} trading days)",
        f"NAV: ${nav0:,.0f} -> ${nav1:,.0f} ({nav1 / nav0 - 1:+.1%})",
        f"Worst drawdown: {m['drawdown'].max():.1%} on {worst_dd.date()}",
        "",
        "LIMITS",
        f"{'':22}{'limit':>8}{'entry':>9}{'latest':>9}{'worst':>9}   days over",
    ]
    for col, label, field in LIMITED:
        limit = getattr(limits, field)
        over = m[col] > limit
        flag = "  <-- BREACH" if over.any() else ""
        lines.append(f"{label:22}{format_to_report(col, limit):>8}{format_to_report(col, m[col].iloc[0]):>9}{format_to_report(col, m[col].iloc[-1]):>9}"
                     f"{format_to_report(col, m[col].max()):>9}   {over.sum()} of {len(m)}{flag}")

    lines += ["", "OTHER METRICS (no limit yet)",
              f"{'':22}{'entry':>9}{'latest':>9}{'low':>9}{'high':>9}"]
    for col, label in OTHER:
        s = m[col]
        lines.append(f"{label:22}{format_to_report(col, s.iloc[0]):>9}{format_to_report(col, s.iloc[-1]):>9}{format_to_report(col, s.min()):>9}{format_to_report(col, s.max()):>9}")

    lines += ["", "BREACHES"]
    any_breach = False
    for col, label, field in LIMITED:
        limit = getattr(limits, field)
        for days in runs(m[col] > limit):
            any_breach = True
            worst = m.loc[days, col].idxmax()
            driver = who(col, worst)
            lines.append(f"- {label} over {format_to_report(col, limit)}: {days[0].date()} to {days[-1].date()} ({len(days)} day{'s' * (len(days) > 1)}), "
                         f"worst {format_to_report(col, m.at[worst, col])} on {worst.date()}" + (f" ({driver})" if driver else ""))
    if not any_breach:
        lines.append("None")

    lines += ["", "Notes:",
              "- Weights, VaR, shortfall, volatility, drawdown and cash buffer are fractions of NAV",
              f"- n/a = fewer than 20 days of return history; VaR uses up to {params.var_window} days",
              f"- Liquidity assumes trading at most {params.participation:.0%} of average daily volume"]
    return "\n".join(lines) + "\n"
