# Looker Studio GUI手順書 — クライアント11確認点の ④⑤⑪（人手・AIFLOW作業）

最終更新: 2026-05-31 | 対象: ARK Analytics / Looker Studio
レポート: https://datastudio.google.com/reporting/e26ea2fe-edd9-47d6-8187-dd7c7cd31b8e
土台ドキュメント: [LOOKER_NEXTPHASE_SETUP.md](LOOKER_NEXTPHASE_SETUP.md)（データソース接続はこちら先に）

> BQ側（データ層）は ①⑦⑧ 含め全て本番反映＋自動更新化済み（daily_refresh で毎日更新）。
> 残るは Looker の GUI 操作のみ（API不可）。所要 約30〜45分。
> ⑨（CTA分類の中身）は GTM 側で cta_location 等を送る設定が前提。本書の⑤は「項目名の日本語化」まで。

---

## ④ チャネル別分析に「コンバージョン数」列を追加

データソース: `marts.traffic_breakdown_daily`（未接続なら土台doc §0 で先に接続）

1. 「チャネル別分析」ページを開く → 編集モード
2. チャネル別の表を選択（フィルタ `dimension_type = 'channel'` が当たっているもの）
3. 右パネル「指標」→「指標を追加」→ **`conversions`** を選択
4. 列見出しをクリック → 表示名を **「コンバージョン数」** に変更
5. （任意）CV率列: 「フィールドを追加（計算フィールド）」→ `SUM(conversions)/SUM(sessions)` → 書式%。
   ※ `conversion_rate_pct` 既存列は単日用。期間集計には上記 ratio of sums を使う（AVG禁止）

検証: チャネル別CV合計が当月の問い合わせ完了数と概ね整合するか確認。

---

## ⑤ CTA別の項目名を日本語化

データソース: `marts.cta_breakdown_daily`（土台doc §0 で接続。本日ビルド稼働化済）

1. 「リソース → 追加済みデータソースの管理 → `cta_breakdown_daily` → 編集」
2. 各フィールドの「フィールド名（表示名）」を日本語に変更:

| 元フィールド | 日本語表示名 |
|---|---|
| cta_clicks | CTAクリック数 |
| click_sessions | CTAクリックセッション数 |
| converting_click_sessions | CTA経由CV数 |
| cta_to_cv_rate_pct | CTA経由CV率 |
| cta_location | CTA設置場所 |
| cta_type | CTAタイプ |
| cta_purpose | CTA目的 |

3. 「ページ別パフォーマンス」or「CTA分析」ページの該当表で、上記フィールドが日本語表示になっていることを確認

注意: 現状 cta_location/type/purpose は全て「(未設定)」表示になります。これは **GTMのcta_clickタグが分類パラメータを送っていない**ためで、⑨（GTM設定）完了後に実際の場所・種別が入ります。項目名の日本語化自体は今すぐ可能。

---

## ⑪ 総合ビューに主要KPIを一覧表示

データソース: `reports.rpt_funnel_overview` および `reports.rpt_looker_main`

クライアント要望の表示項目（総合ビューに追加）:
- お問い合わせフォームセッション数 / CTAクリック数・率 / フォーム到達数・率 / フォーム完了数・率

1. 「総合ビュー」ページを開く → 編集モード
2. スコアカード or 表を追加し、`rpt_funnel_overview` から下記を配置:

| 表示KPI | フィールド |
|---|---|
| CTAクリック数 | `stage1_cta_click` |
| フォーム到達数 | `stage2_form_reach` |
| フォーム完了数 | `stage3_completion` |
| お問い合わせページ到達 | `contact_page_reach` |
| CTA→フォーム率 | `cta_to_form_rate_pct`（単日）/ 期間は ratio of sums |
| フォーム→完了率 | `form_to_complete_rate_pct`（単日）/ 期間は ratio of sums |

3. 「フォームセッション数」は `rpt_looker_main` の `contact_form_views`（お問い合わせフォーム閲覧）を使用
4. 既存の「ファネル分析」ページと数値が一致することを確認（同一データソース由来なので整合するはず）

補足: クライアントの「ファネル分析にあるため総合ビュー未表示、という認識で合っているか」は **その通り**。本手順で総合ビューにも再掲する形。

---

## 仕上げチェック（送信前）

- [ ] ④ チャネル別にコンバージョン数列が表示・CV合計が整合
- [ ] ⑤ cta_breakdown のフィールド名が日本語表示（中身の(未設定)は⑨待ちと返信で明記）
- [ ] ⑪ 総合ビューに主要KPIが一覧表示・ファネル分析ページと数値一致
- [ ] 期間コントロールで全ページ連動（土台doc §1）
- [ ] クライアント返信文はAIFLOWが最終確認のうえ送信（自動送信禁止）

---

## 【2026-06-03 追加】④ 「フォームCR（期間）」→「フォーム閲覧→完了率」へ表示名変更

6/3クライアント確認点④。元フィールド: `rpt_looker_main.contact_form_cr_pct`（= 送信完了数 ÷ お問い合わせフォーム閲覧数）。表示名のみ変更（BQ層は変更不要）。

手順（Looker GUI・API不可）:
1. レポートを開く → 右上「編集」
2. 「リソース」→「追加済みデータソースの管理」→ `rpt_looker_main` →「編集」
3. フィールド一覧で表示名「フォームCR（期間）」（元: `contact_form_cr_pct`）を検索
4. 表示名を **「フォーム閲覧→完了率」** に変更 → 「完了」
5. 「総合ビュー」ページに戻り、該当スコアカード/表の見出しが新表示名になっているか確認
   - もしチャート側で個別にラベルを上書きしていた場合は、そのチャートの「指標」名も同様に変更
6. 変更後、クライアントへ「変更完了」連絡（④の後追い連絡）

---

## 【2026-06-03 追加】統合ビュー ファネル率100%超の根本解決（Looker GUI差替）

BQ層は改定済（commit 9f4f243・`rpt_funnel_overview` に単調な主ファネル列を追加）。残りはLooker GUIで表示列を新指標に差し替えるのみ。新ファネルは全期間でも率≤100%（期間制限は不要）。

### STEP A: データソースの新フィールドを取り込む
1. レポート →「編集」→「リソース」→「追加済みデータソースの管理」→ `rpt_funnel_overview` →「編集」
2. 右下（または上部）の **「フィールドを更新」** をクリック → 新列が一覧に出る → 「完了」

### STEP B: 統合ビューの表/スコアカードを新指標に差し替え
旧（CTA起点・100%超）→ 新（お問合せ到達起点・単調）へ列を入れ替える:

| 旧フィールド（削除） | 新フィールド（追加） | 表示名案 |
|---|---|---|
| `cta_to_form_rate_pct`（CTA→フォーム率・300%） | `contact_to_form_rate_pct` | お問合せ到達→入力開始率 |
| `form_to_complete_rate_pct`（213%になりうる） | `form_to_complete_rate_main_pct` | 入力開始→完了率 |
| `stage2_form_reach` | `form_reach` | フォーム入力開始 |
| `contact_page_reach` / `stage1_cta_click` を段扱い | `contact_reach` | お問合せ到達 |
| （CTAを段から外す） | `cta_click` / `cta_click_rate_pct` | CTAクリック数 / CTAクリック率（補助指標として別枠） |

- ファネルの並びは **お問合せ到達 → フォーム入力開始 → 完了**（CTAは段から外し、独立スコアカードへ）。
- 率は期間集計で SUM/SUM（ratio of sums）。`_pct` 列は単日表示用（AVG禁止）。

### STEP C: 確認
- 統合ビューの率がすべて 0〜100% に収まる（300%/213%が消える）
- 到達 ≥ 入力開始 ≥ 完了 の降順になっている
- 確認後クライアントへ「ファネル指標を整理し、率が正しく表示される状態にした」と連絡
