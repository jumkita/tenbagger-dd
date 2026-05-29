"""買いパターンの検証ベース重み（JSON + ベイズ縮小）。"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.quadrant_screening.config import (
    PATTERN_WEIGHT_PRIOR,
    PATTERN_WEIGHT_PRIOR_N,
    SCORE_PATTERN_MAX,
)

_WEIGHTS_PATH = Path(__file__).resolve().parent / "data" / "pattern_weights.json"

# stock-daytrade の pattern_name / TA-Lib 表示名 → 重みJSONのキー
SIGNAL_TO_QUADRANT_PATTERN: dict[str, str] = {
    "ピンバー": "ハンマー",
    "二本たくり線": "たくり線",
    "包み線": "包み線",
    "陰線後の陽線": "包み線",
    "リバーサルロー": "明けの明星",
    "スパイクロー": "たくり線",
    "インサイドバー": "上昇三法",
    # TA-Lib（本家 BUY_PATTERNS_TALIB ラベル）
    "上げ三法": "上昇三法",
    "陽のつつみ線": "包み線",
    "はらみ線": "上昇三法",
    "切り込み線": "明けの明星",
    "陽のたすき線": "上昇三法",
    "ピンバー(ハンマー)": "ハンマー",
    "逆ハンマー": "ハンマー",
    "抱きの本立ち": "包み線",
    "スラストアップ": "包み線",
    "三空叩き込み": "明けの明星",
}


def canonical_pattern_name(name: str) -> str:
    n = (name or "").strip()
    if not n:
        return n
    return SIGNAL_TO_QUADRANT_PATTERN.get(n, n)


def reload_pattern_weights() -> None:
    load_pattern_weight_table.cache_clear()


@lru_cache(maxsize=1)
def load_pattern_weight_table() -> dict[str, dict[str, Any]]:
    if not _WEIGHTS_PATH.is_file():
        return {}
    try:
        raw = json.loads(_WEIGHTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in raw.items() if not k.startswith("_") and isinstance(v, dict)}


def effective_pattern_weight(pattern_name: str) -> float:
    """サンプル数で縮小したパターン重み（0〜1）。"""
    table = load_pattern_weight_table()
    key = canonical_pattern_name(pattern_name)
    entry = table.get(key) or table.get(pattern_name)
    if not entry:
        return PATTERN_WEIGHT_PRIOR
    raw_w = float(entry.get("weight", PATTERN_WEIGHT_PRIOR))
    n = int(entry.get("n", 0) or 0)
    if n <= 0:
        return PATTERN_WEIGHT_PRIOR
    prior_n = PATTERN_WEIGHT_PRIOR_N
    prior_w = PATTERN_WEIGHT_PRIOR
    return (prior_w * prior_n + raw_w * n) / (prior_n + n)


def score_patterns(patterns: list[str]) -> float:
    """
    検出パターンからテクニカル配点（最大 SCORE_PATTERN_MAX）。
    複数パターン時は最も重い1つのみ採用（二重カウント防止）。
    """
    if not patterns:
        return 0.0
    canon = [canonical_pattern_name(p) for p in patterns]
    best = max(effective_pattern_weight(p) for p in canon)
    return round(min(float(SCORE_PATTERN_MAX), best * float(SCORE_PATTERN_MAX)), 2)
