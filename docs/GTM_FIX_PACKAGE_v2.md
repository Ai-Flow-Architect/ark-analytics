# GTM 修正パッケージ v2（真因確定版・5/15）

最終更新: 2026-05-15  
対象コンテナ: `GTM-5B3L5372`（株式会社アテンド ark-hd.co.jp）  
GA4 測定ID: **`G-Y95H1GWBB7`**（ストリームID 5511077682）  
**本書が正（authoritative）。`GTM_TRIGGER_FIX_PROCEDURE.md` は真因誤認のため superseded。**

---

## 0. 真因（5/15 ライブ検証で確定）

### 確定した事実

| 検証 | 結果 |
|------|------|
| GTM タグ一覧 | 3タグ（CTA/Scroll/Form）全て Custom HTML・公開済（24日前=4/21）・トリガーも妥当 |
| Scroll タグの中身 | `gtag('event','scroll_depth',{...})` を使用。GTM自身が「gtag コマンドは正しく動作しないことがある」と警告表示 |
| サイトHTML | `gtag.js`/`G-` の直接記述なし。GA4は GTM-5B3L5372 経由のみで読み込み |
| GA4 拡張計測 | ON（スクロール数・ページビュー数・離脱クリック） |
| BQ 全イベント（4/1〜5/14）| `page_view` / `session_start` / `first_visit` / `contact_finish` の **4種のみ**。`user_engagement`・拡張計測 `scroll`・`click` すら存在しない |

### 真因（2層）

1. **【主因】Custom HTML タグの `gtag()` が GA4 に到達していない**
   - GA4 が GTM 経由読み込みのため、Custom HTML 内の素の `gtag()` は GA4 設定と結線されておらず、イベントが送信されずに静かに失敗
   - `contact_finish` だけ生きているのは、URL `/contact/?mode=finish` の Page View トリガー由来で gtag に依存しないため（BQ で `form_id`/`page_path` paramを持たない事実と整合）

2. **【副因・コンティンジェンシー】GA4→BQ エクスポートに event 制限の疑い**
   - 拡張計測 ON なのに BQ に `scroll`/`user_engagement` が皆無 → GA4 BQ リンクに event 設定がある可能性
   - 主因修正後も BQ に出ない場合の切り分け手順を §6 に記載

---

## 1. 修正アーキテクチャ

```
[Custom HTML タグ①②③]  ← 修正（gtag → dataLayer.push）
    window.dataLayer.push({ event:'ce_xxx', ... })
        │
        ▼
[カスタムイベント トリガー ①②③]  ← 新規3個
    ce_scroll_depth / ce_cta_click / ce_form_event
        │
        ▼
[GA4 イベント タグ ①②③]  ← 新規3個（測定ID: G-Y95H1GWBB7）
    event_name: scroll_depth / cta_click / {{DLV - form_action}}
    params: データレイヤー変数からマッピング
        │
        ▼
    GA4（G-Y95H1GWBB7）→ BigQuery（24-48h後反映）
```

**重要な設計判断**:
- `contact_finish` は既存 URL トリガーで正常稼働中（36件）→ **フォームタグからは contact_finish を送らない**（二重計上防止）。フォームタグは `form_start` / `form_abandon` のみ。
- イベント名は GTM 側で正規化。dataLayer のイベント名は `ce_` プレフィックスで GA4 イベント名（scroll_depth 等）と分離（無限ループ・名前衝突防止）。
- SQL 側（`scroll_pct` 統一）と完全一致するパラメータ名で送出。

---

## 2. STEP A: Custom HTML タグ3つを修正

### タグ① 「GA4 - スクロール深度計測」 を以下に**全文置換**

```html
<script>
(function() {
  var milestones = [25, 50, 75, 90];
  var fired = {};

  function getScrollPct() {
    var scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    var docHeight = Math.max(
      document.body.scrollHeight, document.documentElement.scrollHeight
    ) - window.innerHeight;
    return docHeight > 0 ? Math.round(scrollTop / docHeight * 100) : 0;
  }

  function onScroll() {
    var pct = getScrollPct();
    milestones.forEach(function(m) {
      if (pct >= m && !fired[m]) {
        fired[m] = true;
        window.dataLayer = window.dataLayer || [];
        window.dataLayer.push({
          'event': 'ce_scroll_depth',
          'sd_scroll_pct': m,
          'sd_page_path': window.location.pathname
        });
      }
    });
  }

  window.addEventListener('scroll', onScroll, { passive: true });
})();
</script>
```

### タグ② 「GA4 - CTAクリック計測」 を以下に**全文置換**

```html
<script>
(function() {
  var ctaSelectors = [
    '.cta-button', '.btn-contact',
    'a[href*="/contact"]', 'a[href*="contact.html"]', '[data-cta]'
  ];

  function getCtaLocation(el) {
    if (el.dataset.ctaLocation) return el.dataset.ctaLocation;
    var rect = el.getBoundingClientRect();
    var absTop = rect.top + window.pageYOffset;
    var docHeight = document.documentElement.scrollHeight;
    var pct = docHeight > 0 ? absTop / docHeight : 0;
    if (pct < 0.33) return 'hero';
    if (pct < 0.66) return 'mid_page';
    return 'footer';
  }
  function getCtaType(el) {
    if (el.dataset.ctaType) return el.dataset.ctaType;
    if (el.closest('nav')) return 'nav';
    if (el.tagName === 'BUTTON' || el.className.match(/btn|cta/i)) return 'button';
    if (el.tagName === 'A') return 'text_link';
    return 'button';
  }
  function getCtaPurpose(el) {
    if (el.dataset.ctaPurpose) return el.dataset.ctaPurpose;
    var s = (el.href || '') + (el.innerText || '');
    if (/contact|問い合わせ|相談/.test(s)) return 'contact';
    if (/download|dl|資料/.test(s)) return 'download';
    if (/consult|コンサル|無料相談/.test(s)) return 'consult';
    return 'contact';
  }
  function getCtaId(el, loc, type) {
    if (el.dataset.ctaId) return el.dataset.ctaId;
    if (el.id) return el.id;
    return loc + '-' + type;
  }

  document.addEventListener('click', function(e) {
    var target = e.target;
    for (var i = 0; i < ctaSelectors.length; i++) {
      var el = target.closest(ctaSelectors[i]);
      if (el) {
        var loc = getCtaLocation(el);
        var type = getCtaType(el);
        window.dataLayer = window.dataLayer || [];
        window.dataLayer.push({
          'event': 'ce_cta_click',
          'cc_cta_location': loc,
          'cc_cta_type': type,
          'cc_cta_purpose': getCtaPurpose(el),
          'cc_cta_id': getCtaId(el, loc, type),
          'cc_cta_text': el.innerText.trim().substring(0, 50),
          'cc_page_path': window.location.pathname
        });
        break;
      }
    }
  });
})();
</script>
```

### タグ③ 「GA4 - フォーム操作計測」 を以下に**全文置換**

> contact_finish は既存 URL トリガーで稼働中のため、本タグからは送出しない（二重計上防止）。form_start / form_abandon のみ。

```html
<script>
(function() {
  var form = document.querySelector('form');
  if (!form) return;
  var started = false;

  form.addEventListener('focusin', function(e) {
    if (!started && e.target.tagName !== 'BUTTON') {
      started = true;
      window.dataLayer = window.dataLayer || [];
      window.dataLayer.push({
        'event': 'ce_form_event',
        'fe_form_action': 'form_start',
        'fe_form_id': form.id || form.name || 'contact_form',
        'fe_page_path': window.location.pathname
      });
    }
  });

  window.addEventListener('beforeunload', function() {
    if (started) {
      var hasInput = false;
      form.querySelectorAll('input, textarea, select').forEach(function(el) {
        if (el.value && el.value.trim() !== '') hasInput = true;
      });
      if (hasInput) {
        window.dataLayer = window.dataLayer || [];
        window.dataLayer.push({
          'event': 'ce_form_event',
          'fe_form_action': 'form_abandon',
          'fe_form_id': form.id || form.name || 'contact_form',
          'fe_page_path': window.location.pathname
        });
      }
    }
  });
})();
</script>
```

トリガーは現状のまま（①② = All Pages / ③ = Contact Page - Page View）で変更不要。

---

## 3. STEP B: データレイヤー変数を作成（変数 → 新規 → データレイヤーの変数）

| 変数名 | データレイヤーの変数名 | 用途 |
|--------|----------------------|------|
| `DLV - sd_scroll_pct` | `sd_scroll_pct` | スクロール率 |
| `DLV - sd_page_path` | `sd_page_path` | スクロール時パス |
| `DLV - cc_cta_location` | `cc_cta_location` | CTA位置 |
| `DLV - cc_cta_type` | `cc_cta_type` | CTA種別 |
| `DLV - cc_cta_purpose` | `cc_cta_purpose` | CTA目的 |
| `DLV - cc_cta_id` | `cc_cta_id` | CTA識別子 |
| `DLV - cc_cta_text` | `cc_cta_text` | CTAテキスト |
| `DLV - cc_page_path` | `cc_page_path` | CTA時パス |
| `DLV - fe_form_action` | `fe_form_action` | form_start / form_abandon |
| `DLV - fe_form_id` | `fe_form_id` | フォームID |
| `DLV - fe_page_path` | `fe_page_path` | フォーム時パス |

データレイヤーのバージョン: いずれも「バージョン 2」（既定）でOK。

---

## 4. STEP C: カスタムイベント トリガーを作成（トリガー → 新規 → カスタムイベント）

| トリガー名 | イベント名 | 条件 |
|-----------|-----------|------|
| `CE - Scroll Depth` | `ce_scroll_depth` | すべてのカスタムイベント |
| `CE - CTA Click` | `ce_cta_click` | すべてのカスタムイベント |
| `CE - Form Event` | `ce_form_event` | すべてのカスタムイベント |

---

## 5. STEP D: GA4 イベントタグを作成（タグ → 新規 → Google アナリティクス: GA4 イベント）

3つとも「測定 ID」欄に **`G-Y95H1GWBB7`** を直接入力。

### GA4イベントタグ① `GA4 Event - Scroll Depth`

| 項目 | 値 |
|------|-----|
| 測定 ID | `G-Y95H1GWBB7` |
| イベント名 | `scroll_depth` |
| イベントパラメータ | `scroll_pct` = `{{DLV - sd_scroll_pct}}` / `page_path` = `{{DLV - sd_page_path}}` |
| トリガー | `CE - Scroll Depth` |

### GA4イベントタグ② `GA4 Event - CTA Click`

| 項目 | 値 |
|------|-----|
| 測定 ID | `G-Y95H1GWBB7` |
| イベント名 | `cta_click` |
| イベントパラメータ | `cta_location`={{DLV - cc_cta_location}} / `cta_type`={{DLV - cc_cta_type}} / `cta_purpose`={{DLV - cc_cta_purpose}} / `cta_id`={{DLV - cc_cta_id}} / `cta_text`={{DLV - cc_cta_text}} / `page_path`={{DLV - cc_page_path}} |
| トリガー | `CE - CTA Click` |

### GA4イベントタグ③ `GA4 Event - Form`

| 項目 | 値 |
|------|-----|
| 測定 ID | `G-Y95H1GWBB7` |
| イベント名 | `{{DLV - fe_form_action}}`（= form_start / form_abandon に動的展開） |
| イベントパラメータ | `form_id`={{DLV - fe_form_id}} / `page_path`={{DLV - fe_page_path}} |
| トリガー | `CE - Form Event` |

---

## 6. STEP E: プレビュー → 公開 → BQ検証

### E-1. プレビュー（公開前 必須）

1. GTM 右上「プレビュー」→ `https://www.ark-hd.co.jp/` を入力して Connect
2. ページをスクロール → Tag Assistant で `GA4 Event - Scroll Depth` が **Fired** になることを確認
3. 「お問い合わせ」リンクをクリック → `GA4 Event - CTA Click` Fired 確認
4. `/contact/` でフォーム入力 → `GA4 Event - Form`（form_start）Fired 確認
5. GA4 リアルタイム → DebugView で scroll_depth / cta_click / form_start イベントが届くことを確認

### E-2. 公開

- 右上「送信」→ バージョン名: `2026-05-16_gtag→dataLayer移行_GA4Event化`
- バージョン説明:
  ```
  5/15 ライブ検証で Custom HTML の gtag() が GA4 未到達と確定。
  3タグを dataLayer.push 化 + GA4 イベントタグ3個 + カスタムイベントトリガー3個 + DLV11個 を新設。
  contact_finish は既存URLトリガー維持（二重計上回避）。
  ```
- 「公開」

### E-3. BQ 反映確認（24h後 = 5/17早朝）

```bash
bq query --use_legacy_sql=false --project_id=ark-hd-analytics '
SELECT event_name, COUNT(*) cnt
FROM `ark-hd-analytics.analytics_386840839.events_*`
WHERE _TABLE_SUFFIX >= "20260516"
  AND event_name IN ("scroll_depth","cta_click","form_start","form_abandon")
GROUP BY event_name ORDER BY cnt DESC'
```

### E-4. 副因コンティンジェンシー（E-3 で依然 0件の場合）

主因修正後も BQ に出ない場合、GA4→BQ エクスポート側の event 設定を疑う:

1. GA4 管理 → サービス間のリンク設定 → BigQuery のリンク → 該当リンクを開く
2. 「データストリームとイベントの設定」でエクスポート対象イベントに制限がないか確認
3. DebugView では出るが BQ に出ない場合 → エクスポート設定側の問題と確定
4. DebugView でも出ない場合 → GTM タグ側の問題が残存（プレビューに戻る）

> この2段構えにより「主因（gtag）」「副因（BQエクスポート）」を確実に切り分けられる。

---

## 7. 完了チェックリスト

- [ ] タグ①②③ の HTML を §2 のコードに全文置換・保存
- [ ] DLV 11個 作成（§3）
- [ ] カスタムイベント トリガー 3個 作成（§4）
- [ ] GA4 イベントタグ 3個 作成・測定ID `G-Y95H1GWBB7` 入力（§5）
- [ ] プレビューで3イベント Fired + DebugView 着弾確認（§6 E-1）
- [ ] 公開（バージョン名明記）（§6 E-2）
- [ ] 5/17 早朝 BQ 反映確認（§6 E-3）
- [ ] 0件継続なら E-4 で BQ エクスポート設定確認
- [ ] 公開バージョン番号を本書 §8 に追記

---

## 8. 公開バージョン記録

| 公開日時 | バージョン番号 | バージョン名 | 公開者 |
|---|---|---|---|
| 2026-05-XX | （実施後記入） | 2026-05-16_gtag→dataLayer移行_GA4Event化 | 弊社担当者 |

---

*このドキュメントは `~/projects/ark-analytics/docs/GTM_FIX_PACKAGE_v2.md`*  
*supersedes: `docs/GTM_TRIGGER_FIX_PROCEDURE.md`（真因誤認版）*  
*関連: `docs/GTM_TAGS.md` / `KNOWLEDGE.md`（2026-05-15 真因確定）/ 5/22 MTG 事前共有3点②*
