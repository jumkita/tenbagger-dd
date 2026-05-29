"""4象限スクリーニングの単体テスト。"""
from __future__ import annotations

import pandas as pd
from dataclasses import replace

from core.quadrant_screening.config import QUADRANT_MIN_SCORE_DEFAULT
from core.quadrant_screening.fundamentals import FundamentalSnapshot, eps_discount_pct
from core.quadrant_screening.scoring import compute_score
from core.quadrant_screening.sector import SectorMomentum
from core.quadrant_screening.technical import (
    analyze_technical,
    detect_buy_patterns,
    passes_primary_filter,
)
from core.quadrant_screening.ticker_utils import normalize_ticker


def test_normalize_ticker_fixes_duplicate_suffix():
    assert normalize_ticker("7063.T7063.T") == "7063.T"
    assert normalize_ticker("7203") == "7203.T"
    assert normalize_ticker("7203.T") == "7203.T"


def test_primary_filter_thresholds():
    assert passes_primary_filter(500.0, 300_000) is True
    assert passes_primary_filter(499.0, 300_000) is False
    assert passes_primary_filter(500.0, 299_999) is False


def test_scoring_prefers_volume_and_pattern():
    df = _sample_uptrend_df()
    tech = analyze_technical(df)
    assert tech is not None
    assert tech.above_75ma is True

    fund = FundamentalSnapshot(roe_pct=10.0, trailing_eps=100.0, trailing_pe=12.0)
    sector = SectorMomentum(sector_code=1, sector_return_pct=5.0, topix_return_pct=2.0)
    high = compute_score(tech, fund, sector)

    fund_low = FundamentalSnapshot(roe_pct=5.0, trailing_eps=None, trailing_pe=None, roe_is_default=True)
    sector_bad = SectorMomentum(sector_code=1, sector_return_pct=1.0, topix_return_pct=3.0)
    tech_flat = replace(tech, vol_ratio=1.0, patterns=[])
    low = compute_score(tech_flat, fund_low, sector_bad)

    assert high.total > low.total


def test_eps_discount_positive_when_cheap():
    assert eps_discount_pct(1000.0, 100.0, industry_per=15.0) == 50.0


def test_detect_engulfing_pattern():
    # 前日陰線を陽線が包む（stock-daytrade カスタム包み線と同条件）
    pair = pd.DataFrame(
        {
            "Open": [100.0, 88.0],
            "High": [101.0, 103.0],
            "Low": [89.0, 87.0],
            "Close": [90.0, 102.0],
            "Volume": [100_000, 100_000],
        }
    )
    df_long = pd.concat([pair] * 40, ignore_index=True)
    patterns = detect_buy_patterns(df_long)
    assert isinstance(patterns, list)
    assert "包み線" in patterns


def test_detect_spylrow_matches_stock_daytrade_custom():
    """下ヒゲがレンジの60%以上の陽線 → スパイクロー（stock-daytrade と同条件）。"""
    df = pd.DataFrame(
        {
            "Open": [100.0, 100.0],
            "High": [101.0, 101.0],
            "Low": [99.0, 98.4],
            "Close": [100.0, 100.9],
            "Volume": [100_000, 100_000],
        }
    )
    assert "スパイクロー" in detect_buy_patterns(df)


def test_three_down_gaps_matches_stock_daytrade():
    """連続で前バーの安値が翌バーの高値より上 → 三空叩き込み（最終行で3連）。"""
    df = pd.DataFrame(
        {
            "Open": [100.0, 95.0, 88.0, 78.0],
            "High": [105.0, 94.0, 84.0, 74.0],
            "Low": [100.0, 90.0, 80.0, 70.0],
            "Close": [104.0, 92.0, 82.0, 76.0],
            "Volume": [100_000] * 4,
        }
    )
    assert "三空叩き込み" in detect_buy_patterns(df)


def test_detect_buy_patterns_runs_full_stack():
    """本家相当の検出が例外なく完走する（TA-Lib 未導入環境でもカスタム等は動く）。"""
    df = _sample_uptrend_df()
    patterns = detect_buy_patterns(df)
    assert isinstance(patterns, list)


def test_quadrant_min_score_default_is_50():
    assert QUADRANT_MIN_SCORE_DEFAULT == 50.0


def _sample_uptrend_df() -> pd.DataFrame:
    n = 90
    close = [500 + i * 2 for i in range(n)]
    return pd.DataFrame(
        {
            "Open": [c - 1 for c in close],
            "High": [c + 2 for c in close],
            "Low": [c - 3 for c in close],
            "Close": close,
            "Volume": [400_000 if i == n - 1 else 300_000 for i in range(n)],
        }
    )
