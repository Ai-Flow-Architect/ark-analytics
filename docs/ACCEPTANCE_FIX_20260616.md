# 検収修正パッケージ 2026-06-16（クライアント 6/16検収PDF対応）

対象: 6/16検収PDF「修正依頼①〜⑤／要望⑥⑦／AIチャット改善希望・検収質問」
原則: コード修正は本リポで実装・実データ検証済み（要デプロイ）。Looker Studioの表示・レイアウトはGUI手動作業（当方のGoogleアカウントで操作）。

---

## A. コード修正（実装済み・実データ検証済み → 要デプロイ）

### ② 週次KPIメールのCVRが壊れていた（63.4% → 8.38%）★最優先・検収直結
- **真因**: 週次メールが `contact_cr`（=お問合せ到達→完了率）を「CVR」として表示。しかも率を日次の単純平均(`AVG`)で算出していたため期間比より膨張し63.4%表示。
- **修正**:
  - `src/data_collector.py get_monthly_kpi`: 率指標を `AVG(日次率)` → `SAFE_DIVIDE(SUM分子, SUM分母)`（ratio of sums）へ。`engagement_rate`/`contact_cr`/`overall_cvr`/`new_user_rate` すべて加重比化。
  - `main.py`: 週次メールのCVRを `contact_cr` → `overall_cvr`（=(問合せ+資料DL)/全セッション）へ。
- **実データ検証**: 6/1-6/13 → セッション358・問合せ30・資料DL0 → **overall_cvr 8.38%**（クライアント期待値と一致）。旧63.4%は消滅。

### ① 週次KPIレポートに実集計期間を表示
- **真因**: 見出しが「{月}月累積」のみで、実データ範囲(MIN/MAX report_date)を出していなかった→「6/1〜送信日」に誤認。
- **修正**: `get_monthly_kpi` に `period_start=MIN(report_date)`/`period_end=MAX(report_date)` を追加。`main.py` 見出し直下に「集計期間：YYYY-MM-DD〜YYYY-MM-DD（GA4→BQ確定反映の都合で送信日の1〜2日前まで）」を表示。

### AIチャット: 直帰率・新規ユーザー率が回答不可 → 回答可能化
- **真因**: `daily_kpi_summary` に `bounce_rate`/`new_user_rate` 列は実在するが、`app.py` のKPIクエリSELECTに含めておらずAIに渡っていなかった。
- **修正**: `app.py` の日次KPIクエリに `bounce_rate_pct`/`new_user_rate_pct` と生値 `engaged_sessions`/`new_users` を追加。

### AIチャット: エンゲージメント率のズレ（39.9% → 41.71%でLooker一致）
- **真因**: AIが日次%（14個）を単純平均し約39.4〜39.9%を出していた。Lookerは加重比41.71%。
- **修正**: `app.py` システムプロンプトに「率の期間集計は単純平均禁止・SUM分子/SUM分母で計算」ルールを明記＋生値(engaged_sessions/sessions)を供給。
- **実データ検証**: 6/1-6/14 → 加重比 **41.71%**（=Looker）／日次平均 39.44%（=旧AIチャット）。

### 検証ログ（実施済み）
- `pytest tests/` → 46 passed, 1 skipped（CVR回帰テスト `tests/test_weekly_cvr.py` 追加）
- BigQuery dry-run → 構文・スキーマOK（5,280 bytes）
- 実データ read-only クエリで上記数値を確認

### デプロイ手順（当方確認後）
1. `git add -A && git commit`（main.py / src/data_collector.py / app.py / tests/test_weekly_cvr.py / docs/）
2. `git push`（→ Streamlit Cloudが app.py を自動再デプロイ。週次メールcron/GitHub Actionsは次回送信から反映）
3. デプロイ後、AIチャットで「直近のエンゲージメント率は？」「直帰率は？」「新規ユーザー率は？」を実機確認

---

## B. Looker Studio GUI手動作業（当方がGoogleアカウントで操作・コード不可）

### ③④ 項目名が英語に退行 → 日本語表示名を再適用 ★退行の真因あり
**退行の真因**: 6/12の検収修正B・Cで、チャネル分析を `traffic_breakdown_daily`、ページ別を `page_performance_daily` という**別データソースに差し替えた**。Looker Studioの日本語表示名は**データソース単位**に紐づくため、差替先の新データソースには日本語名が未適用で、素の英語フィールド名が表示された。

**操作**: レポート編集 → リソース → 「追加済みのデータソースの管理」→ 対象データソースを「編集」→ 各フィールドの表示名を日本語へ変更 → 完了。

`page_performance_daily`（③ページ別パフォーマンス）の表示名マッピング:
| 英語フィールド | 日本語表示名 |
|---|---|
| page_path | ページパス |
| page_title | ページタイトル |
| pageviews | ページビュー数 |
| unique_pageviews | ユニークPV数 |
| avg_time_on_page_sec | 平均滞在時間(秒) |
| scroll_90pct_rate_pct | スクロール90%到達率 |
| scroll_90pct_count | スクロール90%到達数 |
| cta_clicks | CTAクリック数 |
| cta_click_rate_pct | CTAクリック率 |
| conversions_from_page | ページ経由CV数 |

`traffic_breakdown_daily`（④チャネル分析ほか内訳）の表示名マッピング:
| 英語フィールド | 日本語表示名 |
|---|---|
| dimension_type | 区分種別 |
| dimension_value | 区分 |
| sessions | セッション数 |
| users | ユーザー数 |
| new_users | 新規ユーザー数 |
| conversions | コンバージョン数 |
| conversion_rate_pct | コンバージョン率 |
| engagement_rate_pct | エンゲージメント率 |
| pageviews | ページビュー数 |

### ⑥ CTA別セッション数の項目名が途中で切れる → 列幅調整
`cta_breakdown_daily` 由来の表。対象表を選択 → 右「スタイル」→ 列幅を広げる／表全体を横に拡張／不要列を非表示。日本語表示名も併せて適用:
| 英語 | 日本語表示名 |
|---|---|
| cta_clicks | CTAクリック数 |
| click_sessions | CTAクリックセッション数 |
| converting_click_sessions | CTA経由CV数 |
| cta_location | CTA設置場所 |

### ⑦ 総合ビューの表配置を下へ・省略なし表示
編集モードで対象の表をドラッグして下方へ移動 → 表の幅/行高/列幅を「スタイル」で拡張し、項目名・数値が省略されないよう調整。スコアカードと重ならない配置に。

### ⑤ CTAクリック数 11 vs 10 → 仕様（修正不要・任意でラベル明確化）
- ページ別パフォーマンス **11** = 延べクリック回数（`page_performance_daily.cta_clicks`＝COUNTIF）。同一人が2回押せば2件。
- 総合ビュー **10** = CTAをクリックしたセッション数（`conversion_funnel_daily.step2a_cta_click`＝COUNT DISTINCT session）。同一セッション内の複数クリックは1。
- **差の1件＝同一セッション内の重複クリック**（実データで 延べ11／セッション10 を確認済み）。両方正しく、測る対象が違うだけ。
- 任意で総合ビューを延べに揃えたい場合は、タイルを `step2a_cta_click_total`（延べ＝11）にバインド変更（GUIのみ）。または表示名を「CTAクリック数（延べ）」「CTAクリックセッション数」と明確化。

---

## C. 退行 再発防止（恒久対策）
**ルール**: Looker Studioでチャートのデータソースを差し替えたら、差替先データソースに日本語表示名マッピングを必ず再適用する（表示名はデータソース単位で、差替で引き継がれないため）。本ファイルB節のマッピング表を正本とし、データソース差替を伴う修正のチェックリストに「表示名再適用」を必ず入れる。

---

## D. AIチャット「任意期間集計」について（アーキ上の限界・要経営判断）
- 現行AIチャットは「固定範囲(直近14日/30日/月次)で事前集計したサマリーをAIに渡す」設計。質問文から任意期間を読み取って都度BigQueryへ再集計クエリを発行する仕組みは**無い**。
- よって「LP別/検索エンジン別/デバイス別/ファネルを任意期間で集計」はAIチャット単体では原理的に不可（データ自体は `traffic_breakdown_daily` に実在し、直近30日では回答可能）。
- 任意期間×任意ディメンションの自由集計を実現するには **動的クエリ発行機構（text-to-SQL/function calling＋許可テーブル・列ホワイトリスト）の新設＝追加開発（大）** が必要。Phase2提案候補。
- 当面の正直な切り分け: 任意期間の自由集計は **Looker Studio で対応可能**（そのために構築）。AIチャットは「直近の状況を自然文で素早く把握する」用途。直帰率・新規ユーザー率・エンゲージメント率一致は本修正で即対応。
