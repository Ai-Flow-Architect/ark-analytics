# Looker Studio ダッシュボード 接続・設定手順

ark-hd.co.jpのGA4分析データをLooker Studioで可視化する手順です。

---

## 接続するBigQueryテーブル

| テーブル | 用途 |
|---------|------|
| `ark-hd-analytics.reports.rpt_looker_main` | メインダッシュボード（KPI+ファネル統合） |
| `ark-hd-analytics.marts.daily_kpi_summary` | 日次KPIトレンド |
| `ark-hd-analytics.marts.channel_kpi_monthly` | チャネル別分析 |
| `ark-hd-analytics.marts.page_performance` | ページ別パフォーマンス |
| `ark-hd-analytics.marts.conversion_funnel_daily` | ファネル分析 |

---

## STEP 1: Looker Studioにアクセス

1. [https://lookerstudio.google.com/](https://lookerstudio.google.com/) にアクセス
2. ark-hd.co.jpのGoogleアカウント（BQ閲覧権限があるアカウント）でログイン

---

## STEP 2: 新しいレポートを作成

1. 「作成」→「レポート」をクリック
2. 「データをレポートに追加」画面が表示される

---

## STEP 3: BigQueryに接続

1. コネクタ一覧から「**BigQuery**」を選択
2. 以下を選択：
   - **プロジェクト**: `ark-hd-analytics`
   - **データセット**: `reports`
   - **テーブル**: `rpt_looker_main`
3. 「追加」をクリック

> **権限エラーが出た場合**: BQ上でLooker Studioのサービスアカウントに閲覧権限が必要です。後述の「権限設定」を参照してください。

---

## STEP 4: 追加データソースの接続

同じ手順で以下のテーブルも追加接続します（「データソースを追加」から）：

| データセット | テーブル名 |
|------------|----------|
| `marts` | `daily_kpi_summary` |
| `marts` | `channel_kpi_monthly` |
| `marts` | `page_performance` |
| `marts` | `conversion_funnel_daily` |

---

## STEP 5: 推奨ダッシュボード構成

### ページ1: KPIサマリー（経営層向け）

**スコアカード（4枚）**:
- 月間セッション（`SUM(sessions)`）
- 月間問合せ数（`SUM(contact_form_submissions)`）
- 全体CVR（`AVG(overall_cvr)` → パーセント表示）
- エンゲージメント率（`AVG(engagement_rate)` → パーセント表示）

データソース: `daily_kpi_summary`  
日付フィルター: `report_date` で期間指定

**折れ線グラフ**:
- 縦軸: sessions、横軸: report_date
- セッション数の推移を可視化

---

### ページ2: ファネル分析

**棒グラフ（ファネル形式）**:
- 各ステップの平均値を棒グラフで表示

データソース: `conversion_funnel_daily`

| 軸 | フィールド |
|---|----------|
| ステップ1 | `AVG(step1_sessions)` |
| ステップ2 | `AVG(step2_service_view)` |
| ステップ3 | `AVG(step3_contact_page)` |
| ステップ4 | `AVG(step4_form_start)` |
| ステップ5 | `AVG(step5_submission)` |

**ステップ間の遷移率スコアカード**:
- ステップ1→2: `AVG(step1_to_2_rate)`
- ステップ2→3: `AVG(step2_to_3_rate)`
- ステップ3→4: `AVG(step3_to_4_rate)`
- ステップ4→5: `AVG(step4_to_5_rate)`

---

### ページ3: チャネル別分析

**棒グラフ**:
- 縦軸: sessions、横軸（ディメンション）: channel_grouping
- データソース: `channel_kpi_monthly`

**表**:
- ディメンション: channel_grouping, report_month
- 指標: sessions, conversion_rate, engagement_rate

---

### ページ4: ページパフォーマンス

**表**:
- ディメンション: page_path
- 指標: SUM(pageviews), AVG(avg_time_on_page_sec), AVG(scroll_90pct_rate), AVG(cta_click_rate), SUM(conversions_from_page)
- データソース: `page_performance`

---

### ページ5: 統合ダッシュボード（メインページ）

データソース: `rpt_looker_main`（KPI+ファネル統合ビュー）

**含まれるフィールド**:
- report_date, sessions, pageviews, engagement_rate
- contact_form_submissions, overall_cvr
- step1_sessions ～ step5_submission
- step1_to_2_rate ～ step4_to_5_rate

---

## STEP 6: フィルターの設定（推奨）

### 日付範囲コントロール

1. 「コントロールを追加」→「日付範囲コントロール」
2. デフォルト期間: 「先月」または「過去30日間」
3. 全ページに適用（ページレベルのフィルターとして設定）

### チャネルフィルター（ページ3）

1. 「コントロールを追加」→「リストボックス」
2. ディメンション: `channel_grouping`
3. データソース: `channel_kpi_monthly`

---

## 権限設定（BQ閲覧権限の付与）

Looker StudioがBQにアクセスするにはGoogleアカウントのBQ権限が必要です。

### 方法1: BigQuery コンソールで直接付与

1. [BigQuery コンソール](https://console.cloud.google.com/bigquery) にアクセス
2. 左サイドバーでプロジェクト `ark-hd-analytics` を選択
3. 「IAMと管理」→「IAM」
4. 「アクセス権を付与」をクリック
5. Looker Studioにログインしているアカウントのメールアドレスを入力
6. ロール: `BigQuery データ閲覧者` を選択
7. 「保存」

### 方法2: データセットレベルで付与

1. BQコンソール → `ark-hd-analytics` → `marts` データセットを選択
2. 「共有」→「アクセス許可の編集」
3. `allAuthenticatedUsers` または特定アカウントに `roles/bigquery.dataViewer` を付与

---

## 接続確認

設定後、以下のクエリがLooker Studio上で実行できることを確認：

```sql
-- rpt_looker_mainから最新7日を確認
SELECT report_date, sessions, contact_form_submissions
FROM `ark-hd-analytics.reports.rpt_looker_main`
ORDER BY report_date DESC
LIMIT 7
```

データが表示されれば接続成功です。

---

## よくある問題

### 「このデータソースに接続できません」

→ Googleアカウントにbigquery.dataViewer権限があるか確認。

### データが表示されない

→ BQテーブルにデータがあるか確認。GA4エクスポートは24〜48時間後にBQに反映されます。

### グラフが空白になる

→ 日付フィルターの範囲を広げてください。データが存在する期間を確認してから設定します。
