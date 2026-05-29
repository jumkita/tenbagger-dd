from __future__ import annotations

import re
from pathlib import Path
from typing import Union

import pandas as pd

from core.jpx_tickers import fetch_jpx_tickers

PathLike = Union[str, Path]


# 銘柄CSVの列名のゆらぎに対応（先頭一致または部分一致で code / name にマッピング）
CODE_ALIASES = ("code", "銘柄コード", "コード", "symbol", "ticker", "stock_code")
NAME_ALIASES = ("name", "銘柄名", "名称", "会社名", "company", "name_jp")


def _normalize_csv_columns(df: pd.DataFrame) -> pd.DataFrame:
    """CSVの列名を code / name に統一する。"""
    df = df.copy()
    cols = list(df.columns)
    for orig in cols:
        c = str(orig).strip()
        if "code" not in df.columns:
            for alias in CODE_ALIASES:
                if alias in c or c == alias:
                    df["code"] = df[orig]
                    break
    for orig in cols:
        c = str(orig).strip()
        if "name" not in df.columns:
            for alias in NAME_ALIASES:
                if alias in c or c == alias:
                    df["name"] = df[orig]
                    break
    return df


def load_tickers(csv_path: PathLike) -> pd.DataFrame:
    """銘柄コードCSVを読み込む。列名は code/name または 銘柄コード/銘柄名 等に対応。"""
    csv_path = Path(csv_path)
    try:
        df = pd.read_csv(csv_path, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(csv_path, encoding="cp932")
    df = _normalize_csv_columns(df)
    if "code" not in df.columns or "name" not in df.columns:
        raise ValueError(
            f"CSVには銘柄コード列と銘柄名列が必要です。検出した列: {list(df.columns)}"
        )
    df = df.dropna(subset=["code", "name"], how="all")
    # コードを正規化: 1301.0 → "1301", 130A → "130A"（小数は整数に、文字列はそのまま）
    def _normalize_code(x) -> str:
        if pd.isna(x):
            return ""
        s = str(x).strip()
        try:
            return str(int(float(s)))
        except (ValueError, TypeError):
            return s.upper()

    df["_code_raw"] = df["code"].apply(_normalize_code)
    # yfinance用ティッカー: "1301" → "1301.T", "130A" → "130A.T"
    def _to_ticker(raw: str) -> str | None:
        if not raw:
            return None
        raw = raw.upper()
        digits = re.sub(r"\D", "", raw)
        if re.match(r"^\d{4}$", raw):
            return raw + ".T"
        if re.match(r"^\d+[A-Z]$", raw):
            return raw + ".T"
        if len(digits) >= 4:
            return digits[:4].zfill(4) + ".T"
        return None

    df["code"] = df["_code_raw"].apply(_to_ticker)
    df = df.dropna(subset=["code"]).drop(columns=["_code_raw"])
    df["name"] = df["name"].astype(str).str.strip()
    return df.dropna(subset=["name"]).drop_duplicates(subset=["code"]).reset_index(drop=True)


def list_csv_in_folder(data_dir: Path) -> list[str]:
    """data_dir 内の .csv ファイル名をリストで返す（昇順）。"""
    data_dir = Path(data_dir)
    if not data_dir.exists():
        return []
    return sorted(p.name for p in data_dir.glob("*.csv"))


def get_csv_row_count(data_dir: Path, csv_filename: str) -> int:
    """CSVのデータ行数（ヘッダー除く）を返す。読み込みは軽く行う。"""
    path = Path(data_dir) / csv_filename
    if not path.exists():
        return 0
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f) - 1  # ヘッダー1行を除く
    except Exception:
        try:
            with open(path, "r", encoding="cp932", errors="replace") as f:
                return sum(1 for _ in f) - 1
        except Exception:
            return 0


def list_csv_with_counts(data_dir: Path) -> list[tuple[str, int]]:
    """(ファイル名, 行数) のリストを返す。行数が多い順。"""
    names = list_csv_in_folder(data_dir)
    with_count = [(n, get_csv_row_count(data_dir, n)) for n in names]
    return sorted(with_count, key=lambda x: -x[1])


def load_tickers_from_folder(
    data_dir: Path,
    csv_filename: str | None = None,
) -> tuple[pd.DataFrame, str]:
    """
    銘柄一覧を data_dir 内のCSVから取得（JPXは使わない）。
    csv_filename を指定した場合はそのファイルのみ使用。None の場合は従来の優先順で試す。
    戻り値: (tickers_df, "csv" | "none")。
    """
    data_dir = Path(data_dir)
    if csv_filename:
        path = data_dir / csv_filename
        if path.exists():
            try:
                return load_tickers(path), "csv"
            except Exception:
                return pd.DataFrame(columns=["code", "name"]), "none"
        return pd.DataFrame(columns=["code", "name"]), "none"
    for name in ("tickers.csv", "mock_tickers.csv", "銘柄一覧.csv"):
        path = data_dir / name
        if path.exists():
            try:
                return load_tickers(path), "csv"
            except Exception:
                continue
    return pd.DataFrame(columns=["code", "name"]), "none"


def load_tickers_auto(
    data_dir: Path,
    use_folder_csv_only: bool = False,
    folder_csv_filename: str | None = None,
) -> tuple[pd.DataFrame, str]:
    """
    銘柄一覧を取得。
    use_folder_csv_only=True のときはフォルダのCSVのみ使用（JPXは呼ばない）。
    それ以外は JPX を試し、失敗時は data_dir 内の CSV を試す。
    戻り値: (tickers_df, "jpx" | "csv" | "none")。
    """
    if use_folder_csv_only:
        return load_tickers_from_folder(data_dir, csv_filename=folder_csv_filename)
    jpx_df = fetch_jpx_tickers()
    if not jpx_df.empty:
        return jpx_df, "jpx"
    return load_tickers_from_folder(data_dir)


def filter_standard_growth_first(tickers_df: pd.DataFrame, max_tickers: int) -> pd.DataFrame:
    """スタンダード・グロースを先頭に並べ、先頭 max_tickers 件を返す。market 列が無い場合はそのまま先頭から。"""
    if "market" not in tickers_df.columns or tickers_df.empty:
        return tickers_df.head(max_tickers)
    m = tickers_df["market"].astype(str).str.contains("スタンダード|グロース", na=False, regex=True)
    small = tickers_df[m]
    other = tickers_df[~m]
    combined = pd.concat([small, other], ignore_index=True)
    return combined.head(max_tickers)

