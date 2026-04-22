# GTMカスタムイベント タグコード集

ark-hd.co.jpのGA4×BQ分析基盤で計測するカスタムイベントのGTMタグコードです。  
GTM（Googleタグマネージャー）に貼り付けてご利用ください。

---

## 前提

- 計測先: **GA4 測定ID** を使用（GTMの「Google タグ」設定済みのもの）
- イベントはすべて `gtag('event', ...)` 経由で送信
- BQエクスポートにより `analytics_386840839.events_*` テーブルに自動反映（約24時間後）

---

## ① スクロール深度トラッキング（25% / 50% / 75% / 90%）

### タグ種別
カスタムHTML

### タグコード

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
        gtag('event', 'scroll_depth', {
          'scroll_pct': m,
          'page_path': window.location.pathname
        });
      }
    });
  }

  window.addEventListener('scroll', onScroll, { passive: true });
})();
</script>
```

### トリガー
- All Pages（ページビュー時に一度だけ登録）

### BQでの確認クエリ
```sql
SELECT
  event_name,
  (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'scroll_pct') AS scroll_pct,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_path') AS page_path,
  COUNT(*) AS cnt
FROM `ark-hd-analytics.analytics_386840839.events_*`
WHERE event_name = 'scroll_depth'
  AND _TABLE_SUFFIX >= FORMAT_DATE('%Y%m%d', DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY))
GROUP BY 1,2,3
ORDER BY 2, cnt DESC
```

---

## ② CTAクリックトラッキング

### CTAパラメータ命名ルール（2026-04-16 追加）

後からの分析・比較を容易にするため、以下の命名ルールを統一して使用する。

| パラメータ名 | 意味 | 値の例 |
|------------|------|--------|
| `cta_location` | ページ上の位置 | `hero` / `mid_page` / `footer` / `sidebar` |
| `cta_type` | CTAの種別 | `button` / `text_link` / `banner` / `nav` |
| `cta_purpose` | CTAの目的 | `contact` / `download` / `consult` / `inquiry` |
| `cta_id` | CTA識別名（一意） | `hero-contact-btn` / `footer-download-link` |
| `cta_text` | ボタンのテキスト（50文字以内） | `お問い合わせはこちら` |
| `page_path` | ページパス | `/` / `/contact/` |

**位置の判定基準（自動検出）**

| 位置 | 判定ロジック |
|------|------------|
| `hero` | ページ上部 33% 以内（または `data-cta-location="hero"` 属性） |
| `mid_page` | ページ中間 33〜66%（または `data-cta-location="mid_page"` 属性） |
| `footer` | ページ下部 66% 以降（または `data-cta-location="footer"` 属性） |
| `sidebar` | `data-cta-location="sidebar"` 属性が付いている場合 |

**種別の判定基準（自動検出）**

| 種別 | 判定ロジック |
|------|------------|
| `button` | `<button>` 要素、または `.btn-*` / `.cta-*` クラス（または `data-cta-type="button"` 属性） |
| `text_link` | `<a>` 要素でボタンクラスなし |
| `banner` | `data-cta-type="banner"` 属性が付いている場合 |
| `nav` | `<nav>` 内の要素（または `data-cta-type="nav"` 属性） |

> **HTML属性で上書き可能**: `data-cta-location` / `data-cta-type` 属性を要素に付ければ自動検出より優先されます。
> 例: `<a href="/contact/" data-cta data-cta-location="hero" data-cta-type="button">お問い合わせ</a>`

---

### 対象要素
`.cta-button`、`a[href*="contact"]`、`.btn-contact`、`[data-cta]` などのCTAボタン

### タグ種別
カスタムHTML

### タグコード

```html
<script>
(function() {
  var ctaSelectors = [
    '.cta-button',
    '.btn-contact',
    'a[href*="/contact"]',
    'a[href*="contact.html"]',
    '[data-cta]'
  ];

  // cta_location を判定（data属性優先 → スクロール位置で自動判定）
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

  // cta_type を判定（data属性優先 → 要素・クラスで自動判定）
  function getCtaType(el) {
    if (el.dataset.ctaType) return el.dataset.ctaType;
    if (el.closest('nav')) return 'nav';
    if (el.tagName === 'BUTTON' ||
        el.className.match(/btn|cta/i)) return 'button';
    if (el.tagName === 'A') return 'text_link';
    return 'button';
  }

  // cta_purpose を判定（data属性優先 → href/クラスで自動推定）
  function getCtaPurpose(el) {
    if (el.dataset.ctaPurpose) return el.dataset.ctaPurpose;
    var href = el.href || '';
    var text = el.innerText || '';
    if (/contact|問い合わせ|相談/.test(href + text)) return 'contact';
    if (/download|dl|資料/.test(href + text)) return 'download';
    if (/consult|コンサル|無料相談/.test(href + text)) return 'consult';
    if (/inquiry|お問い合わせ/.test(href + text)) return 'inquiry';
    return 'contact';
  }

  // cta_id を取得（data属性優先 → location+type で自動生成）
  function getCtaId(el, location, type) {
    if (el.dataset.ctaId) return el.dataset.ctaId;
    if (el.id) return el.id;
    return location + '-' + type;
  }

  document.addEventListener('click', function(e) {
    var target = e.target;
    for (var i = 0; i < ctaSelectors.length; i++) {
      var el = target.closest(ctaSelectors[i]);
      if (el) {
        var loc  = getCtaLocation(el);
        var type = getCtaType(el);
        gtag('event', 'cta_click', {
          'cta_location': loc,
          'cta_type':     type,
          'cta_purpose':  getCtaPurpose(el),
          'cta_id':       getCtaId(el, loc, type),
          'cta_text':     el.innerText.trim().substring(0, 50),
          'page_path':    window.location.pathname
        });
        break;
      }
    }
  });
})();
</script>
```

### トリガー
- All Pages

### BQでの確認クエリ
```sql
SELECT
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'cta_location') AS cta_location,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'cta_type')     AS cta_type,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'cta_purpose')  AS cta_purpose,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'cta_id')       AS cta_id,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'cta_text')     AS cta_text,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_path')    AS page_path,
  COUNT(*) AS clicks
FROM `ark-hd-analytics.analytics_386840839.events_*`
WHERE event_name = 'cta_click'
  AND _TABLE_SUFFIX >= FORMAT_DATE('%Y%m%d', DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY))
GROUP BY 1,2,3,4
ORDER BY clicks DESC
LIMIT 20
```

---

## ③ フォーム操作トラッキング（開始 / 途中離脱 / 送信完了）

### タグ種別
カスタムHTML

### タグコード

```html
<script>
(function() {
  var form = document.querySelector('form');
  if (!form) return;

  var started = false;

  // フォーム入力開始
  form.addEventListener('focusin', function(e) {
    if (!started && e.target.tagName !== 'BUTTON') {
      started = true;
      gtag('event', 'form_start', {
        'form_id': form.id || form.name || 'contact_form',
        'page_path': window.location.pathname
      });
    }
  });

  // フォーム送信完了
  form.addEventListener('submit', function() {
    gtag('event', 'contact_finish', {
      'form_id': form.id || form.name || 'contact_form',
      'page_path': window.location.pathname
    });
  });

  // ページ離脱時に入力途中かチェック
  window.addEventListener('beforeunload', function() {
    if (started) {
      var hasInput = false;
      var inputs = form.querySelectorAll('input, textarea, select');
      inputs.forEach(function(el) {
        if (el.value && el.value.trim() !== '') hasInput = true;
      });
      if (hasInput) {
        gtag('event', 'form_abandon', {
          'form_id': form.id || form.name || 'contact_form',
          'page_path': window.location.pathname
        });
      }
    }
  });
})();
</script>
```

### トリガー
- フォームが存在するページのみ（例: `/contact/` を含むURLに限定）

### 計測イベント一覧

| イベント名 | タイミング | BQ上のevent_name |
|-----------|-----------|-----------------|
| form_start | フォームに最初にフォーカス | `form_start` |
| contact_finish | フォーム送信ボタン押下 | `contact_finish` |
| form_abandon | 入力途中でページ離脱 | `form_abandon` |

> **注意**: `contact_finish` は既存のコンバージョンイベントと同名です。GA4の既存設定がある場合は重複しないよう確認してください。

### BQでの確認クエリ
```sql
SELECT
  event_name,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_path') AS page_path,
  COUNT(*) AS cnt
FROM `ark-hd-analytics.analytics_386840839.events_*`
WHERE event_name IN ('form_start', 'contact_finish', 'form_abandon')
  AND _TABLE_SUFFIX >= FORMAT_DATE('%Y%m%d', DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
GROUP BY 1,2
ORDER BY page_path, event_name
```

---

## GTMへの設定手順

1. GTMにログイン → コンテナを選択
2. 「タグ」→「新規」→ タグの種類: **カスタムHTML**
3. 上記コードを貼り付け
4. トリガーを設定（All Pages または特定ページ）
5. 「保存」→「プレビュー」で動作確認
6. 問題なければ「公開」

---

## GA4上での確認

設定後24〜48時間で、GA4管理画面の「イベント」一覧に以下が表示されます：
- `scroll_depth`（scroll_pct パラメータ付き）
- `cta_click`（cta_text パラメータ付き）
- `form_start`
- `contact_finish`
- `form_abandon`

BQには翌日以降にエクスポートされます。
