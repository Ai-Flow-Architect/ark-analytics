# GTMカスタムイベント タグコード集（v2・dataLayer.push 方式）

example.com の GA4×BQ分析基盤で計測するカスタムイベントのGTMタグコードです。

> ## ⚠️ v2 改訂（2026-05-15）— gtag() → dataLayer.push() 全面移行
>
> 旧版は Custom HTML 内で `gtag('event',...)` を直接呼んでいたが、当サイトの
> GA4 は **GTM 経由読み込み**（サイトHTMLに gtag.js / G- 記述なし）のため、
> 素の `gtag()` が GA4 設定と結線されず **イベントが送信されずに静かに失敗**
> していた（4/22-5/14 BQ 0件の真因）。
>
> v2 では **Custom HTML は `dataLayer.push()` のみ** を行い、GA4 への送信は
> **GA4 イベントタグ**（測定ID `G-XXXXXXXXXX`）が担う GTM 正準パターンに変更。
>
> GTM 側の配線（データレイヤー変数 / カスタムイベントトリガー / GA4イベントタグ）
> の完全な設定値は **[`GTM_FIX_PACKAGE_v2.md`](GTM_FIX_PACKAGE_v2.md)** を参照。
> 本書は **Custom HTML タグのコード全文** の正本（authoritative source）。

---

## 前提（v2）

- 計測先: **GA4 測定ID `G-XXXXXXXXXX`**（ストリームID __GA4_STREAM_ID__ / GTM-XXXXXXX 経由）
- Custom HTML タグは `window.dataLayer.push({ event:'ce_xxx', ... })` のみ実行
- イベント名は `ce_` プレフィックスで GA4 イベント名（scroll_depth 等）と分離（名前衝突・無限ループ防止）
- GA4 への正規イベント送信は GA4 イベントタグが担当（カスタムイベントトリガーで発火）
- BQエクスポートにより `__GA4_DATASET__.events_*` に約24-48時間後反映
- `contact_finish` は既存 URL Page View トリガー（`/contact/?mode=finish`）で稼働中のため、
  **フォームタグからは送出しない**（二重計上防止）。フォームタグは form_start / form_abandon のみ。

---

## ① スクロール深度トラッキング（25% / 50% / 75% / 90%）

### タグ種別
カスタムHTML（タグ名: `GA4 - スクロール深度計測`）

### タグコード（v2・全文置換用）

```html
<script>
/* v2.1 hardened 2026-05-15 (/harden: dataLayerガード冒頭化 / 90%後listener解除 / null安全) */
(function() {
  window.dataLayer = window.dataLayer || [];
  var milestones = [25, 50, 75, 90];
  var fired = {};

  function getScrollPct() {
    var scrollTop = window.pageYOffset || document.documentElement.scrollTop || 0;
    var body = document.body || {};
    var docEl = document.documentElement || {};
    var docHeight = Math.max(body.scrollHeight || 0, docEl.scrollHeight || 0) - window.innerHeight;
    return docHeight > 0 ? Math.round(scrollTop / docHeight * 100) : 0;
  }

  function onScroll() {
    var pct = getScrollPct();
    milestones.forEach(function(m) {
      if (pct >= m && !fired[m]) {
        fired[m] = true;
        window.dataLayer.push({
          'event': 'ce_scroll_depth',
          'sd_scroll_pct': m,
          'sd_page_path': window.location.pathname
        });
      }
    });
    if (fired[90]) window.removeEventListener('scroll', onScroll);
  }

  window.addEventListener('scroll', onScroll, { passive: true });
})();
</script>
```

### トリガー
- All Pages（変更なし）

### GA4 への送出
GA4イベントタグ `GA4 Event - Scroll Depth`（測定ID `G-XXXXXXXXXX` / イベント名 `scroll_depth` /
params `scroll_pct`,`page_path` / トリガー `CE - Scroll Depth`）が担当。詳細は v2 §5。

### BQ確認クエリ
```sql
SELECT
  event_name,
  (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'scroll_pct') AS scroll_pct,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_path') AS page_path,
  COUNT(*) AS cnt
FROM `__ARK_PROJECT__.__GA4_DATASET__.events_*`
WHERE event_name = 'scroll_depth'
  AND _TABLE_SUFFIX >= FORMAT_DATE('%Y%m%d', DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY))
GROUP BY 1,2,3
ORDER BY 2, cnt DESC
```

---

## ② CTAクリックトラッキング

### CTAパラメータ命名ルール

| パラメータ名 | 意味 | 値の例 |
|------------|------|--------|
| `cta_location` | ページ上の位置 | `hero` / `mid_page` / `footer` |
| `cta_type` | CTAの種別 | `button` / `text_link` / `nav` |
| `cta_purpose` | CTAの目的 | `contact` / `download` / `consult` |
| `cta_id` | CTA識別名（一意） | `hero-contact-btn` |
| `cta_text` | ボタンのテキスト（50文字以内） | `お問い合わせはこちら` |
| `page_path` | ページパス | `/` / `/contact/` |

> **HTML属性で上書き可能**: `data-cta-location` / `data-cta-type` / `data-cta-purpose` /
> `data-cta-id` 属性を要素に付ければ自動検出より優先される。

### 対象要素
`.cta-button`、`a[href*="/contact"]`、`.btn-contact`、`[data-cta]` 等のCTAボタン

### タグ種別
カスタムHTML（タグ名: `GA4 - CTAクリック計測`）

### タグコード（v2・全文置換用）

```html
<script>
/* v2.1 hardened 2026-05-15 (/harden: 重複登録ガード / テキストノード対応 / className SVG安全 / innerText null安全) */
(function() {
  if (window.__ceCtaBound) return;
  window.__ceCtaBound = true;
  window.dataLayer = window.dataLayer || [];
  var ctaSelectors = [
    '.cta-button', '.btn-contact',
    'a[href*="/contact"]', 'a[href*="contact.html"]', '[data-cta]'
  ];

  function getCtaLocation(el) {
    if (el.dataset && el.dataset.ctaLocation) return el.dataset.ctaLocation;
    var rect = el.getBoundingClientRect();
    var absTop = rect.top + window.pageYOffset;
    var docHeight = document.documentElement.scrollHeight || 0;
    var pct = docHeight > 0 ? absTop / docHeight : 0;
    if (pct < 0.33) return 'hero';
    if (pct < 0.66) return 'mid_page';
    return 'footer';
  }
  function getCtaType(el) {
    if (el.dataset && el.dataset.ctaType) return el.dataset.ctaType;
    if (el.closest('nav')) return 'nav';
    var cls = (typeof el.className === 'string') ? el.className : '';
    if (el.tagName === 'BUTTON' || /btn|cta/i.test(cls)) return 'button';
    if (el.tagName === 'A') return 'text_link';
    return 'button';
  }
  function getCtaPurpose(el) {
    if (el.dataset && el.dataset.ctaPurpose) return el.dataset.ctaPurpose;
    var s = (el.href || '') + (el.innerText || '');
    if (/contact|問い合わせ|相談/.test(s)) return 'contact';
    if (/download|dl|資料/.test(s)) return 'download';
    if (/consult|コンサル|無料相談/.test(s)) return 'consult';
    return 'contact';
  }
  function getCtaId(el, loc, type) {
    if (el.dataset && el.dataset.ctaId) return el.dataset.ctaId;
    if (el.id) return el.id;
    return loc + '-' + type;
  }

  document.addEventListener('click', function(e) {
    var target = e.target;
    if (target && target.nodeType === 3) target = target.parentNode; /* テキストノード→親要素 */
    if (!target || target.nodeType !== 1 || !target.closest) return;
    for (var i = 0; i < ctaSelectors.length; i++) {
      var el = target.closest(ctaSelectors[i]);
      if (el) {
        var loc = getCtaLocation(el);
        var type = getCtaType(el);
        window.dataLayer.push({
          'event': 'ce_cta_click',
          'cc_cta_location': loc,
          'cc_cta_type': type,
          'cc_cta_purpose': getCtaPurpose(el),
          'cc_cta_id': getCtaId(el, loc, type),
          'cc_cta_text': ((el.innerText || el.textContent || '').trim()).substring(0, 50),
          'cc_page_path': window.location.pathname
        });
        break;
      }
    }
  });
})();
</script>
```

### トリガー
- All Pages（変更なし）

### GA4 への送出
GA4イベントタグ `GA4 Event - CTA Click`（測定ID `G-XXXXXXXXXX` / イベント名 `cta_click` /
params 6種 / トリガー `CE - CTA Click`）が担当。詳細は v2 §5。

### BQ確認クエリ
```sql
SELECT
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'cta_location') AS cta_location,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'cta_type')     AS cta_type,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'cta_purpose')  AS cta_purpose,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'cta_id')       AS cta_id,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'cta_text')     AS cta_text,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_path')    AS page_path,
  COUNT(*) AS clicks
FROM `__ARK_PROJECT__.__GA4_DATASET__.events_*`
WHERE event_name = 'cta_click'
  AND _TABLE_SUFFIX >= FORMAT_DATE('%Y%m%d', DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY))
GROUP BY 1,2,3,4,5,6
ORDER BY clicks DESC
LIMIT 20
```

---

## ③ フォーム操作トラッキング（開始 / 途中離脱）

> **重要**: `contact_finish`（送信完了）は既存の URL Page View トリガー（`/contact/?mode=finish`）
> で稼働中のため、本タグからは **送出しない**（二重計上防止）。本タグは `form_start` /
> `form_abandon` のみ。

### タグ種別
カスタムHTML（タグ名: `GA4 - フォーム操作計測`）

### タグコード（v2・全文置換用）

```html
<script>
/* v2.1 hardened 2026-05-15 (/harden 🔴: DOM未構築ガード / form[name="form1"]優先 / 遅延描画リトライ / 重複防止) */
(function() {
  window.dataLayer = window.dataLayer || [];

  function init() {
    if (window.__ceFormBound) return;
    /* 複数form対策: contactフォーム(form1)を優先。無ければ最初のform */
    var form = document.querySelector('form[name="form1"]')
            || document.querySelector('#mailform form, form#mailform')
            || document.querySelector('form');
    if (!form) return; /* まだ未描画 → 下のリトライで再入する */
    window.__ceFormBound = true;
    var started = false;

    form.addEventListener('focusin', function(e) {
      if (!started && e.target && e.target.tagName !== 'BUTTON') {
        started = true;
        window.dataLayer.push({
          'event': 'ce_form_event',
          'fe_form_action': 'form_start',
          'fe_form_id': form.id || form.name || 'contact_form',
          'fe_page_path': window.location.pathname
        });
      }
    });

    window.addEventListener('beforeunload', function() {
      if (!started) return;
      var hasInput = false;
      form.querySelectorAll('input, textarea, select').forEach(function(el) {
        if (el.value && String(el.value).trim() !== '') hasInput = true;
      });
      if (hasInput) {
        window.dataLayer.push({
          'event': 'ce_form_event',
          'fe_form_action': 'form_abandon',
          'fe_form_id': form.id || form.name || 'contact_form',
          'fe_page_path': window.location.pathname
        });
      }
    });
  }

  /* GTM Page View は gtm.js 時点(DOM未構築)で発火しうる → DOM確定を待つ */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
    /* 遅延描画フォームの保険: 最大3秒 (500ms×6) リトライ */
    var tries = 0;
    var timer = setInterval(function() {
      tries++;
      if (window.__ceFormBound || tries > 6) { clearInterval(timer); return; }
      init();
    }, 500);
  } else {
    init();
  }
})();
</script>
```

### トリガー
- Contact Page - Page View（変更なし）

### GA4 への送出
GA4イベントタグ `GA4 Event - Form`（測定ID `G-XXXXXXXXXX` / イベント名 `{{DLV - fe_form_action}}`
= form_start / form_abandon に動的展開 / params form_id,page_path / トリガー `CE - Form Event`）。詳細は v2 §5。

### 計測イベント一覧

| イベント名 | タイミング | 送出元 |
|-----------|-----------|--------|
| form_start | フォームに最初にフォーカス | 本タグ → ce_form_event → GA4イベントタグ |
| form_abandon | 入力途中でページ離脱 | 本タグ → ce_form_event → GA4イベントタグ |
| contact_finish | 送信完了 | **既存 URL Page View トリガー（本タグ対象外）** |

> **form_abandon の制限事項**: 近年のブラウザ（Chrome 90+ / Safari 14+）では
> `beforeunload` 内の処理がブロックされる場合があり、最大40%程度の取得漏れの可能性。
> 主要指標は scroll_depth / cta_click / form_start の3つに集中。
> 将来改善: `navigator.sendBeacon` 化（追加見積もり対象）。

### BQ確認クエリ
```sql
SELECT
  event_name,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_path') AS page_path,
  COUNT(*) AS cnt
FROM `__ARK_PROJECT__.__GA4_DATASET__.events_*`
WHERE event_name IN ('form_start', 'contact_finish', 'form_abandon')
  AND _TABLE_SUFFIX >= FORMAT_DATE('%Y%m%d', DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
GROUP BY 1,2
ORDER BY page_path, event_name
```

---

## GTMへの設定手順（v2・概要）

詳細・コピペ用設定値は [`GTM_FIX_PACKAGE_v2.md`](GTM_FIX_PACKAGE_v2.md) を参照。概要のみ:

1. **Custom HTML タグ①②③** を本書のコードに全文置換（トリガーは現状維持）
2. **データレイヤー変数 11個** 作成（sd_* / cc_* / fe_* 各パラメータ）
3. **カスタムイベントトリガー 3個** 作成（`ce_scroll_depth` / `ce_cta_click` / `ce_form_event`）
4. **GA4イベントタグ 3個** 作成（測定ID `G-XXXXXXXXXX` / 各カスタムイベントトリガーで発火）
5. **プレビュー** で3イベント Fired + GA4 DebugView 着弾確認
6. **公開**（バージョン名明記）
7. 24-48h後に **BQ確認クエリ** で各イベント反映を確認

---

## GA4上での確認

公開後24〜48時間で、GA4管理画面の「イベント」一覧に以下が表示される:
- `scroll_depth`（`scroll_pct` パラメータ付き）
- `cta_click`（`cta_*` パラメータ付き）
- `form_start` / `form_abandon`
- `contact_finish`（既存 URL トリガー由来・継続）

BQには翌日以降にエクスポートされる。万一 BQ に出ない場合は
GA4→BQ エクスポートの event 設定を確認（v2 §6 E-4 コンティンジェンシー手順）。

---

*このドキュメントは `~/projects/ark-analytics/docs/GTM_TAGS.md`（Custom HTML コード正本）*
*関連: `GTM_FIX_PACKAGE_v2.md`（GTM配線の正本）/ `KNOWLEDGE.md`（2026-05-15 真因確定）*
