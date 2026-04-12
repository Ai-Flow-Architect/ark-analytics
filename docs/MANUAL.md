# ark-analytics 運用マニュアル

GA4×BigQuery×AIの分析基盤を使った日常運用手順です。

---

## 目次

1. [システム構成図](#1-システム構成図)
2. [日次データ更新（自動）](#2-日次データ更新自動)
3. [自然言語QA（サービス③）](#3-自然言語qasービス③)
4. [改善施策スコアリング（サービス④）](#4-改善施策スコアリングサービス④)
5. [月次レポート生成（サービス②）](#5-月次レポート生成サービス②)
6. [Looker Studioダッシュボード](#6-looker-studioダッシュボード)
7. [トラブルシューティング](#7-トラブルシューティング)

---

## 1. システム構成図

```
GA4（ark-hd.co.jp）
    ↓ 自動エクスポート（毎日）
BigQuery: analytics_386840839.events_*
    ↓ 日次バッチ（毎朝4:00 cron）
  staging.stg_sessions
    ↓
  marts.daily_kpi_summary      ← KPIダッシュボード用
  marts.conversion_funnel_daily ← ファネル分析用
  marts.channel_kpi_monthly    ← チャネル別分析用
  marts.page_performance       ← ページ改善用
    ↓
  reports.rpt_looker_main      ← Looker Studio接続用
    ↓
Python CLI
  ├── AI自然言語QA         ← 「どのページが？」などの質問に即回答
  ├── 改善施策スコアリング   ← 優先順位TOP5を自動算出
  └── 月次レポート自動生成   ← PDF/HTMLレポートをメール配信
```

---

## 2. 日次データ更新（自動）

### 設定済み cron

毎朝4:00に自動実行されます。**手動操作不要。**

```
0 4 * * * /home/kosuke_igarashi/projects/ark-analytics/scripts/daily_refresh.sh
```

### ログの確認方法

```bash
# 今日のログを確認
cat /home/kosuke_igarashi/projects/ark-analytics/logs/refresh_$(date '+%Y%m%d').log

# 最新ログをリアルタイム確認
tail -f /home/kosuke_igarashi/projects/ark-analytics/logs/refresh_$(date '+%Y%m%d').log
```

### 手動実行（急ぎの場合）

```bash
cd /home/kosuke_igarashi/projects/ark-analytics
bash scripts/daily_refresh.sh
```

### 更新されるテーブル

| テーブル | 更新内容 |
|---------|---------|
| `staging.stg_sessions` | GA4生データの整形・集約 |
| `marts.daily_kpi_summary` | 日次KPI（セッション・CVR等） |
| `marts.conversion_funnel_daily` | コンバージョンファネル |
| `marts.channel_kpi_monthly` | チャネル別月次集計 |
| `marts.page_performance` | ページ別パフォーマンス |

---

## 3. 自然言語QA（サービス③）

GA4データに自然言語で質問できます。BQからデータを自動取得してAIが回答します。

### 使い方（コマンドライン）

```bash
cd /home/kosuke_igarashi/projects/ark-analytics

# 質問を直接指定
python3 main.py --report-type qa --question "どのページが一番離脱が多いですか？"

# 対話モード（複数質問を連続して行う場合）
python3 main.py --report-type qa
```

### 対話モードの操作

```
=== GA4 AI自然言語アナリスト ===
質問を入力してください（'exit' で終了）

質問> どのページが一番訪問が多いですか？
（回答が表示されます）

質問> 先月のコンバージョン率はどうでしたか？
（回答が表示されます）

質問> exit
```

### 質問例

| カテゴリ | 質問例 |
|---------|-------|
| ページ分析 | 「どのページが一番離脱が多いですか？」 |
| チャネル分析 | 「どの流入経路がCVRが高いですか？」 |
| ファネル分析 | 「フォームのどこで一番離脱しますか？」 |
| KPI確認 | 「今月のセッション数の傾向は？」 |
| 総合分析 | 「今週の改善ポイントをまとめてください」 |

### 回答の精度について

- 実際のBQデータを参照して回答します（推測ではありません）
- 400文字以内で簡潔に回答します
- 数字を必ず引用し、改善提案を1つ以上含みます

---

## 4. 改善施策スコアリング（サービス④）

BQデータを分析し、改善施策をスコアリングして優先順位TOP5を出力します。

### 使い方

```bash
cd /home/kosuke_igarashi/projects/ark-analytics
python3 main.py --report-type scorer
```

### 出力例

```
=== 改善施策 優先順位スコアリング ===

順位 | 対象            | 課題           | アクション              | 優先度 | 期待効果
 1  | /              | CTAクリック率低 | CTAボタンを目立つ位置に  |    12 | 問合せ数15%向上
 2  | /contact/      | フォーム開始率低 | 入力項目削減             |    11 | CVR5%→8%
...
```

### スコア計算式

```
優先度スコア = インパクト × 2 + 実行可能性 - 工数
```

| スコア軸 | 5点 | 1点 |
|---------|-----|-----|
| インパクト | CV・訪問数への影響大 | ほぼ影響なし |
| 工数 | 実装コスト高 | すぐできる |
| 実行可能性 | GA4/CSS変更で対応可 | 大規模改修必要 |

### 定期実行の目安

- 月次（月初）: 今月の改善優先度の決定
- 施策実施後: 効果測定の参考に

---

## 5. 月次レポート生成（サービス②）

月次のWebサイト分析レポートを自動生成し、メール配信・Google Drive保存します。

### 使い方

```bash
cd /home/kosuke_igarashi/projects/ark-analytics

# 今月（先月分）のレポート生成
python3 main.py --report-type monthly

# 特定月のレポート生成
python3 main.py --report-type monthly --month 2026-04

# ドライラン（メール送信なし・プレビューのみ）
python3 main.py --report-type monthly --dry-run --month 2026-04
```

### レポートに含まれる内容

**経営層向けサマリー**:
- 月間KPI（セッション・CVR・問合せ数）と目標達成率
- 前月比分析
- AIによる総評・良かった点TOP3・改善点TOP3
- 来月の推奨アクション3つ

**実務担当向け詳細**:
- チャネル別分析
- ファネル分析（どのステップで離脱が多いか）
- 改善優先度の高いページTOP3
- A/Bテスト提案

### 配信先の設定

`config/settings.yaml` で設定：

```yaml
report:
  recipients:
    - メールアドレス1@example.com
    - メールアドレス2@example.com
```

---

## 6. Looker Studioダッシュボード

詳細は [LOOKER_STUDIO_SETUP.md](LOOKER_STUDIO_SETUP.md) を参照してください。

接続先テーブル: `ark-hd-analytics.reports.rpt_looker_main`

---

## 7. トラブルシューティング

### Q: cron実行でデータが更新されない

1. ログを確認する
```bash
cat /home/kosuke_igarashi/projects/ark-analytics/logs/refresh_$(date '+%Y%m%d').log
```

2. Google認証が切れていないか確認
```bash
gcloud auth application-default print-access-token
```

3. 切れていた場合、再認証
```bash
gcloud auth application-default login --no-launch-browser
```

---

### Q: QA・Scorer実行時に `OPENAI_API_KEY が設定されていません` と出る

```bash
# 環境変数を確認
echo $OPENAI_API_KEY

# ~/.bashrc に設定されているか確認
grep OPENAI_API_KEY ~/.bashrc
```

---

### Q: BQクエリが失敗する（`Access Denied` エラー）

```bash
# プロジェクトとADCを確認
gcloud config get-value project
gcloud auth application-default print-access-token 2>&1 | head -5
```

---

### Q: データが古い / 最新データが反映されていない

GA4からBQへのエクスポートは通常24〜48時間かかります。  
`events_*` テーブルのパーティションは `_TABLE_SUFFIX` = `YYYYMMDD` 形式です。

最新データがいつまであるか確認：
```sql
SELECT MAX(_TABLE_SUFFIX) AS latest_date
FROM `ark-hd-analytics.analytics_386840839.events_*`
```

---

## 付録

### ファイル構成

```
ark-analytics/
├── config/
│   └── settings.yaml          # GCP・GA4・レポート設定
├── sql/
│   ├── staging/               # データ整形SQL
│   ├── marts/                 # 分析用テーブルSQL
│   └── reports/               # Looker Studio用SQL
├── src/
│   ├── natural_language_qa.py # サービス③ QA
│   ├── priority_scorer.py     # サービス④ スコアリング
│   ├── data_collector.py      # BQデータ取得
│   ├── ai_analyzer.py         # GPT分析
│   ├── prompt_builder.py      # プロンプト生成
│   ├── report_formatter.py    # レポート整形
│   └── delivery.py            # メール・Drive配信
├── scripts/
│   └── daily_refresh.sh       # 日次更新cronスクリプト
├── docs/
│   ├── MANUAL.md              # このファイル
│   ├── GTM_TAGS.md            # GTMタグコード集
│   └── LOOKER_STUDIO_SETUP.md # Looker Studio設定手順
├── logs/                      # cronログ（自動生成）
├── main.py                    # エントリーポイント
└── requirements.txt           # 依存パッケージ
```

### よく使うBQクエリ

```sql
-- 直近7日のKPI確認
SELECT report_date, sessions, contact_form_submissions, ROUND(overall_cvr*100,2) AS cvr_pct
FROM `ark-hd-analytics.marts.daily_kpi_summary`
ORDER BY report_date DESC
LIMIT 7;

-- ページ別パフォーマンス TOP10
SELECT page_path, SUM(pageviews) AS pv, ROUND(AVG(cta_click_rate)*100,1) AS cta_ctr
FROM `ark-hd-analytics.marts.page_performance`
GROUP BY page_path
ORDER BY pv DESC
LIMIT 10;
```
