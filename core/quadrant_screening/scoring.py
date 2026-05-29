"""100点満点の4象限スコア（段階配点・信用・パターン重み・ファンダ4軸）。"""
from __future__ import annotations

from dataclasses import dataclass

from core.quadrant_screening.config import (
    MARGIN_RATIO_CROWDED,
    MARGIN_RATIO_NEUTRAL,
    MARGIN_RATIO_TIGHT,
    SCORE_FUNDAMENTAL_MAX,
    SCORE_MA25,
    SCORE_MA75,
    SCORE_MARGIN_MAX,
    SCORE_MAX,
    SCORE_SECTOR_MAX,
    SCORE_TECHNICAL_MAX,
    SCORE_VOL_SPIKE_MAX,
    SCORE_VOL_STRONG,
    SCORE_VOL_WEAK,
    SCORE_VOLUME_MAX,
    SECTOR_EXCESS_CAP_SHORT,
    SECTOR_EXCESS_PTS_PER_PCT,
    SECTOR_LONG_CONFIRM_BONUS,
    VOL_SPIKE_STRONG,
    VOL_SPIKE_WEAK,
)
from core.quadrant_screening.fundamentals import (
    FundamentalSnapshot,
    score_fundamental_total,
)
from core.quadrant_screening.margin import MarginSnapshot
from core.quadrant_screening.pattern_weights import score_patterns
from core.quadrant_screening.sector import SectorMomentum
from core.quadrant_screening.technical import TechnicalSnapshot


@dataclass
class ScoreBreakdown:
    total: float
    sector_pts: float
    volume_pts: float
    technical_pts: float
    fundamental_pts: float
    sector_label: str
    volume_spike_pts: float = 0.0
    margin_pts: float = 0.0
    ma_pts: float = 0.0
    pattern_pts: float = 0.0


def score_sector(sector: SectorMomentum | None) -> tuple[float, str]:
    """
    セクター0〜15点。
    短期超過リターンに比例（最大12）+ 中期もTOPIX超なら+3。
    """
    if sector is None:
        return 0.0, "—"
    excess = sector.excess_return_pct
    if excess <= 0:
        return 0.0, "悪"
    pts = min(SECTOR_EXCESS_CAP_SHORT, excess * SECTOR_EXCESS_PTS_PER_PCT)
    long_ex = sector.excess_return_long_pct
    if long_ex is not None and long_ex > 0:
        pts += SECTOR_LONG_CONFIRM_BONUS
    pts = min(float(SCORE_SECTOR_MAX), pts)
    if pts >= 10:
        label = "良"
    elif pts >= 5:
        label = "中立"
    else:
        label = "弱"
    return round(pts, 2), label


def score_volume_spike(tech: TechnicalSnapshot) -> float:
    if tech.vol_ratio >= VOL_SPIKE_STRONG:
        return float(SCORE_VOL_STRONG)
    if tech.vol_ratio >= VOL_SPIKE_WEAK:
        return float(SCORE_VOL_WEAK)
    return 0.0


def score_margin(margin: MarginSnapshot | None) -> float:
    """信用倍率（買残÷売残）。低いほど需給タイトで加点。"""
    if margin is None:
        return 0.0
    r = margin.margin_ratio
    if r <= MARGIN_RATIO_TIGHT:
        return float(SCORE_MARGIN_MAX)
    if r <= MARGIN_RATIO_NEUTRAL:
        return SCORE_MARGIN_MAX * 0.65
    if r <= MARGIN_RATIO_CROWDED:
        return SCORE_MARGIN_MAX * 0.25
    return 0.0


def score_volume(tech: TechnicalSnapshot, margin: MarginSnapshot | None) -> tuple[float, float, float]:
    spike = score_volume_spike(tech)
    margin_pts = score_margin(margin)
    total = min(float(SCORE_VOLUME_MAX), spike + margin_pts)
    return round(total, 2), round(spike, 2), round(margin_pts, 2)


def score_technical(tech: TechnicalSnapshot) -> tuple[float, float, float]:
    ma_pts = 0.0
    if tech.above_25ma:
        ma_pts += SCORE_MA25
    if tech.above_75ma:
        ma_pts += SCORE_MA75
    pattern_pts = score_patterns(tech.patterns)
    total = min(float(SCORE_TECHNICAL_MAX), ma_pts + pattern_pts)
    return round(total, 2), round(ma_pts, 2), round(pattern_pts, 2)


def compute_score(
    tech: TechnicalSnapshot,
    fund: FundamentalSnapshot,
    sector: SectorMomentum | None,
    sector_code: int | None = None,
    ticker: str | None = None,
    margin: MarginSnapshot | None = None,
) -> ScoreBreakdown:
    sector_pts, sector_label = score_sector(sector)
    volume_pts, vol_spike_pts, margin_pts = score_volume(tech, margin)
    technical_pts, ma_pts, pattern_pts = score_technical(tech)
    fundamental_pts = score_fundamental_total(
        fund, tech.price, sector_code=sector_code, ticker=ticker
    )

    total = min(
        float(SCORE_MAX),
        sector_pts + volume_pts + technical_pts + fundamental_pts,
    )
    return ScoreBreakdown(
        total=round(total, 1),
        sector_pts=sector_pts,
        volume_pts=volume_pts,
        technical_pts=technical_pts,
        fundamental_pts=fundamental_pts,
        sector_label=sector_label,
        volume_spike_pts=vol_spike_pts,
        margin_pts=margin_pts,
        ma_pts=ma_pts,
        pattern_pts=pattern_pts,
    )
