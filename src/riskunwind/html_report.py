"""
Generates a one-file HTML risk report for one portfolio
- NAV headline and chart
- key risk statistics vs limits
- limit charts, breaches, daily table

Charts are matplotlib PNGs embedded in the page (no extra files)
"""
from __future__ import annotations
import base64
import io
import matplotlib.dates as mdates
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, PercentFormatter
from riskunwind.config import Limits, Params
from riskunwind.market import MarketData
from riskunwind.metrics import daily_metrics
from riskunwind.portfolio import Portfolio
from riskunwind.report import LIMITED, OTHER, format_to_report as fmt, runs
from riskunwind.state import daily_state

SHOW_DAYS = 10  # daily rows shown before "Show all"

INK, MUTED, RULE = "#0f0f14", "#5b636a", "#e0e4e9"
RED, GREEN, LINE = "#eb0f29", "#008a3c", "#2c2c2c"
SMALL_WORDS = {"a", "an", "and", "of", "the", "to", "vs", "per"}

def title(text: str) -> str:
    """Title Case, small words stay lower"""
    words = text.split()
    return " ".join(w if (i and w.lower() in SMALL_WORDS) or not w[0].isalpha() else w[0].upper() + w[1:]
                    for i, w in enumerate(words))

def day_str(d: pd.Timestamp, year: bool = False) -> str:
    return f"{d:%b} {d.day}" + (f", {d.year}" if year else "")

def to_png(fig: Figure) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=170, bbox_inches="tight", facecolor="white")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

def flat_axes(ax, yfmt) -> None:
    """No box, y axis on the right, dotted grid"""
    for side in ("top", "left", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(RULE)
    ax.yaxis.tick_right()
    ax.tick_params(length=0, pad=6, colors=MUTED, labelsize=8.5)
    ax.grid(axis="y", color=RULE, lw=0.7, ls=(0, (2, 2)))
    ax.set_axisbelow(True)
    ax.yaxis.set_major_formatter(yfmt)
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0, interval=2))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: day_str(mdates.num2date(x))))

def nav_chart(m: pd.DataFrame) -> str:
    nav = m["nav"] / 1e6
    color = GREEN if nav.iloc[-1] >= nav.iloc[0] else RED
    floor = nav.min() * 0.98
    fig = Figure(figsize=(9.6, 3.2))
    ax = fig.subplots()
    ax.plot(nav.index, nav, color=color, lw=1.4)
    ax.fill_between(nav.index, nav, floor, color=color, alpha=0.07, lw=0)
    ax.axhline(nav.iloc[0], color=MUTED, lw=0.8, ls=(0, (1, 2)))  # starting NAV
    ax.set_ylim(floor, nav.max() * 1.01)
    ax.set_xlim(nav.index[0], nav.index[-1])
    flat_axes(ax, FuncFormatter(lambda v, _: f"{v:.2f}M"))
    return to_png(fig)

def limits_chart(m: pd.DataFrame, limits: Limits) -> str:
    """2x2: each limited metric, red line = limit, shaded = days over"""
    fig = Figure(figsize=(9.6, 5.2))
    axes = fig.subplots(2, 2, sharex=True)
    for ax, (col, label, field) in zip(axes.flat, LIMITED):
        limit, s = getattr(limits, field), m[col]
        for days in runs(s > limit):
            half = pd.Timedelta(hours=12)
            ax.axvspan(days[0] - half, days[-1] + half, color=RED, alpha=0.08, lw=0)
        ax.plot(s.index, s, color=LINE, lw=1.1)
        ax.axhline(limit, color=RED, lw=0.9)
        ax.set_ylim(0, max(s.max(), limit) * 1.18)
        ax.set_xlim(m.index[0], m.index[-1])
        ax.set_title(title(label), loc="left", fontsize=10, color=INK, fontweight="bold", pad=6)
        days_fmt = FuncFormatter(lambda v, _: f"{v:.0f}d")
        flat_axes(ax, days_fmt if col == "days_to_liquidate" else PercentFormatter(1.0, decimals=None))
    fig.tight_layout(w_pad=3, h_pad=2.5)
    return to_png(fig)

def html_report(portfolio: Portfolio, market: MarketData,
                limits: Limits = Limits(), params: Params = Params()) -> str:
    m = daily_metrics(portfolio, market, params)
    state = daily_state(portfolio, market)

    def driver(col: str, day) -> str:
        if col == "max_name":
            return market.ticker[state.weights.loc[day].abs().idxmax()]
        if col == "max_sector":
            return state.sector_weights.loc[day].abs().idxmax()
        return "-"

    # key stats: limited metrics (latest / limit, days over), then the rest
    stats = []
    for col, label, field in LIMITED:
        limit, latest = getattr(limits, field), m[col].iloc[-1]
        n_over = int((m[col] > limit).sum())
        red = " class=neg" if latest > limit else ""
        stats.append((label, f"<span{red}>{fmt(col, latest)}</span> <span class=lim>/ {fmt(col, limit)}</span>"))
        stats.append((f"{label}: days over", f"<span{' class=neg' if n_over else ''}>{n_over} / {len(m)}</span>"))
    for col, label in OTHER:
        stats.append((label, fmt(col, m[col].iloc[-1])))
    worst_dd = m["drawdown"].idxmax()
    stats.append(("Worst drawdown", f"{m['drawdown'].max():.1%} <span class=lim>{day_str(worst_dd)}</span>"))
    shares = portfolio.positions["shares"]
    stats.append(("Positions", f"{(shares > 0).sum()} long / {(shares < 0).sum()} short"))
    half = (len(stats) + 1) // 2
    stat_cols = ["".join(f"<tr><td>{a}</td><td class=v>{b}</td></tr>" for a, b in part)
                 for part in (stats[:half], stats[half:])]

    breach_rows = ""
    for col, label, field in LIMITED:
        for days in runs(m[col] > getattr(limits, field)):
            worst = m.loc[days, col].idxmax()
            dates = day_str(days[0]) + (f" – {day_str(days[-1])}" if len(days) > 1 else "")
            breach_rows += (f"<tr><td>{label}</td><td>{dates}</td><td class=n>{len(days)}</td>"
                            f"<td class='n neg'>{fmt(col, m.at[worst, col])}</td><td>{driver(col, worst)}</td></tr>")
    breach_rows = breach_rows or "<tr><td colspan=5>None</td></tr>"

    # daily table, newest first; rows past SHOW_DAYS hidden until "Show all"
    daily = m.assign(change=m["nav"].pct_change().fillna(0.0)).iloc[::-1]
    daily_rows = ""
    for i, (day, r) in enumerate(daily.iterrows()):
        hidden = " class=more" if i >= SHOW_DAYS else ""
        sign = "neg" if r["change"] < 0 else "pos"
        daily_rows += (f"<tr{hidden}><td>{day_str(day, year=True)}</td><td class=n>{r['nav']:,.0f}</td>"
                       f"<td class='n {sign}'>{r['change']:+.2%}</td><td class=n>{r['gross']:.1%}</td>"
                       f"<td class=n>{r['net']:.1%}</td><td class=n>{fmt('var', r['var'])}</td>"
                       f"<td class=n>{r['drawdown']:.1%}</td></tr>")
    show_all = f"Show all {len(m)} days"
    button = (f"<button id=more onclick=\"document.body.classList.toggle('all');"
              f"this.textContent=document.body.classList.contains('all')?'Show less':'{show_all}'\">{show_all}</button>"
              if len(m) > SHOW_DAYS else "")

    nav0, nav1 = m["nav"].iloc[0], m["nav"].iloc[-1]
    up = "pos" if nav1 >= nav0 else "neg"
    name = title(portfolio.name)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name} Risk</title>
<style>{CSS}</style></head>
<body><main id="top">
<div class="crumb">Long/short equity · ${portfolio.capital / 1e6:,.0f}M · {len(portfolio.positions)} positions</div>
<h1>{name}</h1>
<div><span class="px">${nav1:,.0f}</span><span class="chg {up}">{nav1 - nav0:+,.0f} ({nav1 / nav0 - 1:+.2%})</span></div>
<div class="asof">NAV as of {day_str(m.index[-1], year=True)} · since entry {day_str(m.index[0], year=True)}</div>
<nav><a class="on" href="#top">Summary</a><a href="#limits">Limits</a><a href="#breaches">Breaches</a><a href="#daily">Daily</a></nav>
<img src="{nav_chart(m)}" alt="NAV since entry">
<h2>Key Risk Statistics</h2>
<div class="stats"><table>{stat_cols[0]}</table><table>{stat_cols[1]}</table></div>
<h2 id="limits">Limits</h2>
<img src="{limits_chart(m, limits)}" alt="Limited metrics over time; red line is the limit, shaded days are over it">
<h2 id="breaches">Breaches</h2>
<div class="scroll"><table class="grid"><tr><th>Limit</th><th>Dates</th><th class=n>Days</th><th class=n>Worst</th><th>Driver</th></tr>{breach_rows}</table></div>
<h2 id="daily">Daily</h2>
<div class="scroll"><table class="grid"><tr><th>Date</th><th class=n>NAV</th><th class=n>Change</th><th class=n>Gross</th><th class=n>Net</th><th class=n>VaR</th><th class=n>Drawdown</th></tr>{daily_rows}</table></div>
{button}
<div class="foot">Values in % are fractions of NAV. VaR and shortfall: 1-day, {params.var_confidence:.0%}, historical.
Liquidity: at most {params.participation:.0%} of average daily volume.</div>
</main></body></html>
"""

CSS = f"""
*{{border-radius:0;box-sizing:border-box}}
body{{margin:0;background:#fff;color:{INK};font:13px/1.4 Helvetica,Arial,sans-serif}}
main{{max-width:1000px;margin:0 auto;padding:20px 16px 40px}}
.crumb{{color:{MUTED};font-size:12px}}
h1{{font-size:24px;font-weight:700;margin:2px 0 10px}}
h2{{font-size:16px;font-weight:700;margin:26px 0 6px}}
.px{{font-size:34px;font-weight:700;letter-spacing:-.5px}}
.chg{{font-size:20px;font-weight:600;margin-left:8px}}
.asof{{color:{MUTED};font-size:12px;margin:2px 0 14px}}
.neg{{color:{RED}}} .pos{{color:{GREEN}}} .lim{{color:{MUTED};font-weight:400}}
nav{{border-bottom:1px solid {RULE};margin-bottom:12px}}
nav a{{display:inline-block;padding:8px 0;margin-right:22px;color:{MUTED};font-weight:600;text-decoration:none}}
nav a.on{{color:{INK};border-bottom:3px solid {INK}}}
img{{width:100%;height:auto;display:block}}
.stats{{display:grid;grid-template-columns:1fr 1fr;column-gap:40px}}
@media(max-width:640px){{.stats{{grid-template-columns:1fr}}}}
table{{border-collapse:collapse;width:100%}}
td,th{{padding:7px 0;border-bottom:1px solid {RULE};white-space:nowrap}}
.stats td{{color:{MUTED}}} .stats td.v{{text-align:right;color:{INK};font-weight:700}}
.grid th{{font-size:11px;color:{MUTED};font-weight:400;text-align:left;text-transform:uppercase}}
.grid th.n,.grid td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.grid td+td,.grid th+th{{padding-left:14px}}
.scroll{{overflow-x:auto}}
tr.more{{display:none}} body.all tr.more{{display:table-row}}
#more{{margin-top:10px;background:#fff;border:1px solid {INK};color:{INK};font:600 12px Helvetica,Arial,sans-serif;padding:7px 14px;cursor:pointer}}
#more:hover{{background:{INK};color:#fff}}
.foot{{color:{MUTED};font-size:11px;margin-top:18px}}
"""
