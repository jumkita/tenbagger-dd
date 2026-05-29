"""pattern_weights.json と canonical マッピングの整合。"""
from __future__ import annotations

import json

from core.quadrant_screening.pattern_weights import (
    SIGNAL_TO_QUADRANT_PATTERN,
    _WEIGHTS_PATH,
)


def test_canonical_alias_targets_exist_in_pattern_weights_json():
    """SIGNAL_TO_QUADRANT_PATTERN の値はすべて JSON にキーとして存在する（事前重みのみに落ちない）。"""
    raw = json.loads(_WEIGHTS_PATH.read_text(encoding="utf-8"))
    keys = {k for k in raw if not k.startswith("_")}
    for src, dst in SIGNAL_TO_QUADRANT_PATTERN.items():
        assert src.strip(), f"empty source key: {src!r}"
        assert dst in keys, (
            f"canonical target {dst!r} (from signal {src!r}) missing from {_WEIGHTS_PATH}"
        )


def test_pattern_weights_json_has_core_keys():
    raw = json.loads(_WEIGHTS_PATH.read_text(encoding="utf-8"))
    for k in ("包み線", "ハンマー", "たくり線", "明けの明星", "上昇三法", "赤三兵"):
        assert k in raw and isinstance(raw[k], dict), k
