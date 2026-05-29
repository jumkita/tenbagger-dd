"""
TAM/SAM/SOM 推計：Gemini API 連携。
"""
from __future__ import annotations

import os
import re
from typing import Optional

from dotenv import load_dotenv

from .models import MarketSizeEstimate

load_dotenv()

# 環境変数: GOOGLE_API_KEY または GEMINI_API_KEY
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")


def verify_gemini_connection() -> dict:
    """
    Gemini API が利用可能か確認する。
    戻り値: {"ok": bool, "message": str}
    """
    if not GEMINI_API_KEY or not str(GEMINI_API_KEY).strip():
        return {"ok": False, "message": "APIキーが設定されていません。.env に GOOGLE_API_KEY または GEMINI_API_KEY を設定してください。"}
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content("「接続OK」とだけ1行で返してください。")
        text = getattr(response, "text", None) or ""
        if not text and response.candidates:
            part = response.candidates[0].content.parts[0]
            text = getattr(part, "text", "") or ""
        if text and ("OK" in text or "ok" in text or "接続" in text):
            return {"ok": True, "message": "Gemini API に接続できました。TAM/SAM/SOM 推計が利用できます。"}
        return {"ok": True, "message": f"Gemini API 応答を取得しました: {text.strip()[:80]}..."}
    except Exception as e:
        err = str(e).strip()
        if "429" in err or "quota" in err.lower() or "exceeded" in err.lower():
            return {"ok": False, "message": "APIキーは有効ですが、利用枠（クォータ）を超えています。しばらく待つか、Google AI Studio のプラン・利用状況を確認してください。"}
        if "API_KEY" in err or "invalid" in err.lower() or "403" in err or "401" in err:
            return {"ok": False, "message": f"APIキーが無効か拒否されました: {err[:200]}"}
        if "404" in err or "not found" in err.lower():
            return {"ok": False, "message": f"指定したモデルが見つかりません: {err[:150]}"}
        return {"ok": False, "message": f"接続エラー: {err[:200]}"}


def _parse_gemini_response(text: str) -> Optional[MarketSizeEstimate]:
    """Gemini の応答テキストから TAM/SAM/SOM と根拠を抽出する。"""
    if not text or not text.strip():
        return None
    text = text.strip()
    tam = sam = som_pct = None
    reasoning = ""

    # 数値の抽出（億円 or ％）
    tam_m = re.search(r"TAM[（(]?億円[）)]?\s*[：:]\s*([0-9,.]+)", text, re.IGNORECASE)
    if tam_m:
        tam = float(tam_m.group(1).replace(",", ""))
    sam_m = re.search(r"SAM[（(]?億円[）)]?\s*[：:]\s*([0-9,.]+)", text, re.IGNORECASE)
    if sam_m:
        sam = float(sam_m.group(1).replace(",", ""))
    som_m = re.search(r"SOM[（(]?.*?[％%]?[）)]?\s*[：:]\s*([0-9,.]+)\s*[％%]?", text, re.IGNORECASE)
    if som_m:
        som_pct = float(som_m.group(1).replace(",", ""))
    if som_pct is None:
        som_m = re.search(r"獲得シェア[（(]?％[）)]?\s*[：:]\s*([0-9,.]+)", text)
        if som_m:
            som_pct = float(som_m.group(1).replace(",", ""))

    # 算出根拠
    reason_m = re.search(r"算出根拠[：:]\s*(.+?)(?=\n\n|\nTAM|\nSAM|\nSOM|$)", text, re.DOTALL | re.IGNORECASE)
    if reason_m:
        reasoning = reason_m.group(1).strip().replace("\n", " ")[:500]
    if not reasoning:
        reasoning = text[:400].replace("\n", " ")

    if tam is None or sam is None or som_pct is None:
        return None
    som_ratio = som_pct / 100.0 if som_pct <= 100 else som_pct  # 既に0-1ならそのまま
    if som_ratio > 1:
        som_ratio = som_ratio / 100.0
    return MarketSizeEstimate(tam=tam, sam=sam, som_ratio=som_ratio, reasoning=reasoning or "（根拠なし）")


def estimate_market_sizes_gemini(
    company_name: str,
    business_desc: str | None = None,
) -> MarketSizeEstimate:
    """
    Gemini API で TAM/SAM/SOM を推計する。
    API キーが未設定または失敗時はダミー値を返す。
    """
    if not GEMINI_API_KEY:
        return _estimate_dummy(company_name)

    prompt = f"""以下について、日本国内の市場規模を億円単位で推計し、指定の形式のみで答えてください。

企業名: {company_name}
{f'事業概要: {business_desc}' if business_desc else ''}

【回答形式（この形式だけを守ること）】
TAM（億円）: [数値のみ]
SAM（億円）: [数値のみ]
SOM（獲得シェア%）: [数値のみ、例: 5]
算出根拠: [1〜2文で簡潔に]
"""

    try:
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        text = getattr(response, "text", None) or ""
        if not text and response.candidates:
            part = response.candidates[0].content.parts[0]
            text = getattr(part, "text", "") or ""
        parsed = _parse_gemini_response(text)
        if parsed:
            return parsed
    except Exception:
        pass
    return _estimate_dummy(company_name)


def _estimate_dummy(company_name: str) -> MarketSizeEstimate:
    """API 未使用時のダミー推計。"""
    base_tam = 5000.0
    tam = base_tam + (hash(company_name) % 1000)
    sam = tam * 0.3
    som_ratio = 0.15
    reasoning = (
        f"{company_name} の主要事業を想定したダミー値です。"
        " .env に GOOGLE_API_KEY または GEMINI_API_KEY を設定すると Gemini で推計します。"
    )
    return MarketSizeEstimate(tam=tam, sam=sam, som_ratio=som_ratio, reasoning=reasoning)


def estimate_market_sizes(
    company_name: str,
    business_desc: str | None = None,
) -> MarketSizeEstimate:
    """
    メイン入口。Gemini API キーがあれば API で推計、なければダミー値を返す。
    """
    return estimate_market_sizes_gemini(company_name, business_desc)
