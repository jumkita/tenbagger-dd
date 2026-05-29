from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from core.data_loader import (
    load_tickers_auto,
    filter_standard_growth_first,
    list_csv_with_counts,
)
from core.market_data import build_market_data, fetch_market_data_for_ticker
from core.screening import screen_candidates, screening_stats
from core.ai_assistant import estimate_market_sizes, verify_gemini_connection
import yfinance as yf

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
MAX_TICKERS_DEFAULT = 600  # 初回負荷軽減のため上限（テンバガー候補は時価総額小さい側に多い）


@st.cache_data(show_spinner=True)
def load_and_build_market_data(
    max_tickers: int,
    prefer_standard_growth: bool,
    use_folder_csv_only: bool,
    folder_csv_filename: str | None,
) -> tuple[pd.DataFrame, str]:
    """
    銘柄一覧をJPXまたはCSVから取得し、yfinanceでマーケットデータを取得してキャッシュ。
    use_folder_csv_only=True のときは data フォルダの指定CSVを銘柄一覧に使う。
    """
    tickers_df, source = load_tickers_auto(
        DATA_DIR,
        use_folder_csv_only=use_folder_csv_only,
        folder_csv_filename=folder_csv_filename,
    )
    if tickers_df.empty:
        return pd.DataFrame(), "none"
    if prefer_standard_growth:
        tickers_df = filter_standard_growth_first(tickers_df, max_tickers)
    else:
        tickers_df = tickers_df.head(max_tickers)
    tickers = tickers_df["code"].tolist()
    market_df = build_market_data(tickers)
    merged = market_df.merge(tickers_df, left_on="ticker", right_on="code", how="left")
    if use_folder_csv_only or source == "csv":
        label = "CSV（data フォルダの銘柄一覧）"
    else:
        label = "JPX（東証銘柄一覧）"
    return merged, label


def run_dashboard() -> None:
    st.title("テンバガー全頭スクリーニング & AI連動TAM/SAM/SOMダッシュボード")

    with st.sidebar:
        use_folder_csv = st.checkbox(
            "銘柄一覧にフォルダのCSVを使う（data フォルダ）",
            value=False,
            help="ONにするとJPXは使わず、下で選んだCSVのみを銘柄一覧に使います。",
        )
        csv_with_counts = list_csv_with_counts(DATA_DIR)
        folder_csv_options = [fn for fn, _ in csv_with_counts]
        selected_csv: str | None = None
        if use_folder_csv:
            if not folder_csv_options:
                st.warning("data フォルダに .csv がありません。tickers.csv 等を入れてください。")
            else:
                # 行数が多いCSVを先頭に表示し、デフォルトで選択されるようにする
                default_idx = 0
                selected_csv = st.selectbox(
                    "使用するCSV（銘柄一覧）",
                    options=folder_csv_options,
                    index=default_idx,
                    format_func=lambda x: f"{x} （{next((c for fn, c in csv_with_counts if fn == x), 0)} 件）",
                    help="選んだファイルの行数＝取得する銘柄数です。4件しか出ない場合は、行数が多いCSVを選んでください。",
                )
        max_tickers = st.number_input(
            "取得する銘柄数（多すぎると初回に時間がかかります）",
            min_value=50,
            max_value=4000,
            value=MAX_TICKERS_DEFAULT,
            step=50,
        )
        if use_folder_csv and folder_csv_options:
            sel_count = next((c for fn, c in csv_with_counts if fn == selected_csv), 0)
            st.caption(f"※選択中: **{selected_csv}** → 最大 **{sel_count}** 銘柄取得されます。")
        prefer_sg = st.checkbox(
            "スタンダード・グロースを優先（JPX使用時のみ。テンバガー候補が増えやすい）",
            value=True,
        )
        st.divider()
        st.markdown("**スクリーニング条件**")
        min_mc = st.number_input("時価総額 下限（億円）", min_value=0, value=50, step=10)
        max_mc = st.number_input("時価総額 上限（億円）", min_value=10, value=300, step=50)
        min_yoy = st.number_input("売上高YoY 下限（%）", min_value=-100, value=20, step=5)
        require_yoy = st.checkbox(
            "売上高YoY条件を必須にする（OFFだと時価総額のみでフィルタ。日本株はYoYが取れないことが多い）",
            value=False,
            help="yfinanceでは日本株の売上高が取得できない銘柄が多く、ONのままだと0件になりがちです。",
        )
        st.divider()
        st.markdown("**Gemini API**")
        if st.button("接続確認（Gemini）"):
            result = verify_gemini_connection()
            if result["ok"]:
                st.success(result["message"])
            else:
                st.error(result["message"])

    with st.spinner("銘柄一覧を取得し、株価・財務データを取得しています…"):
        market_df, data_source = load_and_build_market_data(
            max_tickers, prefer_sg, use_folder_csv, selected_csv if use_folder_csv else None
        )

    if market_df.empty:
        st.warning(
            "銘柄データが取得できませんでした。\n\n"
            "・JPXの東証銘柄一覧ページに接続できない場合、`data` フォルダに "
            "`tickers.csv`（列: code, name）を用意してください。\n"
            "・**下の「銘柄コードを直接入力」で任意の銘柄を入力すれば、計算・検証できます。**"
        )
        data_source = "なし"
        candidates_df = pd.DataFrame()
    else:
        st.caption(f"データソース: **{data_source}**（取得済み銘柄数: {len(market_df)}）")

    if not market_df.empty:
        # データ取得の検証用ビュー
        with st.expander("データ取得の検証（market_df の中身を確認）", expanded=False):
            st.write(
                "下表は yfinance から取得した生データの一部です。"
                " ticker 数や時価総額・売上高の欠損状況を確認できます。"
            )
            st.write(
                {
                    "ユニークticker数": int(market_df["ticker"].nunique()),
                    "時価総額（億円）取得済み": int(market_df["market_cap_oku"].notna().sum())
                    if "market_cap_oku" in market_df.columns
                    else 0,
                    "売上高（最新期）取得済み": int(market_df["revenue_latest"].notna().sum())
                    if "revenue_latest" in market_df.columns
                    else 0,
                    "売上高（前期）取得済み": int(market_df["revenue_prev"].notna().sum())
                    if "revenue_prev" in market_df.columns
                    else 0,
                }
            )
            sample_cols = [
                c
                for c in [
                    "ticker",
                    "market_cap_oku",
                    "market_cap_jpy",
                    "revenue_latest_oku",
                    "revenue_prev_oku",
                ]
                if c in market_df.columns
            ]
            if sample_cols:
                st.dataframe(market_df[sample_cols].head(50))
            else:
                st.dataframe(market_df.head(50))

        st.subheader("① 一次スクリーニング（テンバガーの種探し）")
        cond_caption = f"条件：時価総額 {min_mc}〜{max_mc} 億円"
        if require_yoy:
            cond_caption += f"、売上高 YoY +{min_yoy}% 以上"
        else:
            cond_caption += "（売上高YoYは見ず、時価総額のみ）"
        st.caption(cond_caption)

        stats = screening_stats(market_df, min_mc_oku=float(min_mc), max_mc_oku=float(max_mc), min_yoy=float(min_yoy))
        st.markdown(
            f"取得 **{stats['total']}** 件のうち → "
            f"時価総額該当: **{stats['mc_in_range']}** 件 / "
            f"売上高YoY取得済: **{stats['yoy_available']}** 件 / "
            f"YoY+{min_yoy}%以上: **{stats['yoy_in_range']}** 件 → "
            f"**両方満たす: {stats['both']}** 件"
        )
        if stats["yoy_available"] == 0 and require_yoy:
            st.warning("売上高が1件も取得できていません。サイドバーで「売上高YoY条件を必須にする」をOFFにすると、時価総額条件のみでスクリーニングできます。")

        candidates_df = screen_candidates(
            market_df,
            min_mc_oku=float(min_mc),
            max_mc_oku=float(max_mc),
            min_yoy=float(min_yoy),
            require_revenue_yoy=require_yoy,
        )
        display_cols = [c for c in ["name", "ticker", "market_cap_oku", "revenue_yoy", "revenue_latest_oku", "revenue_prev_oku"] if c in candidates_df.columns]
        if not display_cols:
            display_cols = list(candidates_df.columns)
        st.dataframe(candidates_df[display_cols] if display_cols else candidates_df)

        if candidates_df.empty:
            st.info(
                "条件を満たす銘柄がありません。\n\n"
                "・**銘柄一覧にフォルダのCSVを使う**をONにすると、data フォルダのCSVだけが銘柄一覧になります。\n"
                "・**売上高YoY条件を必須にする**をOFFにすると、時価総額だけの条件で表示されます（日本株は売上高が取れないことが多いです）。\n"
                "・下の「銘柄コードを直接入力」で任意の銘柄を指定すれば、計算・検証できます。"
            )
    else:
        candidates_df = pd.DataFrame()

    st.subheader("銘柄コードを直接入力して検証")
    manual_code = st.text_input(
        "銘柄コード（4桁または XXXX.T）",
        placeholder="例: 7203 または 7203.T",
        key="manual_ticker_input",
    )
    col_btn, col_clear = st.columns(2)
    with col_btn:
        use_manual = st.button("この銘柄で計算・検証する")
    with col_clear:
        clear_manual = st.button("直接入力の銘柄をクリア")
    if clear_manual and "manual_selected" in st.session_state:
        del st.session_state["manual_selected"]
        if "ai_estimate" in st.session_state:
            st.session_state["ai_estimate"] = None
        st.rerun()
    if use_manual and manual_code:
        raw = manual_code.strip().upper().replace(".T", "").replace(" ", "")
        if not raw or len(raw) < 4:
            st.error("銘柄コードを4桁以上（例: 7203 または 130A）で入力してください。")
        else:
            ticker = raw + ".T"
            with st.spinner("銘柄データを取得中…"):
                row = fetch_market_data_for_ticker(ticker)
                info = yf.Ticker(ticker).info
                row["name"] = info.get("shortName") or info.get("longName") or ticker
                st.session_state["manual_selected"] = row
                st.session_state["ai_estimate"] = None
            st.success(f"**{row['name']}**（{ticker}）を読み込みました。")
            st.rerun()

    # 選択中の銘柄: 直接入力で読み込んだ行 または スクリーニング結果から選択
    selected_row = None
    if st.session_state.get("manual_selected"):
        selected_row = st.session_state["manual_selected"]
    elif not candidates_df.empty:
        display_options = candidates_df["name"] + " (" + candidates_df["ticker"] + ")"
        selected_label = st.selectbox("深掘りする銘柄を選択", options=display_options)
        if selected_label:
            idx = display_options[display_options == selected_label].index[0]
            sr = candidates_df.loc[idx]
            selected_row = sr.to_dict() if hasattr(sr, "to_dict") else dict(sr)

    if selected_row is None:
        st.caption("上で銘柄コードを入力して「この銘柄で計算・検証する」を押すか、スクリーニング結果から銘柄を選んでください。")
        return

    st.subheader("② AI推計アシスト（ダミー実装）")
    company_name = selected_row.get("name") or selected_row.get("ticker", "")
    if st.session_state.get("manual_selected"):
        st.write(f"選択中の銘柄（直接入力）：**{company_name}**（{selected_row['ticker']}）")
    else:
        st.write(f"選択中の銘柄：**{company_name}**（{selected_row['ticker']}）")

    if "ai_estimate" not in st.session_state:
        st.session_state["ai_estimate"] = None

    if st.button("AIでTAM/SAM/SOM初期推計を取得（Gemini）"):
        with st.spinner("Gemini API で推計中…"):
            st.session_state["ai_estimate"] = estimate_market_sizes(company_name)
        st.success("TAM/SAM/SOM を取得しました。下のスライダーで前提を微調整できます。")

    estimate = st.session_state.get("ai_estimate")

    # TAM/SAM/SOM が取れているか検証用に表示
    with st.expander("TAM / SAM / SOM 取得結果の検証", expanded=True):
        if estimate is None:
            st.warning("未取得です。上で「AIでTAM/SAM/SOM初期推計を取得（Gemini）」を押してください。")
        else:
            st.success("TAM・SAM・SOM は取得済みです。")
            v1, v2, v3 = st.columns(3)
            v1.metric("TAM（億円）", f"{estimate.tam:,.0f}")
            v2.metric("SAM（億円）", f"{estimate.sam:,.0f}")
            v3.metric("SOM（シェア）", f"{estimate.som_ratio * 100:.1f}%")
            st.caption("算出根拠")
            st.text(estimate.reasoning)

    st.subheader("③ TAM/SAM/SOM & バリュエーション・シミュレーター")

    if estimate is None:
        st.info("まず「AIでTAM/SAM/SOM初期推計を取得（Gemini）」ボタンを押してください。")
        return

    col1, col2 = st.columns(2)
    with col1:
        tam_input = st.number_input(
            "TAM（最大市場規模・億円）",
            min_value=0.0,
            value=float(estimate.tam),
            step=100.0,
        )
        sam_input = st.number_input(
            "SAM（ターゲット市場規模・億円）",
            min_value=0.0,
            value=float(estimate.sam),
            step=50.0,
        )
        som_share_pct = st.slider(
            "SOM（現実的な獲得シェア・%）",
            min_value=0.0,
            max_value=100.0,
            value=float(estimate.som_ratio * 100.0),
            step=1.0,
        )

    with col2:
        op_margin_pct = st.slider(
            "想定営業利益率・%",
            min_value=0.0,
            max_value=60.0,
            value=20.0,
            step=1.0,
        )
        target_per = st.number_input(
            "ターゲット PER",
            min_value=1.0,
            value=25.0,
            step=0.5,
        )

    # 計算ロジック
    som_ratio = som_share_pct / 100.0
    op_margin_ratio = op_margin_pct / 100.0

    expected_sales = sam_input * som_ratio  # 想定売上高（億円）
    operating_profit = expected_sales * op_margin_ratio  # 営業利益（億円）
    after_tax_profit = operating_profit * 0.7  # 実効税率 30% を想定
    future_market_cap = after_tax_profit * target_per  # 将来時価総額（億円ベース想定）

    # 現在時価総額（億円）。market_cap_jpy があれば円→億円、なければ market_cap_oku を使用
    current_mc_oku = selected_row.get("market_cap_oku")
    if current_mc_oku is None and selected_row.get("market_cap_jpy") is not None:
        current_mc_oku = selected_row["market_cap_jpy"] / 1e8
    upside_multiple = None
    if current_mc_oku is not None and current_mc_oku > 0:
        upside_multiple = future_market_cap / current_mc_oku

    st.markdown("#### シミュレーション結果")
    kpi_cols = st.columns(4)
    kpi_cols[0].metric("想定売上高（億円）", f"{expected_sales:,.0f}")
    kpi_cols[1].metric("税後利益（億円）", f"{after_tax_profit:,.0f}")
    kpi_cols[2].metric("将来想定時価総額（億円換算）", f"{future_market_cap:,.0f}")
    if upside_multiple is not None:
        kpi_cols[3].metric("現在比アップサイド倍率", f"{upside_multiple:,.1f}倍")
    else:
        kpi_cols[3].metric("現在比アップサイド倍率", "N/A")

    if current_mc_oku is not None:
        st.caption(f"現在の時価総額: {current_mc_oku:,.0f} 億円 → 想定将来時価総額: {future_market_cap:,.0f} 億円")

