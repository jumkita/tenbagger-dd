"""17業種ETF vs TOPIX のセクターモメンタム。"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import yfinance as yf

from core.quadrant_screening.config import (
    SECTOR_ETF_BY_CODE,
    SECTOR_MOMENTUM_DAYS,
    SECTOR_MOMENTUM_DAYS_LONG,
    TOPIX_ETF,
)
from core.quadrant_screening.market_data import normalize_ohlcv


@dataclass(frozen=True)
class SectorMomentum:
    sector_code: int
    sector_return_pct: float
    topix_return_pct: float
    sector_return_long_pct: float | None = None
    topix_return_long_pct: float | None = None

    @property
    def excess_return_pct(self) -> float:
        return self.sector_return_pct - self.topix_return_pct

    @property
    def excess_return_long_pct(self) -> float | None:
        if self.sector_return_long_pct is None or self.topix_return_long_pct is None:
            return None
        return self.sector_return_long_pct - self.topix_return_long_pct

    @property
    def outperforms_topix(self) -> bool:
        return self.excess_return_pct > 0


def _return_over_days(df: pd.DataFrame, days: int) -> float | None:
    if df.empty or len(df) < days + 1 or "Close" not in df.columns:
        return None
    close = df["Close"].astype(float)
    start = float(close.iloc[-days - 1])
    end = float(close.iloc[-1])
    if start <= 0:
        return None
    return (end - start) / start * 100.0


def load_sector_momentum(
    days: int = SECTOR_MOMENTUM_DAYS,
    days_long: int = SECTOR_MOMENTUM_DAYS_LONG,
) -> tuple[float | None, dict[int, SectorMomentum]]:
    """
    TOPIX ETF と17業種ETFの直近・中期騰落率を一括取得。
    Returns: (topix_return_pct, {sector_code: SectorMomentum})
    """
    tickers = [TOPIX_ETF] + list(SECTOR_ETF_BY_CODE.values())
    try:
        raw = yf.download(
            tickers,
            period="6mo",
            interval="1d",
            group_by="ticker",
            progress=False,
            auto_adjust=True,
            threads=True,
        )
    except Exception:
        return None, {}

    etf_to_sector = {v: k for k, v in SECTOR_ETF_BY_CODE.items()}
    returns_short: dict[str, float | None] = {}
    returns_long: dict[str, float | None] = {}

    if len(tickers) == 1:
        norm = normalize_ohlcv(raw)
        returns_short[tickers[0]] = _return_over_days(norm, days)
        returns_long[tickers[0]] = _return_over_days(norm, days_long)
    else:
        for t in tickers:
            try:
                sub = raw[t].dropna(how="all")
                norm = normalize_ohlcv(sub)
                returns_short[t] = _return_over_days(norm, days)
                returns_long[t] = _return_over_days(norm, days_long)
            except Exception:
                returns_short[t] = None
                returns_long[t] = None

    topix_ret = returns_short.get(TOPIX_ETF)
    topix_long = returns_long.get(TOPIX_ETF)
    out: dict[int, SectorMomentum] = {}
    for etf, sec_code in etf_to_sector.items():
        sec_ret = returns_short.get(etf)
        if sec_ret is None or topix_ret is None:
            continue
        out[sec_code] = SectorMomentum(
            sector_code=sec_code,
            sector_return_pct=sec_ret,
            topix_return_pct=topix_ret,
            sector_return_long_pct=returns_long.get(etf),
            topix_return_long_pct=topix_long,
        )
    return topix_ret, out
