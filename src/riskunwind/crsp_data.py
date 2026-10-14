"""
Takes in daily stock data (from WRDS)

Returns df with col: date, permno, ticker, siccd, price, ret, volume, shares_out
"""
from __future__ import annotations
from datetime import date, timedelta
import pandas as pd

COLS = ["date", "permno", "ticker", "siccd", "price", "ret", "volume", "shares_out"]

LEGACY_SQL = """
select a.date, a.permno, b.ticker, b.siccd, a.prc, a.ret, a.vol, a.shrout
from crsp.dsf a
join crsp.msenames b
  on a.permno = b.permno and b.namedt <= a.date and a.date <= b.nameendt
where a.date between %(start)s and %(end)s
  and b.shrcd in (10, 11) and b.exchcd in (1, 2, 3) 
  {permno_filter}
"""
# keeps shrcd  = 10/11 (common stock) and exchcd = 1/2/3 (NYSE, AMEX, NASDAQ)

# 2024 file pull
V2_SQL = """
select dlycaldt, permno, ticker, siccd, dlyprc, dlyret, dlyvol, shrout
from crsp.dsf_v2
where dlycaldt between %(start)s and %(end)s
  and securitytype = 'EQTY' and securitysubtype = 'COM' and sharetype = 'NS'
  and usincflg = 'Y' and issuertype in ('ACOR', 'CORP')
  and primaryexch in ('N', 'A', 'Q')
  {permno_filter}
"""

def connect():
    import wrds
    return wrds.Connection()

def detect_table(db) -> str:
    tables = set(db.list_tables(library="crsp"))
    for name in ("dsf_v2", "dsf"):
        if name in tables:
            return name
    raise RuntimeError("This WRDS account has neither crsp.dsf_v2 nor crsp.dsf.")

def normalize_legacy(raw: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(raw["date"]),
        "permno": raw["permno"].astype(int),
        "ticker": raw["ticker"],
        "siccd": pd.to_numeric(raw["siccd"], errors="coerce"),
        "price": raw["prc"].abs(), # negative = no trade, bid/ask midpoint
        "ret": raw["ret"].where(raw["ret"] >= -1), # missing ret are negative
        "volume": raw["vol"],
        "shares_out": raw["shrout"],  # thousands
    })[COLS]

def normalize_v2(raw: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(raw["dlycaldt"]),
        "permno": raw["permno"].astype(int),
        "ticker": raw["ticker"],
        "siccd": pd.to_numeric(raw["siccd"], errors="coerce"),
        "price": raw["dlyprc"].abs(),
        "ret": raw["dlyret"].where(raw["dlyret"] >= -1),
        "volume": raw["dlyvol"],
        "shares_out": raw["shrout"],  # in thousands
    })[COLS]

def run_sql(db, sql: str, params: dict) -> pd.DataFrame:
    """
    Opens WRDS connection 
    """
    conn = db.engine.raw_connection()
    # wrds needs SQLAlchemy 1.4, pandas 3 takes SQLAlchemy 2.x 
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        columns = [c[0] for c in cur.description]
        return pd.DataFrame.from_records(cur.fetchall(), columns=columns, coerce_float=True)
    finally:
        conn.close()

def query(db, table: str, start: date, end: date, permnos: list[int] | None = None) -> pd.DataFrame:
    if table == "dsf_v2":
        sql = V2_SQL
        normalize_func = normalize_v2
    else:
        sql = LEGACY_SQL
        normalize_func = normalize_legacy

    params = {"start": str(start), "end": str(end)}
    permno_filter = ""
    if permnos is not None:
        permno_col = "permno" if table == "dsf_v2" else "a.permno"
        permno_filter = f"and {permno_col} in %(permnos)s"
        params["permnos"] = tuple(permnos)
    raw = run_sql(db, sql.format(permno_filter=permno_filter), params)
    return normalize_func(raw)

def pull(db, start: date, end: date, n_stocks: int = 100) -> tuple[pd.DataFrame, str]:
    """
    Grab largest US common stocks by market cap daily from start to end
    """
    table = detect_table(db)

    # Finds closesl trading date before start for market cap calcs
    snap = query(db, table, start - timedelta(days=7), start)
    snap = snap[snap["date"] == snap["date"].max()]
    mktcap = snap["price"] * snap["shares_out"] * 1000
    permnos = snap.loc[mktcap.nlargest(n_stocks).index, "permno"].tolist()

    panel = query(db, table, start, end, permnos)
    panel = panel.drop_duplicates(["date", "permno"]).sort_values(["date", "permno"]).reset_index(drop=True)
    return panel, table


def summarize(panel: pd.DataFrame) -> str:
    return (
        f"{len(panel):,} rows | {panel['permno'].nunique()} stocks | {panel['date'].nunique()} trading days "
        f"| {panel['date'].min().date()} to {panel['date'].max().date()}\n"
        f"missing: price {panel['price'].isna().mean():.1%}, ret {panel['ret'].isna().mean():.1%}, "
        f"volume {panel['volume'].isna().mean():.1%}"
    )
