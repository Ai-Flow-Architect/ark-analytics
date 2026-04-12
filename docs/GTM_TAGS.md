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

### 対象要素
`.cta-button`、`a[href*="contact"]`、`.btn-contact` などのCTAボタン

### タグ種別
カスタムHTML

### タグコード

```html
<script>
(function() {
  // CTAとして計測するセレクタ一覧（必要に応じて追加）
  var ctaSelectors = [
    '.cta-button',
    '.btn-contact',
    'a[href*="/contact"]',
    'a[href*="contact.html"]',
    '[data-cta]'
  ];

  document.addEventListener('click', function(e) {
    var target = e.target;
    // クリックした要素または親要素がCTAに一致するか確認
    for (var i = 0; i < ctaSelectors.length; i++) {
      var el = target.closest(ctaSelectors[i]);
      if (el) {
        gtag('event', 'cta_click', {
          'cta_text': el.innerText.trim().substring(0, 50),
          'cta_url': el.href || '',
          'page_path': window.location.pathname
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
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'cta_text') AS cta_text,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_path') AS page_path,
  COUNT(*) AS clicks
FROM `ark-hd-analytics.analytics_386840839.events_*`
WHERE event_name = 'cta_click'
  AND _TABLE_SUFFIX >= FORMAT_DATE('%Y%m%d', DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY))
GROUP BY 1,2
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
