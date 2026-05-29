"""一次フィルター・需給・75MA・買いパターン。"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from core.quadrant_screening.config import (
    MA_PERIOD,
    MA_PERIOD_SHORT,
    MIN_PRICE,
    MIN_VOL_20D,
    VOL_RATIO_LOOKBACK,
)

try:
    import talib

    _TALIB_AVAILABLE = True
except ImportError:
    talib = None  # type: ignore[misc, assignment]
    _TALIB_AVAILABLE = False


# 本家 `stock-daytrade/logic.py` の BUY_PATTERNS_TALIB と同順・同ラベル
BUY_PATTERNS_TALIB: list[tuple[str, str]] = [
    ("赤三兵", "CDL3WHITESOLDIERS"),
    ("明けの明星", "CDLMORNINGSTAR"),
    ("上げ三法", "CDLRISEFALL3METHODS"),
    ("抱きの本立ち", "CDLBELTHOLD"),
    ("陽のつつみ線", "CDLENGULFING"),
    ("はらみ線", "CDLHARAMI"),
    ("切り込み線", "CDLPIERCING"),
    ("陽のたすき線", "CDLTASUKIGAP"),
    ("ピンバー(ハンマー)", "CDLHAMMER"),
    ("逆ハンマー", "CDLINVERTEDHAMMER"),
    ("スラストアップ", "CDLTHRUSTING"),
    ("包み線", "CDLENGULFING"),
]


@dataclass
class TechnicalSnapshot:
    price: float
    vol_20d_avg: float
    vol_ratio: float
    ma25: float
    ma75: float
    above_25ma: bool
    above_75ma: bool
    patterns: list[str]
    atr14: float | None = None


def _atr(df: pd.DataFrame, period: int = 14) -> float | None:
    if len(df) < period + 1:
        return None
    h = df["High"].astype(float)
    l = df["Low"].astype(float)
    c = df["Close"].astype(float)
    tr = pd.concat([(h - l), (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    val = tr.iloc[-period:].mean()
    return float(val) if pd.notna(val) else None


def passes_primary_filter(price: float, vol_20d: float) -> bool:
    return price >= MIN_PRICE and vol_20d >= MIN_VOL_20D


def _dedupe_preserve(names: list[str]) -> list[str]:
    """同一ラベルの二重付与（本家と同様に起こり得る）を表示用に1回にまとめる。"""
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


def _talib_buy_at_last(df: pd.DataFrame, i: int) -> list[str]:
    """最終行で TA-Lib 買いシグナル（>0）を拾う。未インストール時は空。"""
    if not _TALIB_AVAILABLE or talib is None or i < 0:
        return []
    out: list[str] = []
    o = df["Open"].astype(float).values
    h = df["High"].astype(float).values
    l_ = df["Low"].astype(float).values
    c = df["Close"].astype(float).values
    for name_ja, fname in BUY_PATTERNS_TALIB:
        func = getattr(talib, fname, None)
        if func is None:
            continue
        try:
            res = func(o, h, l_, c)
            if res is not None and len(res) > i and float(res[i]) > 0:
                out.append(name_ja)
        except Exception:
            continue
    return out


# --- stock-daytrade `logic.py` の _custom_buy_patterns と同一式（最終行のみ） ---


def _sd_body(r: pd.Series) -> float:
    return abs(float(r["Close"]) - float(r["Open"]))


def _sd_range_hl(r: pd.Series) -> float:
    return float(r["High"]) - float(r["Low"])


def _sd_lower_shadow(r: pd.Series) -> float:
    return min(float(r["Open"]), float(r["Close"])) - float(r["Low"])


def _sd_upper_shadow(r: pd.Series) -> float:
    return float(r["High"]) - max(float(r["Open"]), float(r["Close"]))


def _sd_bull(r: pd.Series) -> bool:
    return float(r["Close"]) > float(r["Open"])


def _sd_bear(r: pd.Series) -> bool:
    return float(r["Open"]) > float(r["Close"])


def _sd_body_is_tiny(r: pd.Series) -> bool:
    rng = _sd_range_hl(r)
    if rng <= 1e-10:
        return True
    return _sd_body(r) < rng * 0.1


def _three_down_gaps_at(df: pd.DataFrame, i: int) -> bool:
    """stock-daytrade `detect_all_patterns` の三空叩き込みループと同趣旨。"""
    if i < 3:
        return False
    gaps = 0
    for k in range(i, i - 3, -1):
        if k < 1:
            break
        curr, prev = df.iloc[k], df.iloc[k - 1]
        if float(prev["Low"]) > float(curr["High"]):
            gaps += 1
        else:
            break
    return gaps >= 3


def _custom_buy_at_last(df: pd.DataFrame, i: int) -> list[str]:
    r0 = df.iloc[i]
    r1 = df.iloc[i - 1]
    out: list[str] = []

    body0 = _sd_body(r0)
    body1 = _sd_body(r1)
    range0 = _sd_range_hl(r0)
    range1 = _sd_range_hl(r1)
    ls0 = _sd_lower_shadow(r0)
    ls1 = _sd_lower_shadow(r1)
    us0 = _sd_upper_shadow(r0)

    if range0 > 0 and range1 > 0 and ls0 >= body0 * 2 and ls1 >= body1 * 2:
        out.append("二本たくり線")
    if _sd_bear(r1) and _sd_bull(r0) and float(r0["Close"]) > float(r1["Close"]):
        out.append("陰線後の陽線")
    if range0 > 0 and _sd_body_is_tiny(r0) and ls0 > body0 * 2 and us0 < ls0:
        out.append("ピンバー")
    if _sd_bull(r0) and range0 > 0 and ls0 >= range0 * 0.6:
        out.append("スパイクロー")
    if i >= 5 and _sd_bull(r0):
        prev_low = min(float(df.iloc[k]["Low"]) for k in range(i - 5, i))
        if float(r0["Low"]) <= prev_low and float(r0["Close"]) > float(df.iloc[i - 1]["Close"]):
            out.append("リバーサルロー")
    if range1 > 0 and float(r0["High"]) < float(r1["High"]) and float(r0["Low"]) > float(r1["Low"]):
        out.append("インサイドバー")
    if body1 > 0 and _sd_bull(r0) and float(r0["Open"]) < float(r1["Close"]) and float(r0["Close"]) > float(r1["Open"]):
        out.append("包み線")
    return out


def detect_buy_patterns(df: pd.DataFrame) -> list[str]:
    """直近1本の買いパターン名（本家 ``stock-daytrade/logic.detect_all_patterns`` の買い系に準拠）。

    付与順: ``BUY_PATTERNS_TALIB`` → ``_custom_buy_patterns`` 相当 →
    ``signal_scanner.CandlePatterns`` の買い3種 → 三空叩き込み。
    TA-Lib 未インストール時は TA-Lib 分をスキップ（他は従来どおり）。

    同一ラベルが複数ルートで立つ場合は ``_dedupe_preserve`` で1本化する。
    """
    if df is None or len(df) < 2:
        return []
    i = len(df) - 1
    found: list[str] = []

    found.extend(_talib_buy_at_last(df, i))
    found.extend(_custom_buy_at_last(df, i))

    try:
        from core.quadrant_screening.stock_daytrade_candle_patterns import CandlePatterns

        cp = CandlePatterns(df)
        if cp.is_akenomyojo(i):
            found.append("明けの明星")
        if cp.is_aka_sanpei(i):
            found.append("赤三兵")
        if cp.is_nihon_takuri(i):
            found.append("二本たくり線")
    except Exception:
        pass

    if i >= 3 and _three_down_gaps_at(df, i):
        found.append("三空叩き込み")

    return _dedupe_preserve(found)


def analyze_technical(df: pd.DataFrame) -> TechnicalSnapshot | None:
    min_len = max(MA_PERIOD, MA_PERIOD_SHORT)
    if df is None or len(df) < min_len:
        return None
    try:
        close = float(df["Close"].iloc[-1])
        vol20 = float(df["Volume"].iloc[-20:].mean())
        vol5 = float(df["Volume"].iloc[-VOL_RATIO_LOOKBACK:].mean())
        vol_today = float(df["Volume"].iloc[-1])
        ma25 = float(df["Close"].iloc[-MA_PERIOD_SHORT:].mean())
        ma75 = float(df["Close"].iloc[-MA_PERIOD:].mean())
    except (TypeError, ValueError):
        return None

    if close <= 0 or pd.isna(vol20) or pd.isna(ma75) or pd.isna(ma25):
        return None

    vol_ratio = vol_today / vol5 if vol5 > 0 else 0.0
    patterns = detect_buy_patterns(df)

    return TechnicalSnapshot(
        price=close,
        vol_20d_avg=vol20,
        vol_ratio=vol_ratio,
        ma25=ma25,
        ma75=ma75,
        above_25ma=close > ma25,
        above_75ma=close > ma75,
        patterns=patterns,
        atr14=_atr(df),
    )


def compute_tp_sl(price: float, atr: float | None, rr: float = 2.0) -> tuple[float, float]:
    """SL=2ATRまたは3%、TP=リスクリワード2倍。"""
    if price <= 0:
        return price, price
    risk = (2.0 * atr) if atr and atr > 0 else price * 0.03
    sl = max(price - risk, price * 0.92)
    tp = price + (price - sl) * rr
    return round(tp, 2), round(sl, 2)
