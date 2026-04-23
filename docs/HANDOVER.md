# ark-analytics 納品・権限移譲チェックリスト

納品担当: 五十嵐 | 対象: 株式会社アテンド 様（ark-hd.co.jp）| 目標納品日: 2026年4月23〜24日

---

## システム概要

| サービス | 内容 | 状態 | URL / 備考 |
|---------|------|------|-----------|
| ① BigQuery分析基盤 | GA4データをBQへ自動転送・集計 | ✅ 構築済み | GCP: ark-hd-analytics |
| ② 月次レポート自動生成 | 毎月1日9:00にHTMLメール+Drive保存 | ✅ cron設定済み | 配信先: aspr.k.kamimura@gmail.com |
| ③ 自然言語QA（Streamlit） | 「どのページが…？」に即回答 | ✅ 本番稼働中 | https://ark-analytics.streamlit.app/ |
| ④ 改善施策スコアリング | 優先度TOP5を自動算出 | ✅ 実装済み | QAアプリに統合 |
| ⑤ Looker Studioダッシュボード | BQ接続のリアルタイム可視化 | ⏳ Page3〜5グラフ設定中（4/23） | https://datastudio.google.com/reporting/e26ea2fe-edd9-47d6-8187-dd7c7cd31b8e |
| ⑥ GTMカスタムイベント | スクロール・CTA・フォーム計測 | ✅ 設置・確認済み（4/23） | GTM-5B3L5372 / ark-hd.co.jp head確認済み |
| ⑦ 仕様書（GitHub Pages） | 全システム仕様・運用マニュアル | ✅ 公開済み | https://ai-flow-architect.github.io/ark-analytics-spec/ |

---

## 権限移譲チェックリスト（株式会社アテンド 様側での操作）

### A. BigQuery権限確認

```
プロジェクト: ark-hd-analytics
```

- [ ] GCPコンソール（console.cloud.google.com）にログイン
- [ ] 「BigQuery」→ データセットが表示されることを確認
  - `staging` / `marts` / `reports` の3データセット
- [ ] `reports.rpt_looker_main` テーブルをプレビューできることを確認

### B. Looker Studio ダッシュボード共有確認

ダッシュボードURL: https://datastudio.google.com/reporting/e26ea2fe-edd9-47d6-8187-dd7c7cd31b8e

- [x] 株式会社アテンド 担当者様（aspr.k.kamimura@gmail.com）に「閲覧者」権限を付与済みか確認（4/22完了）
- [ ] 上記URLを株式会社アテンド 担当者様に送付（4/24 納品時）
- [ ] 株式会社アテンド 担当者様側でPage1〜5が表示されることを確認（4/24 納品時）

### C. GTMタグ設置

詳細コード: [GTM_TAGS.md](GTM_TAGS.md)

- [x] GTMコンテナ GTM-5B3L5372 にタグ①〜③設定・v2公開済み（4/21完了）
- [x] ark-hd.co.jp `<head>` + `<noscript>` にGTMスニペット設置確認済み（4/23 curl確認）

### D. 月次レポート配信確認

- [ ] 翌月1日（5月1日）のレポートを手動ドライランで確認
  ```bash
  cd /home/kosuke_igarashi/projects/ark-analytics
  python3 main.py --report-type monthly --dry-run --month 2026-04
  ```
- [ ] 配信先メール: aspr.k.kamimura@gmail.com に届くことを確認

---

## 環境変数（サーバー側設定済み）

| 変数名 | 用途 |
|-------|------|
| `ARK_CLIENT_EMAIL` | レポート配信先メール |
| `GMAIL_ADDRESS` | 送信元Gmail |
| `GMAIL_APP_PASSWORD` | Gmailアプリパスワード |
| `OPENAI_API_KEY` | AI分析用GPT-4o |

---

## cron自動実行スケジュール（設定済み）

| 実行時間 | 処理 |
|---------|------|
| 毎日 AM 4:00 | BQテーブル更新（`daily_refresh.sh`） |
| 毎月1日 AM 9:00 | 月次レポート生成・メール配信 |

---

## よく使うコマンド

```bash
cd /home/kosuke_igarashi/projects/ark-analytics

# 自然言語QA
python3 main.py --report-type qa --question "どのページが一番離脱が多いですか？"

# 改善施策スコアリング
python3 main.py --report-type scorer

# 月次レポート（ドライラン）
python3 main.py --report-type monthly --dry-run --month 2026-04

# 月次レポート（本番送信）
python3 main.py --report-type monthly --month 2026-04

# 手動BQ更新
bash scripts/daily_refresh.sh
```

---

## トラブルシューティング

→ [MANUAL.md トラブルシューティング](MANUAL.md#7-トラブルシューティング) を参照

---

## 納品後のサポート範囲

- 納品後 **約2週間** は確認・修正対応を実施
- バグ・動作不良: Coconalaトークルームにてご連絡ください
- Looker Studio設定・GTM設置のサポートも対応可能
