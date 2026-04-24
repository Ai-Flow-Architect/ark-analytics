# ark-analytics 納品・引き継ぎドキュメント

納品担当: 五十嵐 | 対象: 株式会社アテンド 様（ark-hd.co.jp）| 最終更新: 2026-04-24

---

## 1. システム全体マップ

```
ark-hd.co.jp（Webサイト）
  │
  ├── GTMタグ（GTM-5B3L5372）
  │     ├── タグ①: スクロール90%計測
  │     ├── タグ②: CTAクリック計測
  │     └── タグ③: フォーム送信計測
  │
  ▼
GA4（プロパティID: 448869498）
  │
  ▼  ← BigQuery Export（毎日自動）
BigQuery（ark-hd-analytics）
  ├── staging/  ← GA4生データ整形
  ├── marts/    ← 分析テーブル5種
  └── reports/  ← Looker Studio接続用
  │
  ├──▶ Looker Studio ダッシュボード（5ページ）
  │         https://datastudio.google.com/reporting/e26ea2fe-edd9-47d6-8187-dd7c7cd31b8e
  │
  └──▶ Streamlit QAアプリ（自然言語チャット）
  │         https://ark-analytics.streamlit.app/
  │
  └──▶ 月次AIレポート（毎月1日自動メール）
            配信先: aspr.k.kamimura@gmail.com
```

---

## 2. 納品物 ステータス一覧（2026-04-24 時点）

| # | 納品物 | 状態 | URL / 備考 |
|---|--------|------|-----------|
| ① | BigQuery 分析基盤 | ✅ 完成 | GCPプロジェクト: ark-hd-analytics |
| ② | 月次AI自動レポート | ✅ 完成・cron稼働中 | 毎月1日 AM9:00 自動配信 |
| ③ | Streamlit 自然言語QAアプリ | ✅ v2.2 本番稼働中 | https://ark-analytics.streamlit.app/ |
| ④ | 改善施策スコアリング | ✅ 完成（Streamlitに統合） | QAアプリ内で動作 |
| ⑤ | Looker Studio ダッシュボード | ⚠️ 表示OK・日本語化が未完 | 後述「残課題①」参照 |
| ⑥ | GTM カスタムイベント3種 | ✅ 設置・確認済み | GTM-5B3L5372 / 4/23確認 |
| ⑦ | 仕様書（GitHub Pages） | ✅ 公開済み | https://ai-flow-architect.github.io/ark-analytics-spec/ |

---

## 3. 残課題（後日対応）

### 残課題① Looker Studio フィールド名の日本語化

**状況:** データは表示されているが、グラフのラベル・スコアカード名が英語のまま（`sessions`, `contact_form_submissions` 等）

**修正方法（Looker Studio GUI操作 / 約10分）:**

> **ポイント:** データソースレベルで一括変更するため、チャートを1個ずつ触る必要はない

手順:
1. Looker Studio を開く → 上部メニュー「**リソース**」→「**追加済みのデータソースの管理**」
2. `rpt_looker_main`（または `daily_kpi_summary`）の横「**編集**」をクリック
3. 下記テーブルを参考に、各フィールドの表示名を日本語に変更
4. 「**完了**」→ レポートに戻る → 全チャートが自動で日本語に変わる
5. チャネル・ページの各データソースも同様に変更

**フィールド名 日本語変換マッピング（rpt_looker_main）:**

| 現在の英語名 | 変更後の日本語名 |
|-------------|----------------|
| `report_date` | 日付 |
| `sessions` | セッション数 |
| `users` | ユーザー数 |
| `new_users` | 新規ユーザー数 |
| `engaged_sessions` | エンゲージメントセッション数 |
| `pageviews` | ページビュー数 |
| `avg_session_duration` | 平均セッション時間(秒) |
| `engagement_rate` | エンゲージメント率 |
| `bounce_rate` | 直帰率 |
| `contact_form_views` | 問い合わせページ閲覧数 |
| `contact_form_submissions` | 問い合わせ件数 |
| `document_downloads` | 資料DL数 |
| `total_conversions` | 総コンバージョン数 |
| `contact_form_cr` | 問い合わせCVR |
| `overall_cvr` | 全体CVR |
| `funnel_step1_sessions` | Step1: 訪問 |
| `funnel_step2_service_view` | Step2: サービスページ閲覧 |
| `funnel_step3_contact_page` | Step3: お問い合わせページ |
| `funnel_step4_form_start` | Step4: フォーム入力開始 |
| `funnel_step5_submission` | Step5: フォーム送信完了 |
| `funnel_overall_cvr` | ファネル全体CVR |

**フィールド名 日本語変換マッピング（channel_kpi_monthly）:**

| 現在の英語名 | 変更後の日本語名 |
|-------------|----------------|
| `report_month` | 月 |
| `channel_grouping` | チャネル |
| `sessions` | セッション数 |
| `users` | ユーザー数 |
| `engagement_rate` | エンゲージメント率 |
| `pageviews` | ページビュー数 |
| `conversions` | コンバージョン数 |
| `conversion_rate` | CVR |

**フィールド名 日本語変換マッピング（page_performance）:**

| 現在の英語名 | 変更後の日本語名 |
|-------------|----------------|
| `week_start` | 週開始日 |
| `page_path` | ページパス |
| `page_title` | ページタイトル |
| `pageviews` | ページビュー数 |
| `avg_time_on_page_sec` | 平均滞在時間(秒) |
| `scroll_90pct_rate` | スクロール90%到達率 |
| `conversions_from_page` | このページ起点のCV数 |

---

### 残課題② ページ分析・スクロール率データの蓄積待ち

**状況:** GTMタグ①〜③を4/21に設置したばかりのため、以下のデータが未蓄積

| データ項目 | 蓄積開始 | 有効化の目安 |
|-----------|---------|------------|
| スクロール90%到達率 | 4/21〜 | 5月上旬（2週間後） |
| CTAクリック数 | 4/21〜 | 5月上旬 |
| フォーム入力開始イベント | 4/21〜 | 5月上旬 |
| 平均滞在時間 | 4/10〜（GA4デフォルト） | すでに一部あり |

**対応:** 5月上旬以降に Streamlit QAアプリ・Looker Studioのページ分析ページを再確認する

---

## 4. 全アクセスURL・認証情報

### アプリ・ダッシュボード

| システム | URL |
|---------|-----|
| Streamlit QAアプリ | https://ark-analytics.streamlit.app/ |
| Looker Studio | https://datastudio.google.com/reporting/e26ea2fe-edd9-47d6-8187-dd7c7cd31b8e |
| 仕様書（GitHub Pages） | https://ai-flow-architect.github.io/ark-analytics-spec/ |

### GCP / BigQuery

| 項目 | 値 |
|------|---|
| GCPプロジェクトID | `ark-hd-analytics` |
| GA4プロパティID | `448869498` |
| BigQuery データセット | `staging` / `marts` / `reports` |
| Looker Studio 共有先 | aspr.k.kamimura@gmail.com（閲覧者権限付与済み） |

### GTM

| 項目 | 値 |
|------|---|
| GTMコンテナID | `GTM-5B3L5372` |
| 設置確認日 | 2026-04-23 |
| 設置確認方法 | `curl -s https://ark-hd.co.jp` でスニペット確認済み |

### Coconala

| 項目 | URL |
|------|-----|
| 案件ページ | https://coconala.com/service_requests/4928503 |
| トークルーム | https://coconala.com/talkrooms/17468749 |

### GitHubリポジトリ

| 用途 | URL |
|------|-----|
| 本体コード | https://github.com/Ai-Flow-Architect/ark-analytics |
| 仕様書 | https://github.com/Ai-Flow-Architect/ark-analytics-spec |

---

## 5. BigQuery テーブル構成

| テーブル | 更新タイミング | 主な用途 |
|---------|-------------|---------|
| `staging.stg_ga4_events` | 毎日 AM4:00 | GA4生データ整形 |
| `staging.stg_sessions` | 毎日 AM4:00 | セッション集計 |
| `marts.daily_kpi_summary` | 毎日 AM5:00 | 日次KPI |
| `marts.channel_kpi_monthly` | 毎月1日 AM6:00 | チャネル月次 |
| `marts.page_performance` | 毎週月曜 AM5:00 | ページ分析 |
| `marts.conversion_funnel_daily` | 毎日 AM5:00 | ファネル |
| `reports.rpt_looker_main` | 毎日 AM5:30 | Looker Studio メイン |

---

## 6. Streamlit アプリ仕様（v2.2）

**URL:** https://ark-analytics.streamlit.app/

**機能:**
- サイドバーからカテゴリ別の質問例をワンクリック
- BigQueryからリアルタイムデータ取得（最大30秒）
- GPT-4oがデータを元に日本語で即回答
- グラフ（折れ線・棒）＋テーブルで補足表示
- 会話履歴を引き継いだ連続質問に対応

**対応質問カテゴリ:**

| カテゴリ | 接続テーブル |
|---------|------------|
| ページ分析 | `page_performance` |
| チャネル分析 | `channel_kpi_monthly` |
| ファネル分析 | `conversion_funnel_daily` |
| KPI確認 | `daily_kpi_summary` |

**GitHubリポジトリ:** https://github.com/Ai-Flow-Architect/ark-analytics
- `app.py`: Streamlitアプリ本体
- `src/`: AI分析・データ取得モジュール
- Streamlit CloudはGitHubへのpushで自動デプロイ

---

## 7. cron 自動実行スケジュール

| 実行時間（JST） | 処理 | スクリプト |
|--------------|------|----------|
| 毎日 AM 4:00 | GA4→BQ staging更新 | `scripts/daily_refresh.sh` |
| 毎日 AM 5:00 | marts テーブル更新 | `scripts/daily_refresh.sh` |
| 毎日 AM 5:30 | reports ビュー更新 | `scripts/daily_refresh.sh` |
| 毎月1日 AM 9:00 | 月次AIレポート生成・メール配信 | `main.py --report-type monthly` |
| 毎週月曜 AM 5:00 | page_performance 週次更新 | `scripts/daily_refresh.sh` |

**確認コマンド:**
```bash
# cron設定確認
crontab -l

# 手動BQ更新
bash scripts/daily_refresh.sh

# 月次レポート ドライラン
python3 main.py --report-type monthly --dry-run --month 2026-04

# 月次レポート 本番送信
python3 main.py --report-type monthly --month 2026-04
```

---

## 8. 環境変数（本番サーバー設定済み）

| 変数名 | 用途 |
|-------|------|
| `ARK_CLIENT_EMAIL` | レポート配信先メール（aspr.k.kamimura@gmail.com） |
| `GMAIL_ADDRESS` | 送信元Gmail |
| `GMAIL_APP_PASSWORD` | Gmailアプリパスワード |
| `OPENAI_API_KEY` | GPT-4o API キー |

Streamlit Cloud側の Secrets（`.streamlit/secrets.toml` 相当）にも設定済み:
- `OPENAI_API_KEY`
- `[gcp_service_account]`（BigQuery接続用サービスアカウントJSON）

---

## 9. 月次レポート 運用フロー

毎月1日に以下が自動実行される:

1. BigQueryから直近1ヶ月のKPIデータ取得
2. GPT-4oが自動分析・改善提案テキスト生成
3. HTMLメールとしてフォーマット
4. `aspr.k.kamimura@gmail.com` に自動送信
5. Google Driveにバックアップ保存

**ドライランで事前確認する場合:**
```bash
cd ~/projects/ark-analytics
python3 main.py --report-type monthly --dry-run --month 2026-05
```

---

## 10. トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| Streamlitが「接続エラー」 | BQサービスアカウント権限切れ | Streamlit Cloud Secrets の `gcp_service_account` を確認 |
| Streamlitが「OpenAI APIエラー」 | APIキー期限切れ or 残高不足 | Streamlit Cloud Secrets の `OPENAI_API_KEY` を更新 |
| 月次レポートが届かない | Gmailアプリパスワード失効 | `~/.bashrc` の `GMAIL_APP_PASSWORD` を再発行・更新 |
| Looker Studioが「データなし」 | BQ接続切れ or データ未更新 | BQコンソールでテーブルを確認 / `daily_refresh.sh` 手動実行 |
| BQテーブルが更新されない | cronが停止している | `crontab -l` で設定確認 / `scripts/daily_refresh.sh` 手動実行 |
| GA4データがBQに来ない | GA4→BigQuery Exportが止まっている | GCPコンソール→BigQuery→データ転送でステータス確認 |

---

## 11. 権限移譲チェックリスト（株式会社アテンド 様）

### BiqQuery アクセス確認
- [x] `aspr.k.kamimura@gmail.com` にBigQuery閲覧権限付与済み（2026-04-22）
- [ ] GCPコンソール（console.cloud.google.com）へのログイン確認
- [ ] BigQuery → `staging` / `marts` / `reports` が見えることを確認
- [ ] `reports.rpt_looker_main` のプレビュー確認

### Looker Studio
- [x] `aspr.k.kamimura@gmail.com` に閲覧権限付与済み（2026-04-22）
- [ ] URLでダッシュボードが開けることを確認
- [ ] 全5ページ（主要分析・ファネル・チャネル・ページ・統合）が表示されることを確認

### Streamlit QAアプリ
- [ ] https://ark-analytics.streamlit.app/ が開けることを確認
- [ ] サイドバーのボタンをクリックして回答が返ることを確認
- [ ] 「今月のセッション数の傾向はどうですか？」でグラフが表示されることを確認

### GTMタグ
- [x] GTM-5B3L5372 が `ark-hd.co.jp` に設置済み（2026-04-23 確認済み）
- [ ] GTM管理画面へのアクセス権限付与（必要であれば）

---

## 12. 今後の運用・推奨アクション

| タイミング | アクション |
|-----------|----------|
| **2026-05-01** | 月次レポートの受信確認（初回自動配信） |
| **2026-05-07以降** | Streamlit・Looker Studioのページ分析データ確認（GTMタグ設置2週間後） |
| **都度** | Looker Studioの日本語化（残課題①）を実施 |
| **毎月末** | 月次レポート内容を確認し、改善施策を検討 |

---

## 13. 開発メモ（技術引き継ぎ用）

**Looker Studioのフィールド名について:**

Looker StudioのフィールドエイリアスはGUI操作（データソース編集）でのみ変更可能。
APIによる自動化は現時点で非対応。

変更手順: `リソース` → `追加済みのデータソースの管理` → `編集` → 各フィールドの表示名を日本語に変更 → `完了`

詳細マッピング表は「残課題①」セクション参照。

**Streamlit デプロイについて:**

GitHub `Ai-Flow-Architect/ark-analytics` の `master` ブランチにpushすると自動デプロイ。
デプロイ確認はフッターのバージョン番号（`v2.2`）で確認。

**BQビューの再作成が必要になった場合:**

```bash
cd ~/projects/ark-analytics
bq query --use_legacy_sql=false < sql/reports/rpt_looker_main.sql
bq query --use_legacy_sql=false < sql/marts/daily_kpi_summary.sql
# 以降同様
```

---

*最終確認: 2026-04-24 | 担当: 五十嵐（AIフローアーキテクト）*
*Coconalaトークルーム: https://coconala.com/talkrooms/17468749*
