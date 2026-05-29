from __future__ import annotations

from typing import Iterable, Dict, Any, Optional

import pandas as pd
import yfinance as yf

_usdjpy: Optional[float] = None


def _get_usdjpy() -> float:
    global _usdjpy
    if _usdjpy is not None and _usdjpy > 0:
        return _usdjpy
    try:
        t = yf.Ticker("JPY=X")
        hist = t.history(period="1d")
        if hist is not None and not hist.empty:
            _usdjpy = float(hist["Close"].iloc[-1])
        else:
            _usdjpy = 150.0
    except Exception:
        _usdjpy = 150.0
    return _usdjpy


def fetch_market_data_for_ticker(ticker: str) -> Dict[str, Any]:
    """
    単一銘柄の時価総額（円→億円）と直近2期売上高を取得。
    通貨がUSDの場合はUSD/JPYで円換算し、時価総額は億円で market_cap_oku に格納する。
    """
    ticker_obj = yf.Ticker(ticker)
    info = ticker_obj.info
    currency = (info.get("currency") or "JPY").upper()
    market_cap_raw = info.get("marketCap")
    financials = ticker_obj.financials

    revenue_latest = None
    revenue_prev = None
    if isinstance(financials, pd.DataFrame) and "Total Revenue" in financials.index:
        revenues = financials.loc["Total Revenue"].dropna()
        if len(revenues) >= 2:
            revenue_latest = float(revenues.iloc[0])
            revenue_prev = float(revenues.iloc[1])

    market_cap_jpy: Optional[float] = None
    if market_cap_raw is not None and market_cap_raw > 0:
        if currency == "USD":
            market_cap_jpy = market_cap_raw * _get_usdjpy()
        else:
            market_cap_jpy = float(market_cap_raw)
    market_cap_oku = (market_cap_jpy / 1e8) if market_cap_jpy else None

    revenue_latest_oku = None
    revenue_prev_oku = None
    if revenue_latest is not None and revenue_prev is not None:
        if currency == "USD":
            rate = _get_usdjpy()
            revenue_latest_oku = revenue_latest * rate / 1e8
            revenue_prev_oku = revenue_prev * rate / 1e8
        else:
            revenue_latest_oku = revenue_latest / 1e8
            revenue_prev_oku = revenue_prev / 1e8

    return {
        "ticker": ticker,
        "market_cap": market_cap_raw,
        "market_cap_jpy": market_cap_jpy,
        "market_cap_oku": market_cap_oku,
        "revenue_latest": revenue_latest,
        "revenue_prev": revenue_prev,
        "revenue_latest_oku": revenue_latest_oku,
        "revenue_prev_oku": revenue_prev_oku,
    }


def build_market_data(tickers: Iterable[str]) -> pd.DataFrame:
    """複数銘柄についてマーケットデータDataFrameを構築。"""
    rows = [fetch_market_data_for_ticker(t) for t in tickers]
    return pd.DataFrame(rows)

