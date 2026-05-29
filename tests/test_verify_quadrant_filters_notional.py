"""verify_quadrant_filters の等金額加重リターン。"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "verify_quadrant_filters",
    _ROOT / "scripts" / "verify_quadrant_filters.py",
)
assert _SPEC and _SPEC.loader
_vqf = importlib.util.module_from_spec(_SPEC)

sys.modules["verify_quadrant_filters"] = _vqf
_SPEC.loader.exec_module(_vqf)
GroupStats = _vqf.GroupStats
Signal = _vqf.Signal
REALIZED_WEIGHT_NOTIONAL_JPY = _vqf.REALIZED_WEIGHT_NOTIONAL_JPY


def test_weighted_realized_uses_equal_notional_matches_arithmetic_mean():
    g = GroupStats(name="test")
    s1 = Signal("7203.T", "2024-01-01", 3000.0, 1.0, "p", realized_return_pct=10.0)
    s2 = Signal("7203.T", "2024-01-02", 500.0, 1.0, "p", realized_return_pct=-2.0)
    g.add(s1)
    g.add(s2)
    assert g.n_realized == 2
    assert g.avg_realized == 4.0
    assert g.weighted_realized == 4.0
    assert g.sum_notional_jpy == 2 * REALIZED_WEIGHT_NOTIONAL_JPY


def test_old_100_share_would_have_differed():
    """値段が違うと100株加重は算術平均と一致しない（回帰防止の説明用）。"""
    high = 3000.0 * 100 * 0.10
    low = 500.0 * 100 * (-0.02)
    cost = 3000.0 * 100 + 500.0 * 100
    legacy_weighted = (high + low) / cost * 100.0
    assert abs(legacy_weighted - 4.0) > 0.01
