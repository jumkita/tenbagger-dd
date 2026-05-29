# 4象限スクリーニングの買いパターン（本家準拠）

`core.quadrant_screening.technical.detect_buy_patterns` は、`jumkita/stock-daytrade` の `logic.py` にある **`detect_all_patterns` の買い側**に揃えています。

## 付与順（本家と同じ）

1. **`BUY_PATTERNS_TALIB`** … TA-Lib の12ラベル（`陽のつつみ線` と `包み線` はどちらも `CDLENGULFING`）
2. **`_custom_buy_patterns` 相当** … 二本たくり線・陰線後の陽線・ピンバー・スパイクロー・リバーサルロー・インサイドバー・包み線
3. **`signal_scanner.CandlePatterns`** … 明けの明星・赤三兵・二本たくり線（抜粋実装は `stock_daytrade_candle_patterns.py`）
4. **三空叩き込み** … 連続ギャップ判定

同一ラベルが複数ルートで立つ場合は、返却リストでは **重複を1回にまとめます**（スコアの二重カウントは `score_patterns` 側でも防いでいます）。

## TA-Lib のインストール

`requirements.txt` に `TA-Lib` を追加済みです。

### GitHub Actions（Linux）

`.github/workflows/tests.yml` と `.github/workflows/pattern-weights.yml` では、`scripts/ci_install_ta_lib.sh` で **TA-Lib 0.4.0 の C ライブラリをソースからビルド**し `/usr/local` に入れてから `pip install -r requirements.txt` します。SourceForge の取得に失敗した場合はログを確認し、再実行またはミラー検討ください。

### ローカル

- **Linux**: 上記スクリプトを参考にするか、`pip install TA-Lib` の manylinux ホイールで足りる場合があります。
- **Windows**: 公式の TA-Lib C ライブラリと互換のビルドが必要な場合があります。`pip install TA-Lib` が失敗したら、環境向けの手順（例: 非公式ホイール）を参照してください。

TA-Lib が import できない環境では、**TA-Lib 分だけスキップ**し、カスタム・CandlePatterns・三空はそのまま動きます。

## 重み JSON との対応

`pattern_weights.json` のキーは従来の短い集合のままにし、`pattern_weights.canonical_pattern_name` で本家ラベル（例: `上げ三法`）を既存キー（例: `上昇三法`）に寄せています。

**整合テスト:** `tests/test_pattern_weights.py` で、`SIGNAL_TO_QUADRANT_PATTERN` のすべての値が JSON に存在することを保証しています。

## `update_pattern_weights.py`

`stock-daytrade` の `daily_buy_signals_*.json` を集計し、`canonical_pattern_name` 後のキーで統計を作って JSON を更新します。

- `--max-files N` … 日付昇順の **末尾 N ファイル**だけを読む（GitHub API 負荷・実行時間の抑制）。`verify_quadrant_filters.py` にも `--max-signal-files N` を追加済み。
- `--dry-run` … 標準出力に JSON を出すのみ（ファイルは書かない）。

