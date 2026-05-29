"""ROE / EPS / 成長率 取得（欠損フォールバック付き）。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import yfinance as yf

from core.quadrant_screening.config import (
    DEBT_EQUITY_GOOD,
    DEBT_EQUITY_OK,
    DEBT_EQUITY_WARN,
    EPS_DISCOUNT_TIER2_PCT,
    EPS_DISCOUNT_TIER3_PCT,
    FUNDAMENTAL_MAX_WORKERS,
    GROWTH_FUND_TIER2_PCT,
    GROWTH_FUND_TIER3_PCT,
    GROWTH_PER_MULT_NORMAL,
    GROWTH_PER_MULT_TIER2,
    GROWTH_PER_MULT_TIER3,
    GROWTH_PER_TIER2_PCT,
    GROWTH_PER_TIER3_PCT,
    HIGH_GROWTH_PER,
    HIGH_GROWTH_TICKER_SET,
    ROE_DEFAULT_PCT,
    ROE_BONUS_THRESHOLD,
    ROE_TIER2_PCT,
    ROE_TIER3_PCT,
    SCORE_FUND_AXIS,
    SCORE_FUNDAMENTAL_MAX,
    get_sector_per,
)
from core.quadrant_screening.ticker_utils import normalize_ticker


@dataclass
class FundamentalSnapshot:
    roe_pct: float
    trailing_eps: float | None
    trailing_pe: float | None
    growth_pct: float = 0.0
    roe_is_default: bool = False
    operating_margin_pct: float | None = None
    debt_to_equity: float | None = None


def _parse_pct_field(raw: object) -> float | None:
    if raw is None or not isinstance(raw, (int, float)) or raw != raw:
        return None
    v = float(raw)
    if abs(v) <= 1.5:
        v *= 100.0
    return v


def _parse_debt_to_equity(raw: object) -> float | None:
    """yfinance debtToEquity（%表記のことが多い）を比率に正規化。"""
    if raw is None or not isinstance(raw, (int, float)) or raw != raw:
        return None
    v = float(raw)
    if v > 20.0:
        return v / 100.0
    return v


def _parse_growth_pct(info: dict) -> float:
    """earningsGrowth を優先し、欠損時は revenueGrowth。いずれも無ければ 0%。"""
    for key in ("earningsGrowth", "revenueGrowth"):
        raw = info.get(key)
        if raw is not None and isinstance(raw, (int, float)) and raw == raw:
            v = float(raw)
            if abs(v) <= 1.5:
                v *= 100.0
            return v
    return 0.0


def compute_allowed_per(
    base_per: float,
    growth_pct: float,
    ticker: str | None = None,
) -> float:
    """
    業種別基礎PERに成長率プレミアムを乗算して許容PERを返す。
    HIGH_GROWTH_TICKERS は無条件で HIGH_GROWTH_PER（40倍）を適用。
    """
    norm = normalize_ticker(ticker) if ticker else None
    if norm and norm in HIGH_GROWTH_TICKER_SET:
        return HIGH_GROWTH_PER

    if growth_pct >= GROWTH_PER_TIER3_PCT:
        multiplier = GROWTH_PER_MULT_TIER3
    elif growth_pct >= GROWTH_PER_TIER2_PCT:
        multiplier = GROWTH_PER_MULT_TIER2
    else:
        multiplier = GROWTH_PER_MULT_NORMAL
    return base_per * multiplier


def _fetch_one(ticker: str) -> tuple[str, FundamentalSnapshot]:
    roe_pct = ROE_DEFAULT_PCT
    eps: float | None = None
    pe: float | None = None
    growth_pct = 0.0
    is_default = True
    op_margin: float | None = None
    dte: float | None = None
    try:
        info = yf.Ticker(ticker).info or {}
        raw_roe = info.get("returnOnEquity")
        if raw_roe is not None and isinstance(raw_roe, (int, float)) and raw_roe == raw_roe:
            roe_pct = float(raw_roe) * 100.0 if abs(float(raw_roe)) <= 1.5 else float(raw_roe)
            is_default = False
        raw_eps = info.get("trailingEps")
        if raw_eps is not None and isinstance(raw_eps, (int, float)) and raw_eps == raw_eps:
            eps = float(raw_eps)
        raw_pe = info.get("trailingPE")
        if raw_pe is not None and isinstance(raw_pe, (int, float)) and raw_pe == raw_pe:
            pe = float(raw_pe)
        growth_pct = _parse_growth_pct(info)
        op_margin = _parse_pct_field(info.get("operatingMargins") or info.get("profitMargins"))
        dte = _parse_debt_to_equity(info.get("debtToEquity"))
    except Exception:
        pass
    return ticker, FundamentalSnapshot(
        roe_pct=roe_pct,
        trailing_eps=eps,
        trailing_pe=pe,
        growth_pct=growth_pct,
        roe_is_default=is_default,
        operating_margin_pct=op_margin,
        debt_to_equity=dte,
    )


def fetch_fundamentals_parallel(tickers: list[str]) -> dict[str, FundamentalSnapshot]:
    out: dict[str, FundamentalSnapshot] = {}
    if not tickers:
        return out
    workers = min(FUNDAMENTAL_MAX_WORKERS, len(tickers))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch_one, t): t for t in tickers}
        for fut in as_completed(futs):
            try:
                ticker, snap = fut.result()
                out[ticker] = snap
            except Exception:
                t = futs[fut]
                out[t] = FundamentalSnapshot(
                    roe_pct=ROE_DEFAULT_PCT,
                    trailing_eps=None,
                    trailing_pe=None,
                    growth_pct=0.0,
                    roe_is_default=True,
                )
    return out


def eps_discount_pct(
    price: float,
    eps: float | None,
    *,
    sector_code: int | None = None,
    industry_per: float | None = None,
    growth_pct: float = 0.0,
    ticker: str | None = None,
) -> float | None:
    """適正株価(EPS×補正後許容PER)に対する割安度（%）。プラス=割安。"""
    if price <= 0 or eps is None or eps <= 0:
        return None
    base_per = industry_per if industry_per is not None else get_sector_per(sector_code)
    allowed_per = compute_allowed_per(base_per, growth_pct, ticker)
    fair = eps * allowed_per
    if fair <= 0:
        return None
    return (fair - price) / price * 100.0


def _tier_score(value: float, t1: float, t2: float, t3: float, axis: float = SCORE_FUND_AXIS) -> float:
    """t1未満0、t1で2、t2で3.5、t3以上で満点。"""
    if value < t1:
        return 0.0
    if value >= t3:
        return axis
    if value >= t2:
        return axis * 0.7
    return axis * 0.4


def score_profitability(fund: FundamentalSnapshot) -> float:
    if fund.roe_is_default:
        return 0.0
    base = _tier_score(fund.roe_pct, ROE_BONUS_THRESHOLD, ROE_TIER2_PCT, ROE_TIER3_PCT)
    if fund.operating_margin_pct is not None and fund.operating_margin_pct >= 10.0:
        base = min(SCORE_FUND_AXIS, base + 1.0)
    return round(min(SCORE_FUND_AXIS, base), 2)


def score_growth(fund: FundamentalSnapshot) -> float:
    return round(
        _tier_score(fund.growth_pct, 5.0, GROWTH_FUND_TIER2_PCT, GROWTH_FUND_TIER3_PCT),
        2,
    )


def score_valuation(
    price: float,
    fund: FundamentalSnapshot,
    *,
    sector_code: int | None = None,
    ticker: str | None = None,
) -> float:
    disc = eps_discount_pct(
        price,
        fund.trailing_eps,
        sector_code=sector_code,
        growth_pct=fund.growth_pct,
        ticker=ticker,
    )
    if disc is None:
        return 0.0
    if disc <= 0:
        return 0.0
    return round(
        _tier_score(disc, 5.0, EPS_DISCOUNT_TIER2_PCT, EPS_DISCOUNT_TIER3_PCT),
        2,
    )


def score_financial_health(fund: FundamentalSnapshot) -> float:
    dte = fund.debt_to_equity
    if dte is None:
        return SCORE_FUND_AXIS * 0.4
    if dte <= DEBT_EQUITY_GOOD:
        return float(SCORE_FUND_AXIS)
    if dte <= DEBT_EQUITY_OK:
        return SCORE_FUND_AXIS * 0.7
    if dte <= DEBT_EQUITY_WARN:
        return SCORE_FUND_AXIS * 0.35
    return 0.0


def score_fundamental_total(
    fund: FundamentalSnapshot,
    price: float,
    *,
    sector_code: int | None = None,
    ticker: str | None = None,
) -> float:
    pts = (
        score_profitability(fund)
        + score_growth(fund)
        + score_valuation(price, fund, sector_code=sector_code, ticker=ticker)
        + score_financial_health(fund)
    )
    return round(min(float(SCORE_FUNDAMENTAL_MAX), pts), 2)
