# GTM トリガー条件 修正手順書（B⑤ 5/15 検証 → 修正実施用）

最終更新: 2026-05-15  
対象コンテナ: `GTM-XXXXXXX`（（クライアント企業） example.com）  
実施担当: AIフローアーキテクト（弊社ログイン可・要弊社担当者アカウントでの直接実施）

---

## 0. 前提と背景

### 真因（5/15 BQ実測検証で確定）

| event | 4/22-5/14 BQ実測 | 状態 |
|---|---:|---|
| `page_view` / `session_start` / `first_visit` / `contact_finish` | 1,234件以上 | ✅ 正常 |
| `scroll_depth` / `cta_click` / `form_start` / `form_abandon` | **0 件** | ❌ 未発火 |

タグそのもの（`docs/GTM_TAGS.md` 記載のCustom HTMLコード）は汎用セレクタで書かれているため動くはずだが、**GTM管理画面側のタグ設定 or トリガー紐付けが docs/GTM_TAGS.md と乖離している** ことが唯一の原因と推定される。

### 本手順で修正する3タグ

| # | タグ | 期待される発火 | 期待パラメータ |
|---|---|---|---|
| ① | Scroll Depth (Custom HTML) | 25% / 50% / 75% / 90% で各1回 | `scroll_pct` (int) / `page_path` (string) |
| ② | CTA Click (Custom HTML) | CTAボタン・問合せリンククリック時 | `cta_location` / `cta_type` / `cta_purpose` / `cta_id` / `cta_text` / `page_path` |
| ③ | Form Operations (Custom HTML) | フォーム入力開始時 / 送信時 / 離脱時 | `form_id` / `page_path` |

### 重要な設計判断（弊社確認済み）

- **HTML改修は不要**: `<form name="form1">` 旧来構造でも、JavaScriptセレクタ `document.querySelector('form')` で取れる
- **GA4 構成タグの「拡張計測」をONにしない**: ONにすると scroll パラメータ名が `percent_scrolled` になり、SQL側（`scroll_pct` 統一）と不整合
- **Custom HTML タグを必ず採用**: 上記理由のため、組み込みトリガー（Scroll Depth Trigger / Form Submission Trigger）の利用は避ける

---

## 1. アクセス権限の確認（実施前にこれを必ず最初に）

### 弊社担当者（AIフローアーキテクト）の招待状況確認

1. ブラウザで https://tagmanager.google.com/ を開く
2. `{{ARK_OPERATOR_EMAIL}}` でログイン
3. アカウント一覧に「（クライアント企業）」または `example.com` 関連のアカウントが表示されるか確認

#### ケースA: 表示される（招待済み）

- そのままコンテナ `GTM-XXXXXXX` をクリック → **「2. タグ①の修正」へ進む**

#### ケースB: 表示されない（招待未済）

- 本ドキュメント末尾「付録A: クライアントへのGTM招待依頼DMドラフト」を参照
- Coconala DMで弊社担当者アカウントの招待を依頼（手動送信・自動送信禁止ルール準拠）
- 招待受領後（通常クライアント側で5-10分作業）に本手順に戻る

---

## 2. タグ①「スクロール深度トラッキング」の修正

### 2.1 現状確認

1. GTM管理画面 左メニュー「タグ」をクリック
2. タグ一覧から「Scroll Depth」「スクロール深度」「タグ①」等の名前のタグを探す
3. クリックして詳細画面を開く

### 2.2 タグ設定の確認・修正

| 項目 | 期待値 | 確認ポイント |
|---|---|---|
| タグの種類 | **カスタム HTML** | Built-in の「Scroll Depth Trigger」を使うタグになっていたら ❌（パラメータ名が `percent_scrolled` になり SQL 不整合） |
| HTML コード | `docs/GTM_TAGS.md` のタグ①コード全文 | gtag('event', 'scroll_depth', { 'scroll_pct': m, 'page_path': ... }) が含まれていれば ✅ |
| 配信トリガー | **All Pages** (Built-in `Page View` トリガー) | 「Window Loaded」「DOM Ready」「特定ページのみ」だと発火タイミングずれの原因 |

### 2.3 修正アクション

#### もしタグが「Scroll Depth Trigger」を使っていたら（最も多いケース）

1. **タグを削除しない**（履歴保全のため）
2. 「新規タグを追加」→「タグの種類: カスタム HTML」を選択
3. `docs/GTM_TAGS.md` の **① スクロール深度トラッキング** セクションのHTMLコードを全文コピー（行22〜53）
4. HTML欄に貼り付け
5. 「タグ名」を「**Custom HTML - Scroll Depth (v2)**」に設定
6. トリガー: **All Pages**
7. 「保存」
8. 古いScroll Depth Triggerタグを「一時停止」（削除ではなく一時停止で履歴保全）

#### もしタグがCustom HTMLだが発火していない場合

1. タグ詳細画面で「タグの順序付け」を確認 → GA4構成タグの**後**に発火するよう設定（通常はデフォルトで問題ない）
2. トリガーが「All Pages」になっていることを確認
3. 必要に応じてHTML中の `gtag` を `window.gtag` に書き換え（一部環境で gtag が global に出ていない場合）

---

## 3. タグ②「CTAクリックトラッキング」の修正

### 3.1 現状確認

GTM管理画面「タグ」→「CTA Click」「タグ②」「カスタムイベント - cta_click」等を探してクリック。

### 3.2 タグ設定の確認・修正

| 項目 | 期待値 | 確認ポイント |
|---|---|---|
| タグの種類 | カスタム HTML | ✅（Built-in `Click - Just Links` でも可だが、パラメータ送信が複雑になるので Custom HTML 推奨） |
| HTML コード | `docs/GTM_TAGS.md` のタグ②コード全文 | gtag('event', 'cta_click', { 'cta_location': loc, ... }) が含まれていれば ✅ |
| 配信トリガー | **All Pages** | Click トリガーではなく All Pages（HTML内で document.addEventListener('click') しているため） |

### 3.3 修正アクション

#### もしタグが「Click All Elements」「Click Just Links」トリガーを使っていたら

1. **タグを一時停止**（削除ではなく）
2. 「新規タグを追加」→「タグの種類: カスタム HTML」
3. `docs/GTM_TAGS.md` の **② CTAクリックトラッキング** セクション（行120〜193）をコピペ
4. タグ名: 「**Custom HTML - CTA Click (v2)**」
5. トリガー: **All Pages**
6. 「保存」

#### もし Click Trigger に `data-tracking` 属性のマッチ条件があったら

- example.com の HTML には `data-tracking` 属性が存在しないため、その条件は**マッチしない**
- → Custom HTML 版へ切り替え（上記手順）

#### CSS セレクタの確認

`docs/GTM_TAGS.md` タグ②内の `ctaSelectors` 配列に注目:

```javascript
var ctaSelectors = [
  '.cta-button',         // ← example.com に存在しない場合あり
  '.btn-contact',        // ← example.com に存在しない場合あり
  'a[href*="/contact"]', // ← 最も汎用的・「お問い合わせ」リンクはこれでカバー
  'a[href*="contact.html"]',
  '[data-cta]'           // ← example.com に存在しない
];
```

example.com のHTML構造を踏まえると、**`a[href*="/contact"]` だけで90%のCTAクリックは捕捉できる**。

念のため Preview Mode で実際にどのセレクタがマッチしているかを確認（次セクション参照）。

---

## 4. タグ③「フォーム操作トラッキング」の修正

### 4.1 現状確認

GTM管理画面「タグ」→「Form Tracking」「タグ③」「カスタムイベント - form_start」等を探す。

### 4.2 タグ設定の確認・修正

| 項目 | 期待値 | 確認ポイント |
|---|---|---|
| タグの種類 | カスタム HTML | Built-in `Form Submission` トリガーだと旧来型フォームでマッチしにくい |
| HTML コード | `docs/GTM_TAGS.md` のタグ③コード全文 | `document.querySelector('form')` で `<form name="form1">` を取っているか確認 |
| 配信トリガー | **フォームページのみ**（`/contact` 含むURL） | All Pages でも動くが、不要なページで実行コスト発生 |

### 4.3 修正アクション

#### もしタグが「Form Submission」トリガーを使っていたら

1. **タグを一時停止**
2. 「新規タグを追加」→「タグの種類: カスタム HTML」
3. `docs/GTM_TAGS.md` の **③ フォーム操作トラッキング** セクション（行225〜270）をコピペ
4. タグ名: 「**Custom HTML - Form Operations (v2)**」
5. トリガー:
   - 「**新規トリガー**」→「**ページビュー**」
   - トリガー条件: 「Page URL」「含む」「/contact」（簡易）
   - 保存して適用
6. 「保存」

### 4.4 タグ③の form_abandon に関する注意

タグ③コードには `beforeunload` イベントで `form_abandon` を送信する処理が含まれているが、近年のブラウザ（Chrome 90+ / Safari 14+）では `beforeunload` 内の `gtag()` 呼び出しがブロックされる場合がある。

- **影響範囲**: form_abandon の取得漏れが最大40%程度発生する可能性
- **対策**: 5/22 MTGで「制限事項」として明示・主要指標は scroll_depth / cta_click / form_start の3つに絞る
- **将来改善**: `navigator.sendBeacon` への置換（追加見積もり対象）

---

## 5. プレビューモードでの実発火確認（修正後 必ず実施）

### 5.1 プレビュー起動

1. GTM管理画面 右上「**プレビュー**」をクリック
2. 別タブで Tag Assistant が開く
3. URL欄に `https://www.example.com/` を入力 → 「Connect」
4. example.com のサイトが新タブで開く（Tag Assistant 接続済み）

### 5.2 タグ①の発火確認（スクロール）

1. example.com のページで下までスクロール
2. Tag Assistant に戻り、左ペインのイベント一覧を確認
3. 期待される表示:
   - `Custom HTML - Scroll Depth (v2)` が25%/50%/75%/90% の各ポイントで発火 → ✅ OK
4. 発火しない場合のチェック:
   - 「Tags Not Fired」欄に該当タグがある → トリガー条件を確認
   - そもそも Custom HTML タグが見えない → タグ作成・保存・**プレビュー再起動**を実施

### 5.3 タグ②の発火確認（CTAクリック）

1. example.com のページ内「お問い合わせ」リンク（hero / footer / 中間）をクリック
2. Tag Assistant に戻り、`Custom HTML - CTA Click (v2)` の発火を確認
3. イベント詳細画面で `cta_location` / `cta_type` / `cta_purpose` / `cta_id` / `cta_text` / `page_path` のパラメータがセットされているか確認
4. 期待される `cta_location`: `hero` / `mid_page` / `footer`（自動判定）

### 5.4 タグ③の発火確認（フォーム）

1. `https://www.example.com/contact/` を開く
2. お名前欄をクリック（フォーカスイン） → Tag Assistant で `form_start` イベントを確認
3. 「お名前」「メール」等にダミーテキストを入力（送信はしない）
4. ブラウザのタブを閉じる前にコンソールで `window.dispatchEvent(new Event('beforeunload'))` を実行 → `form_abandon` を発火させて確認
5. フォーム送信ボタンを実際に押す（=テスト送信） → `contact_finish` を確認
   - ⚠️ 注意: 実フォーム送信なので、テスト内容を「テスト - AIフローアーキテクト弊社検証」等で明記

### 5.5 GA4 DebugView でも確認（補助）

1. GA4管理画面（プロパティID `__GA4_PROPID__`）→ 左メニュー「設定」→「DebugView」
2. プレビューで開いているブラウザのデバイスIDが DebugView に表示される
3. リアルタイムで `scroll_depth` / `cta_click` / `form_start` イベントが流れることを確認

---

## 6. 公開（バージョン管理）

### 6.1 公開前の最終確認

- 一時停止した旧タグが「タグ一覧」で「**一時停止**」表示になっていること
- 新タグ3つが「**有効**」表示で「**最終公開バージョン**」以降に追加されたこと
- プレビューで全て発火確認済みであること

### 6.2 公開操作

1. GTM管理画面 右上「**送信**」をクリック
2. 「バージョン名」: `2026-05-16_タグ①②③トリガー修正_Custom_HTML版`
3. 「バージョンの説明」:
   ```
   B⑤ 5/15 BQ実測検証でscroll/cta/form系イベントが0件継続を確認。
   タグ①②③をCustom HTML版（汎用セレクタ）に切替・組み込みトリガー版を一時停止。
   旧タグは履歴保全のため削除せず一時停止のみ。
   ```
4. 「公開」をクリック
5. 公開完了画面で バージョン番号（例: バージョン3）を控える

### 6.3 ロールバック手順（万が一の場合）

- GTM管理画面「バージョン」タブ → バージョン2（公開前の最終安定版）→ 「公開」
- バージョン履歴は無期限保持されるので、いつでも復帰可能

---

## 7. 修正後のBQ反映確認（24-48時間後）

修正公開から24時間後（5/16公開 → 5/17 早朝）に以下を実行:

### 7.1 1次確認（5/17 早朝）

```bash
cd ~/projects/ark-analytics
bq query --use_legacy_sql=false --project_id=__ARK_PROJECT__ '
SELECT
  PARSE_DATE("%Y%m%d", _TABLE_SUFFIX) AS event_date,
  event_name,
  COUNT(*) AS cnt
FROM `__ARK_PROJECT__.__GA4_DATASET__.events_*`
WHERE _TABLE_SUFFIX >= "20260516"
  AND event_name IN ("scroll_depth","cta_click","form_start","form_abandon")
GROUP BY event_date, event_name
ORDER BY event_date DESC, event_name
'
```

期待値: 各イベントが少なくとも 1件以上発火していること。

### 7.2 2次確認（5/19）

修正後72時間（5/18データ反映）で安定状態を確認:

```bash
bq query --use_legacy_sql=false --project_id=__ARK_PROJECT__ '
SELECT event_name, COUNT(*) AS total
FROM `__ARK_PROJECT__.__GA4_DATASET__.events_*`
WHERE _TABLE_SUFFIX BETWEEN "20260516" AND "20260518"
  AND event_name IN ("scroll_depth","cta_click","form_start","form_abandon")
GROUP BY event_name
'
```

期待値:
- `scroll_depth`: 100件以上（page_view 1日30件 × 4マイルストーン × 3日）
- `cta_click`: 5件以上
- `form_start`: 2件以上
- `form_abandon`: 0件でも可（前述の制限事項あり）

### 7.3 Looker Studio 反映確認

修正後72-96時間（5/19-5/20）で:
- Looker Studio ダッシュボード「ページ別パフォーマンス」タブを開く
- `scroll_90pct_rate` 列に0でない値が表示されていることを確認
- 「ファネル分析」タブで `funnel_step4_form_start` に値が表示されていることを確認

---

## 8. トラブルシューティング

| 症状 | 原因の可能性 | 対処 |
|---|---|---|
| プレビューで発火表示はあるがGA4 DebugViewに来ない | GA4 構成タグ（測定ID設定済み）の前に Custom HTML タグが発火している | タグの「タグの順序付け」で GA4構成タグ後発に設定 |
| GA4 DebugView に来るがBQに来ない（24h後） | BigQuery Export が遅延 | GCP Console → BigQuery → データ転送 で Export ステータス確認 |
| `scroll_pct` パラメータがBQで NULL | GTMタグが Built-in Scroll Depth Trigger を使っており、パラメータ名が `percent_scrolled` になっている | Custom HTML 版に切替 |
| Form の `<input>` クリックで `form_start` が発火しない | `document.querySelector('form')` が `<form name="form1">` を取れていない可能性 | ブラウザコンソールで `document.querySelector('form')` を実行し、`HTMLFormElement` が返ることを確認 |
| `cta_click` が問合せリンクで発火しない | `a[href*="/contact"]` セレクタにマッチしていない | リンクの実 href が `/contact/` でなく `/contact.html` などになっている可能性。ブラウザ DevTools で確認 |

---

## 9. 完了チェックリスト（実施後に確認）

- [ ] 弊社担当者アカウントで GTM-XXXXXXX にアクセス可能
- [ ] タグ① Custom HTML - Scroll Depth (v2) 作成・保存・プレビュー発火確認
- [ ] タグ② Custom HTML - CTA Click (v2) 作成・保存・プレビュー発火確認
- [ ] タグ③ Custom HTML - Form Operations (v2) 作成・保存・プレビュー発火確認
- [ ] 旧Built-inトリガー版タグ3つを「一時停止」設定（削除ではない）
- [ ] バージョン名・説明を明記して「公開」
- [ ] 公開バージョン番号を本ドキュメントの末尾に追記
- [ ] 24h後（5/17）のBQ 1次確認実行
- [ ] 72h後（5/19）のBQ 2次確認実行
- [ ] Looker Studio で `scroll_90pct_rate` / `funnel_step4_form_start` の表示確認

---

## 付録A: クライアントへのGTM招待依頼DMドラフト

招待未済の場合のみ、Coconala DM（https://coconala.com/mypage/direct_message/9590324）で**ユーザー手動送信**:

```
（クライアント企業） ご担当者様

お世話になっております。
AIフローアーキテクトでございます。

本日（5/15）の BigQuery 実測検証で
scroll_depth / cta_click / form_start イベントの
発火状況確認を進めておりますが、
GTM管理画面（GTM-XXXXXXX）の設定内容との突合せが必要になりました。

つきましては弊社作業用アカウント（{{ARK_OPERATOR_EMAIL}}）を
GTMコンテナの「公開」権限で招待いただけますでしょうか。

招待手順:
① https://tagmanager.google.com/ にログイン
② コンテナ GTM-XXXXXXX を開く
③ 左下「管理」→「ユーザー管理」→「+」
④ メールアドレス: {{ARK_OPERATOR_EMAIL}}
⑤ コンテナ権限: 「公開」を選択

権限付与後、弊社側でトリガー条件の調整・修正を実施し、
公開作業まで代行させていただきます（5/16中）。

ご面倒をおかけいたしますが、よろしくお願いいたします。

AIフローアーキテクト
```

---

## 付録B: 公開バージョン番号記録

実施後にここへ追記:

| 公開日時 | バージョン番号 | バージョン名 | 公開者 |
|---|---|---|---|
| 2026-05-XX HH:MM | （実施後記入） | 2026-05-16_タグ①②③トリガー修正_Custom_HTML版 | 弊社担当者 |

---

*このドキュメントは `~/projects/ark-analytics/docs/GTM_TRIGGER_FIX_PROCEDURE.md`*  
*関連: `docs/GTM_TAGS.md`（タグHTMLコード全文）/ `KNOWLEDGE.md`（2026-05-15: B⑤ GTM発火状況 代行検証 結果）*
