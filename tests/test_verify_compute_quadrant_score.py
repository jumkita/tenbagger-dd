"""verify_quadrant_filters の compute_quadrant_score_for_signal（ネットワークなし）。"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

from core.quadrant_screening.fundamentals import FundamentalSnapshot
from core.quadrant_screening.margin import MarginSnapshot
from core.quadrant_screening.sector import SectorMomentum

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "verify_quadrant_filters",
    _ROOT / "scripts" / "verify_quadrant_filters.py",
)
assert _SPEC and _SPEC.loader
_vqf = importlib.util.module_from_spec(_SPEC)
sys.modules["verify_quadrant_filters"] = _vqf
_SPEC.loader.exec_module(_vqf)

compute_quadrant_score_for_signal = _vqf.compute_quadrant_score_for_signal
Signal = _vqf.Signal


def test_compute_quadrant_returns_none_when_no_ohlcv():
    sig = Signal(
        ticker="9999.T",
        signal_date="2024-06-01",
        entry=1000.0,
        avg_return_pct=1.0,
        pattern_name="",
    )
    out = compute_quadrant_score_for_signal(
        sig,
        {},
        {},
        {},
        {},
        {},
    )
    assert out is None


def test_compute_quadrant_handles_dataframe_cache_lookup():
    """DataFrame を or で短絡評価しない（曖昧真偽エラー回避）。"""
    sig = Signal(
        ticker="7203.T",
        signal_date="2024-06-01",
        entry=1000.0,
        avg_return_pct=1.0,
        pattern_name="",
    )
    empty = pd.DataFrame()
    out = compute_quadrant_score_for_signal(
        sig,
        {"7203.T": empty},
        {"7203.T": FundamentalSnapshot(5.0, None, None, roe_is_default=True)},
        {"7203.T": None},
        {},
        {},
    )
    assert out is None
