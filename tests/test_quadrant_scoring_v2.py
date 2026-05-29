"""4象限スコア v2（段階配点・信用・パターン重み・ファンダ4軸）。"""
from __future__ import annotations

import pandas as pd
from dataclasses import replace

from core.quadrant_screening.config import SCORE_MAX, SCORE_PATTERN_MAX, SCORE_SECTOR_MAX
from core.quadrant_screening.fundamentals import FundamentalSnapshot, score_fundamental_total
from core.quadrant_screening.margin import MarginSnapshot
from core.quadrant_screening.pattern_weights import (
    canonical_pattern_name,
    effective_pattern_weight,
    score_patterns,
)
from core.quadrant_screening.scoring import (
    compute_score,
    score_margin,
    score_sector,
    score_technical,
    score_volume_spike,
)
from core.quadrant_screening.sector import SectorMomentum
from core.quadrant_screening.technical import TechnicalSnapshot, analyze_technical


def _tech(**kwargs) -> TechnicalSnapshot:
    base = TechnicalSnapshot(
        price=1000.0,
        vol_20d_avg=400_000.0,
        vol_ratio=1.3,
        ma25=950.0,
        ma75=900.0,
        above_25ma=True,
        above_75ma=True,
        patterns=["包み線"],
    )
    return replace(base, **kwargs)


def test_sector_graduated_by_excess():
    weak, _ = score_sector(
        SectorMomentum(1, sector_return_pct=2.1, topix_return_pct=2.0)
    )
    strong, label = score_sector(
        SectorMomentum(
            1,
            sector_return_pct=8.0,
            topix_return_pct=2.0,
            sector_return_long_pct=10.0,
            topix_return_long_pct=3.0,
        )
    )
    bad, bad_label = score_sector(
        SectorMomentum(1, sector_return_pct=1.0, topix_return_pct=3.0)
    )
    assert bad == 0.0 and bad_label == "悪"
    assert weak < strong <= SCORE_SECTOR_MAX
    assert label == "良"


def test_volume_spike_tiers():
    assert score_volume_spike(_tech(vol_ratio=1.0)) == 0.0
    weak = score_volume_spike(_tech(vol_ratio=1.16))
    strong = score_volume_spike(_tech(vol_ratio=1.3))
    assert weak > 0 < strong
    assert weak < strong


def test_margin_tight_scores_higher():
    tight = score_margin(MarginSnapshot(margin_ratio=0.8))
    crowded = score_margin(MarginSnapshot(margin_ratio=10.0))
    assert tight > crowded
    assert score_margin(None) == 0.0


def test_technical_ma_and_pattern():
    total, ma_pts, pat_pts = score_technical(_tech())
    assert ma_pts == 15
    assert pat_pts > 0
    assert total <= 40
    no_pat = score_technical(_tech(patterns=[]))[0]
    assert no_pat < total


def test_pattern_canonical_alias():
    assert canonical_pattern_name("ピンバー") == "ハンマー"
    assert canonical_pattern_name("包み線") == "包み線"


def test_pattern_weight_shrinks_with_low_n():
    w_default = effective_pattern_weight("存在しないパターン")
    w_known = effective_pattern_weight("包み線")
    assert 0.3 < w_default <= 1.0
    assert w_known > 0.5
    assert score_patterns(["包み線"]) <= SCORE_PATTERN_MAX


def test_fundamental_four_axes():
    fund = FundamentalSnapshot(
        roe_pct=15.0,
        trailing_eps=50.0,
        trailing_pe=10.0,
        growth_pct=25.0,
        roe_is_default=False,
        operating_margin_pct=12.0,
        debt_to_equity=0.4,
    )
    pts = score_fundamental_total(fund, 500.0, sector_code=9, ticker="7203.T")
    assert pts > 10


def test_compute_score_high_beats_low():
    fund = FundamentalSnapshot(
        roe_pct=15.0,
        trailing_eps=50.0,
        trailing_pe=10.0,
        growth_pct=20.0,
        roe_is_default=False,
        debt_to_equity=0.5,
    )
    sector = SectorMomentum(
        1,
        sector_return_pct=6.0,
        topix_return_pct=1.0,
        sector_return_long_pct=12.0,
        topix_return_long_pct=2.0,
    )
    high = compute_score(
        _tech(vol_ratio=1.3, patterns=["包み線"]),
        fund,
        sector,
        margin=MarginSnapshot(margin_ratio=0.9),
    )
    low = compute_score(
        _tech(vol_ratio=1.0, patterns=[], above_25ma=False),
        FundamentalSnapshot(roe_pct=5.0, trailing_eps=None, trailing_pe=None, roe_is_default=True),
        SectorMomentum(1, 1.0, 3.0),
        margin=None,
    )
    assert high.total > low.total
    assert high.total <= SCORE_MAX


def test_analyze_technical_includes_ma25():
    n = 90
    close = [500 + i * 2 for i in range(n)]
    df = pd.DataFrame(
        {
            "Open": [c - 1 for c in close],
            "High": [c + 2 for c in close],
            "Low": [c - 3 for c in close],
            "Close": close,
            "Volume": [300_000] * n,
        }
    )
    tech = analyze_technical(df)
    assert tech is not None
    assert tech.above_25ma is True
    assert tech.above_75ma is True
