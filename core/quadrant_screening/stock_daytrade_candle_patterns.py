# -*- coding: utf-8 -*-
"""
stock-daytrade `signal_scanner.CandlePatterns` から、本家 `logic.detect_all_patterns`
が買いに使う判定だけを抜粋（出所: jumkita/stock-daytrade の signal_scanner.py）。
"""
from __future__ import annotations

from typing import Optional

import pandas as pd


def _body(row: pd.Series) -> float:
    return abs(float(row["Close"]) - float(row["Open"]))


def _upper_shadow(row: pd.Series) -> float:
    return float(row["High"]) - max(float(row["Open"]), float(row["Close"]))


def _lower_shadow(row: pd.Series) -> float:
    return min(float(row["Open"]), float(row["Close"])) - float(row["Low"])


def _bull(row: pd.Series) -> bool:
    return float(row["Close"]) > float(row["Open"])


def _bear(row: pd.Series) -> bool:
    return float(row["Open"]) > float(row["Close"])


def _range_hl(row: pd.Series) -> float:
    return float(row["High"]) - float(row["Low"])


def _body_is_tiny(row: pd.Series, min_range: float = 1e-8) -> bool:
    r = _range_hl(row)
    if r <= min_range:
        return True
    return _body(row) < r * 0.1


def _body_is_small(row: pd.Series, avg_body: float, min_range: float = 1e-8) -> bool:
    if avg_body <= min_range:
        return False
    return _body(row) >= avg_body * 0.3


class CandlePatterns:
    """本家 `detect_all_patterns` が参照する買い系メソッドのみ実装。"""

    def __init__(self, df: pd.DataFrame):
        self.df = df

    def _row(self, i: int) -> Optional[pd.Series]:
        if i < 0 or i >= len(self.df):
            return None
        return self.df.iloc[i]

    def _safe(self, i: int, *more: int) -> bool:
        indices = [i] + list(more)
        return all(0 <= k < len(self.df) for k in indices)

    def is_aka_sanpei(self, i: int) -> bool:
        if not self._safe(i, i - 1, i - 2):
            return False
        r0, r1, r2 = self._row(i), self._row(i - 1), self._row(i - 2)
        if not (_bull(r0) and _bull(r1) and _bull(r2)):
            return False
        if not (float(r2["Close"]) < float(r1["Close"]) < float(r0["Close"])):
            return False
        avg_body = (_body(r0) + _body(r1) + _body(r2)) / 3.0
        return (
            _body_is_small(r0, avg_body)
            and _body_is_small(r1, avg_body)
            and _body_is_small(r2, avg_body)
        )

    def is_akenomyojo(self, i: int) -> bool:
        if not self._safe(i, i - 1, i - 2):
            return False
        r0, r1, r2 = self._row(i), self._row(i - 1), self._row(i - 2)
        if not _bear(r2):
            return False
        body2 = _body(r2)
        range2 = _range_hl(r2)
        if range2 <= 0:
            return False
        if body2 < range2 * 0.5:
            return False
        if not _body_is_tiny(r1):
            return False
        gap_down_2_1 = float(r1["High"]) < float(r2["Low"])
        if not gap_down_2_1:
            return False
        if not _bull(r0):
            return False
        body0 = _body(r0)
        if body0 < _range_hl(r0) * 0.5:
            return False
        gap_up_1_0 = float(r0["Low"]) > float(r1["High"])
        engulf_1_0 = float(r0["Open"]) < float(r1["Low"]) and float(r0["Close"]) > float(r1["High"])
        return gap_up_1_0 or engulf_1_0

    def is_nihon_takuri(self, i: int) -> bool:
        if not self._safe(i, i - 1):
            return False
        r0, r1 = self._row(i), self._row(i - 1)
        for r in (r0, r1):
            ls, body = _lower_shadow(r), _body(r)
            if body <= 0:
                if ls <= 0:
                    return False
                continue
            if ls <= body * 2:
                return False
        return True
