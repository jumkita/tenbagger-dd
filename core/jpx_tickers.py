"""
東証上場銘柄一覧をJPX公式ページから取得するモジュール。
HTMLからExcelリンクを抽出してダウンロードし、code / name のDataFrameを返す。
"""
from __future__ import annotations

from io import BytesIO
from typing import Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

JPX_LISTING_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html"
JPX_BASE = "https://www.jpx.co.jp/markets/statistics-equities/misc/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _find_xlsx_url_from_page() -> Optional[str]:
    """JPXの銘柄一覧HTMLからExcel(.xlsx)のURLを取得する。"""
    try:
        r = requests.get(JPX_LISTING_URL, headers={"User-Agent": USER_AGENT}, timeout=15)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if ".xlsx" in href.lower():
                if href.startswith("http"):
                    return href
                return requests.compat.urljoin(JPX_BASE, href)
    except Exception:
        pass
    return None


def _try_direct_xlsx_urls() -> Optional[bytes]:
    """よくあるファイル名で直接ダウンロードを試す。"""
    for name in ("01_03.xlsx", "01_04.xlsx", "01_02.xlsx", "01_01.xlsx"):
        url = requests.compat.urljoin(JPX_BASE, name)
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
            if r.status_code == 200 and len(r.content) > 1000:
                return r.content
        except Exception:
            continue
    return None


def _parse_jpx_excel(content: bytes) -> pd.DataFrame:
    """JPXのExcelをパースし、code / name（と market）のDataFrameを返す。"""
    df = pd.read_excel(BytesIO(content), engine="openpyxl")
    col_map = {}
    for c in df.columns:
        c_str = str(c).strip()
        if "code" not in col_map.values() and ("コード" in c_str or c_str == "Code"):
            col_map[c] = "code"
        if "name" not in col_map.values() and ("銘柄名" in c_str or "名称" in c_str or c_str == "Name" or ("銘柄" in c_str and "コード" not in c_str)):
            col_map[c] = "name"
        if "market" not in col_map.values() and ("市場" in c_str or "商品" in c_str):
            col_map[c] = "market"
    df = df.rename(columns=col_map)
    if "code" not in df.columns or "name" not in df.columns:
        df = df.rename(columns={df.columns[0]: "code", df.columns[1]: "name"})
    use_cols = [c for c in ["code", "name", "market"] if c in df.columns]
    df = df[use_cols].dropna(subset=["code", "name"], how="all")
    df["code"] = df["code"].astype(str).str.replace(r"\D", "", regex=True)
    df = df[df["code"].str.len() >= 4]
    df["code"] = df["code"].str.zfill(4) + ".T"
    df["name"] = df["name"].astype(str).str.strip()
    if "market" in df.columns:
        df["market"] = df["market"].astype(str).str.strip()
    return df.dropna(subset=["name"]).drop_duplicates(subset=["code"]).reset_index(drop=True)


def fetch_jpx_tickers() -> pd.DataFrame:
    """
    東証上場銘柄一覧を取得する。
    戻り値: columns [code, name], code は '7203.T' 形式（yfinance用）。
    """
    content: Optional[bytes] = None
    url = _find_xlsx_url_from_page()
    if url:
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
            if r.status_code == 200 and len(r.content) > 1000:
                content = r.content
        except Exception:
            pass
    if content is None:
        content = _try_direct_xlsx_urls()
    if content is None:
        return pd.DataFrame(columns=["code", "name"])
    return _parse_jpx_excel(content)
