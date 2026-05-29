#!/usr/bin/env python3
"""プライム母集団サンプルで4象限スコア分布と閾値別通過件数を表示（足切り目安用）。"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from core.quadrant_screening.fundamentals import fetch_fundamentals_parallel
from core.quadrant_screening.margin import fetch_margin_parallel
from core.quadrant_screening.market_data import fetch_ohlcv_bulk
from core.quadrant_screening.scoring import compute_score
from core.quadrant_screening.sector import SectorMomentum, load_sector_momentum
from core.quadrant_screening.technical import analyze_technical, passes_primary_filter
from core.quadrant_screening.universe import load_prime_universe


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="4象限スコア分布（閾値目安）")
    parser.add_argument(
        "--csv",
        type=Path,
        default=ROOT / "data" / "jpx_all_tickers.csv",
    )
    parser.add_argument("--limit", type=int, default=250, help="母集団先頭N件")
    args = parser.parse_args()

    universe = load_prime_universe(args.csv).head(args.limit)
    tickers = universe["ticker"].tolist()
    sector_map: dict[str, int | None] = {}
    for _, row in universe.iterrows():
        sec = row.get("sector_code_17")
        sector_map[row["ticker"]] = int(sec) if pd.notna(sec) else None

    _, sector_momentum = load_sector_momentum()
    ohlcv = fetch_ohlcv_bulk(tickers)

    primary: list[str] = []
    tech_snap: dict[str, object] = {}
    for t in tickers:
        df = ohlcv.get(t)
        if df is None or df.empty:
            continue
        tech = analyze_technical(df)
        if tech is None or not passes_primary_filter(tech.price, tech.vol_20d_avg):
            continue
        if not tech.above_75ma:
            continue
        primary.append(t)
        tech_snap[t] = tech

    fundamentals = fetch_fundamentals_parallel(primary)
    margins = fetch_margin_parallel(primary)

    scores: list[float] = []
    for t in primary:
        tech = tech_snap[t]
        fund = fundamentals.get(t)
        if fund is None:
            continue
        sec_code = sector_map.get(t)
        sec_mom: SectorMomentum | None = None
        if sec_code is not None and sec_code in sector_momentum:
            sec_mom = sector_momentum[sec_code]
        bd = compute_score(tech, fund, sec_mom, sector_code=sec_code, ticker=t, margin=margins.get(t))
        scores.append(bd.total)

    scores.sort(reverse=True)
    n = len(scores)
    if not scores:
        print("スコア算出できる銘柄がありません。")
        sys.exit(1)

    asc = sorted(scores)

    def pct(p: float) -> float:
        """pパーセンタイル（昇順・古典定義）。"""
        if n == 1:
            return asc[0]
        k = (n - 1) * p / 100.0
        lo = int(k)
        hi = min(lo + 1, n - 1)
        w = k - lo
        return asc[lo] * (1 - w) + asc[hi] * w

    print(f"# 母集団先頭 {args.limit} 件 → 75MA等通過 {n} 件のスコア分布（1時点・参考）")
    print(f"- min: {asc[0]:.1f}  max: {asc[-1]:.1f}  mean: {statistics.mean(scores):.1f}  stdev: {statistics.stdev(scores) if n > 1 else 0:.1f}")
    print(f"- p90: {pct(90):.1f}  p75: {pct(75):.1f}  p50: {pct(50):.1f}  p25: {pct(25):.1f}")
    print()
    print("| 閾値以上 | 件数 | 通過率(通過母集団比) |")
    print("|---:|---:|---:|")
    for th in (55, 50, 45, 40, 35, 30, 28, 25, 22, 20):
        c = sum(1 for s in scores if s >= th)
        print(f"| ≥{th} | {c} | {100.0 * c / n:.1f}% |")
    print()
    print("## 目安（このサンプル時点）")
    for label, k in (("上位5件相当", 5), ("上位10件相当", 10), ("上位20件相当", 20)):
        if n >= k:
            print(f"- {label}の下限スコア ≈ **{scores[k - 1]:.0f}点**（{k}件目）")


if __name__ == "__main__":
    main()
