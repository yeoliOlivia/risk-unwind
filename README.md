# risk-unwind

Typed exception handling for portfolio risk management (CPSC 4900). See `proposal.tex`.

Built so far: data ingestion (S0 input side), the state layer (S1), the exception
hierarchy, and stub monitors (S2). Dispatch, netting and repair are not started.

## Setup

```bash
uv venv && uv pip install -e ".[dev,wrds]"
.venv/bin/pytest
```

## Data

CRSP is licensed: `data/raw/` is gitignored, never commit it.

```bash
# needs a WRDS login (the wrds package prompts for it; credentials are never stored here)
.venv/bin/python scripts/pull_crsp.py --tag covid2020 --start 2020-02-03 --end 2020-05-29
.venv/bin/python scripts/build_portfolios.py --panel data/raw/crsp_covid2020.csv.gz
.venv/bin/python scripts/run_state.py --panel data/raw/crsp_covid2020.csv.gz --portfolio data/portfolios/cascade.csv
```

No WRDS yet? `scripts/make_synthetic.py` writes a same-schema fake panel to `data/raw/crsp_synthetic.csv.gz`.

## Layout

| Path | What |
|---|---|
| `src/riskunwind/crsp.py` | WRDS pull; detects `dsf_v2` vs legacy `dsf`; normalises both to one schema |
| `src/riskunwind/market.py` | `MarketData`: panel as date x permno matrices (the S0 fault-injection hook) |
| `src/riskunwind/portfolio.py`, `builders.py` | buy-and-hold long/short book; baseline / cascade / highvol builders |
| `src/riskunwind/state.py` | S1: weights, gross/net, sector weights, ADV, days-to-liquidate, 1d historical VaR |
| `src/riskunwind/exceptions.py`, `monitors.py` | the hierarchy; threshold monitors that return typed breaches |
| `src/riskunwind/config.py` | `Limits` and `Params`: every threshold is a placeholder to tune |

## Conventions

- Weights are fractions of NAV; `NAV = cash + sum(shares * price)`; shorts have negative shares.
- Sector limit applies to |net| sector weight. Sectors come from SIC (`sectors.py`).
- Days-to-liquidate = |shares| / (participation x 20d ADV). VaR = historical simulation of today's weights over the last 250 days of returns.
