import pandas as pd


def compute_yoy_growth(df: pd.DataFrame) -> pd.DataFrame:
    """売上高 YoY 成長率（%）を計算して列を追加。"""
    df = df.copy()
    df["revenue_yoy"] = None

    mask = (
        df["revenue_latest"].notna()
        & df["revenue_prev"].notna()
        & (df["revenue_prev"] != 0)
    )
    df.loc[mask, "revenue_yoy"] = (
        df.loc[mask, "revenue_latest"] / df.loc[mask, "revenue_prev"] - 1.0
    ) * 100.0

    return df


def _ensure_mc_oku(
    df: pd.DataFrame,
    min_mc_oku: float,
    max_mc_oku: float,
) -> tuple[pd.DataFrame, str, float, float]:
    """億円列を用意し、(df, mc_col, min_mc, max_mc) を返す。"""
    df = df.copy()
    if "market_cap_oku" not in df.columns and "market_cap" in df.columns:
        df["market_cap_oku"] = df["market_cap"].apply(
            lambda x: x / 1e8 if x is not None and x > 0 else None
        )
    mc_col = "market_cap_oku" if "market_cap_oku" in df.columns else "market_cap"
    if mc_col == "market_cap":
        return df, mc_col, min_mc_oku * 1e8, max_mc_oku * 1e8
    return df, mc_col, min_mc_oku, max_mc_oku


def screening_stats(
    market_df: pd.DataFrame,
    min_mc_oku: float = 50.0,
    max_mc_oku: float = 300.0,
    min_yoy: float = 20.0,
) -> dict:
    """スクリーニングの内訳件数を返す（表示用）。"""
    df = compute_yoy_growth(market_df.copy())
    df, mc_col, min_mc, max_mc = _ensure_mc_oku(df, min_mc_oku, max_mc_oku)

    mc_ok = df[mc_col].notna() & (df[mc_col] >= min_mc) & (df[mc_col] <= max_mc)
    yoy_ok = df["revenue_yoy"].notna() & (df["revenue_yoy"] >= min_yoy)
    both = mc_ok & yoy_ok
    return {
        "total": len(df),
        "mc_in_range": int(mc_ok.sum()),
        "yoy_available": int(df["revenue_yoy"].notna().sum()),
        "yoy_in_range": int(yoy_ok.sum()),
        "both": int(both.sum()),
    }


def screen_candidates(
    market_df: pd.DataFrame,
    min_mc_oku: float = 50.0,
    max_mc_oku: float = 300.0,
    min_yoy: float = 20.0,
    require_revenue_yoy: bool = True,
) -> pd.DataFrame:
    """
    テンバガー候補の一次スクリーニング。時価総額は億円で指定。
    require_revenue_yoy=False のときは時価総額条件のみでフィルタ（売上高YoYが無くても通過可）。
    """
    df = compute_yoy_growth(market_df.copy())
    df, mc_col, min_mc, max_mc = _ensure_mc_oku(df, min_mc_oku, max_mc_oku)

    cond = df[mc_col].notna() & (df[mc_col] >= min_mc) & (df[mc_col] <= max_mc)
    if require_revenue_yoy:
        cond = cond & df["revenue_yoy"].notna() & (df["revenue_yoy"] >= min_yoy)
    return df.loc[cond].reset_index(drop=True)

