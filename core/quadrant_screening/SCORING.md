# 4象限スコアリング（100点満点）

## セクター（最大15点）

- 短期（21営業日）: 業種ETF騰落率 − TOPIX（`1306.T`）超過幅 × 4（上限12点）
- 中期（63営業日）もTOPIX超過なら **+3点**
- 超過≤0は0点。ラベル: 10点以上=良 / 5点以上=中立 / それ以外=弱

## 需給（最大25点）

| 内訳 | 条件 |
|------|------|
| 出来高（最大15） | 当日÷5日平均 ≥1.25 → 15点 / ≥1.15 → 8点 |
| 信用（最大10） | 買残÷売残 ≤1.0 → 10点 / ≤2.5 → 6.5点 / ≤6.0 → 2.5点 |

信用データ: 環境変数 `JQUANTS_REFRESH_TOKEN` 設定時に J-Quants 週次信用残。未設定時は `.cache/margin_ratios.json` のキャッシュのみ（無ければ0点）。

## テクニカル（最大40点）

| 内訳 | 条件 |
|------|------|
| 25MA上 | +8点 |
| 75MA上 | +7点 |
| パターン | `data/pattern_weights.json` の検証重み × 25（ベイズ縮小、複数時は最大1パターン） |

パターン重み更新: `python scripts/update_pattern_weights.py [--local-dir PATH]`

## ファンダ（最大20点・4軸×5点）

1. **収益性**: ROE段階（8/12/18%）+ 営業利益率10%超で+1
2. **成長**: 利益/売上成長率（5/15/30%）
3. **割安**: EPS×許容PERに対する割安度%（5/15/30%）
4. **健全性**: D/E（0.5/1.5/3.0以下で段階、欠損時2点）

## スクリーニング必須条件（点数外）

- 株価≥500円、20日平均出来高≥30万株
- **75MA上**（エンジン・integrate共通）

`verify_quadrant_filters.py` の「100万円加重%」列は、各シグナルに **同一元本100万円** を投下したポートフォリオの実現リターン（旧100株加重は廃止）。

## 定期実行コマンド

```powershell
python -m pytest tests/ -q
python scripts/update_pattern_weights.py
python scripts/run_quadrant_screen.py --top 5
python scripts/verify_quadrant_filters.py --max-signals 100
```

パターン名は stock-daytrade 向け名称を `SIGNAL_TO_QUADRANT_PATTERN`（`pattern_weights.py`）で4象限名に集約してから重み付けする。

## 未実装・要準備（2026-05-28 時点）

| 項目 | 状態 | 必要なもの |
|------|------|------------|
| 信用倍率スコア | コード済・データ0件 | `.env` に `JQUANTS_REFRESH_TOKEN`（[J-Quants](https://jpx-jquants.com/) 無料登録） |
| パターン重みの完全同期 | 集計済（746件→5象限名） | stock-daytrade と4象限の検出ロジック統一が理想 |
| 全件フィルタ検証 | 部分実行のみ（60件） | `verify_quadrant_filters.py` 全746件は yfinance 取得で30分〜 |
| CI自動更新 | 未設定 | GitHub Actions + シークレット + workflow 追加 |
