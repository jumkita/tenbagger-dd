"""信用倍率（買残÷売残）の取得。J-Quants またはローカルキャッシュ。"""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import requests
from dotenv import load_dotenv

from core.quadrant_screening.config import FUNDAMENTAL_MAX_WORKERS

load_dotenv()
from core.quadrant_screening.ticker_utils import normalize_ticker

_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache"
_CACHE_FILE = _CACHE_DIR / "margin_ratios.json"
_CACHE_TTL_SEC = 7 * 24 * 3600
_JQUANTS_MARGIN_URL = "https://api.jquants.com/v1/markets/weekly_margin_interest"


@dataclass(frozen=True)
class MarginSnapshot:
    margin_ratio: float
    buy_balance: int | None = None
    sell_balance: int | None = None


def _ticker_to_jquants_code(ticker: str) -> str | None:
    norm = normalize_ticker(ticker)
    if not norm or not norm.endswith(".T"):
        return None
    code = norm[:-2]
    if not code.isdigit():
        return None
    return f"{code}0"


def _load_file_cache() -> dict[str, tuple[float, float]]:
    """ticker -> (ratio, saved_at_epoch)"""
    if not _CACHE_FILE.is_file():
        return {}
    try:
        raw = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        out: dict[str, tuple[float, float]] = {}
        for k, v in raw.items():
            if isinstance(v, dict) and "ratio" in v and "ts" in v:
                out[k] = (float(v["ratio"]), float(v["ts"]))
        return out
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def _save_file_cache(entries: dict[str, float]) -> None:
    now = time.time()
    merged: dict[str, dict[str, float]] = {}
    for t, r in _load_file_cache().items():
        merged[t] = {"ratio": r[0], "ts": r[1]}
    for t, ratio in entries.items():
        merged[t] = {"ratio": ratio, "ts": now}
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_jquants_id_token() -> str | None:
    refresh = os.environ.get("JQUANTS_REFRESH_TOKEN", "").strip()
    if not refresh:
        return None
    try:
        r = requests.post(
            "https://api.jquants.com/v1/token/auth_refresh",
            params={"refreshtoken": refresh},
            timeout=15,
        )
        r.raise_for_status()
        return str(r.json().get("idToken") or "")
    except Exception:
        return None


def _fetch_margin_jquants(ticker: str, id_token: str) -> MarginSnapshot | None:
    code = _ticker_to_jquants_code(ticker)
    if not code:
        return None
    try:
        r = requests.get(
            _JQUANTS_MARGIN_URL,
            params={"code": code},
            headers={"Authorization": f"Bearer {id_token}"},
            timeout=20,
        )
        r.raise_for_status()
        rows = r.json().get("weekly_margin_interest") or []
        if not rows:
            return None
        latest = rows[-1]
        buy = int(latest.get("LongOutstanding") or latest.get("LongOutstandingEggs") or 0)
        sell = int(latest.get("ShrtOutstanding") or latest.get("ShrtOutstandingEggs") or 0)
        if sell <= 0 or buy <= 0:
            return None
        ratio = buy / sell
        return MarginSnapshot(margin_ratio=ratio, buy_balance=buy, sell_balance=sell)
    except Exception:
        return None


def _fetch_one_margin(ticker: str, id_token: str | None) -> tuple[str, MarginSnapshot | None]:
    norm = normalize_ticker(ticker) or ticker
    cached = _load_file_cache()
    if norm in cached:
        ratio, ts = cached[norm]
        if time.time() - ts < _CACHE_TTL_SEC:
            return norm, MarginSnapshot(margin_ratio=ratio)
    if id_token:
        snap = _fetch_margin_jquants(norm, id_token)
        if snap is not None:
            return norm, snap
    return norm, None


def fetch_margin_parallel(tickers: list[str]) -> dict[str, MarginSnapshot]:
    """並列で信用倍率を取得。API未設定時はキャッシュのみ。"""
    out: dict[str, MarginSnapshot] = {}
    if not tickers:
        return out
    id_token = _get_jquants_id_token()
    workers = min(FUNDAMENTAL_MAX_WORKERS, len(tickers))
    fresh: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch_one_margin, t, id_token): t for t in tickers}
        for fut in as_completed(futs):
            try:
                ticker, snap = fut.result()
                if snap is not None:
                    out[ticker] = snap
                    fresh[ticker] = snap.margin_ratio
            except Exception:
                pass
    if fresh:
        _save_file_cache(fresh)
    return out
