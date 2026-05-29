#!/usr/bin/env python3
"""verify_quadrant_filters のシグナルからパターン別統計を集計し pattern_weights.json を更新。"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.quadrant_screening.config import PATTERN_WEIGHT_PRIOR
from core.quadrant_screening.pattern_weights import (
    _WEIGHTS_PATH,
    canonical_pattern_name,
    reload_pattern_weights,
)

DEFAULT_PRIOR = PATTERN_WEIGHT_PRIOR


def _load_signals(local_dir: Path | None, max_files: int | None):
    from scripts.verify_quadrant_filters import load_signals

    return load_signals(local_dir, max_files=max_files)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="パターン重みJSONをバックテスト統計で更新")
    parser.add_argument("--local-dir", type=Path, default=None)
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        metavar="N",
        help="daily_buy_signals_*.json を日付順で末尾 N 件だけ集計（GitHub／ローカル共通）",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    signals = _load_signals(args.local_dir, args.max_files)
    if not signals:
        print("シグナルがありません。")
        sys.exit(1)

    stats: dict[str, dict[str, float]] = defaultdict(
        lambda: {"n": 0, "wins": 0, "sum_ret": 0.0}
    )
    for sig in signals:
        raw = (getattr(sig, "pattern_name", None) or "").strip()
        if not raw:
            continue
        name = canonical_pattern_name(raw)
        bucket = stats[name]
        bucket["n"] += 1
        ret = float(getattr(sig, "avg_return_pct", 0) or 0)
        bucket["sum_ret"] += ret
        if ret > 0:
            bucket["wins"] += 1

    existing: dict = {}
    if _WEIGHTS_PATH.is_file():
        try:
            existing = json.loads(_WEIGHTS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}

    out: dict[str, object] = {"_comment": existing.get("_comment", "auto-updated")}
    baseline_wr = 0.5
    baseline_ret = 0.0
    all_wr = []
    all_ret = []
    for name, b in stats.items():
        n = int(b["n"])
        if n > 0:
            wr = b["wins"] / n
            avg = b["sum_ret"] / n
            all_wr.append(wr)
            all_ret.append(avg)
    if all_wr:
        baseline_wr = sum(all_wr) / len(all_wr)
    if all_ret:
        baseline_ret = sum(all_ret) / len(all_ret)

    for name, b in stats.items():
        n = int(b["n"])
        wr = b["wins"] / n if n else baseline_wr
        avg = b["sum_ret"] / n if n else baseline_ret
        wr_score = wr / baseline_wr if baseline_wr > 0 else 1.0
        ret_score = 1.0 + (avg - baseline_ret) / 10.0
        raw_w = max(0.35, min(1.0, wr_score * 0.6 + ret_score * 0.4))
        if n < 30:
            raw_w = DEFAULT_PRIOR * 0.5 + raw_w * 0.5
        out[name] = {
            "weight": round(raw_w, 3),
            "n": n,
            "win_rate": round(wr, 3),
            "avg_return": round(avg, 2),
        }

    for name, entry in existing.items():
        if name.startswith("_") or name in out:
            continue
        canon = canonical_pattern_name(name)
        if canon != name and canon in out:
            continue
        if isinstance(entry, dict):
            out[name] = entry

    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.dry_run:
        print(text)
        return
    _WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _WEIGHTS_PATH.write_text(text + "\n", encoding="utf-8")
    reload_pattern_weights()
    print(f"Updated {_WEIGHTS_PATH} ({len(stats)} canonical patterns from {len(signals)} signals)")


if __name__ == "__main__":
    main()
