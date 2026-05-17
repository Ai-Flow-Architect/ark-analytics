# GTM 修正パッケージ v2（真因確定版・5/15）

最終更新: 2026-05-15  
対象コンテナ: `GTM-XXXXXXX`（（クライアント企業） example.com）  
GA4 測定ID: **`G-XXXXXXXXXX`**（ストリームID __GA4_STREAM_ID__）  
**本書が正（authoritative）。`GTM_TRIGGER_FIX_PROCEDURE.md` は真因誤認のため superseded。**

---

## 0. 真因（5/15 ライブ検証で確定）

### 確定した事実

| 検証 | 結果 |
|------|------|
| GTM タグ一覧 | 3タグ（CTA/Scroll/Form）全て Custom HTML・公開済（24日前=4/21）・トリガーも妥当 |
| Scroll タグの中身 | `gtag('event','scroll_depth',{...})` を使用。GTM自身が「gtag コマンドは正しく動作しないことがある」と警告表示 |
| サイトHTML | `gtag.js`/`G-` の直接記述なし。GA4は GTM-XXXXXXX 経由のみで読み込み |
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
[GA4 イベント タグ ①②③]  ← 新規3個（測定ID: G-XXXXXXXXXX）
    event_name: scroll_depth / cta_click / {{DLV - form_action}}
    params: データレイヤー変数からマッピング
        │
        ▼
    GA4（G-XXXXXXXXXX）→ BigQuery（24-48h後反映）
```

**重要な設計判断**:
- `contact_finish` は既存 URL トリガーで正常稼働中（36件）→ **フォームタグからは contact_finish を送らない**（二重計上防止）。フォームタグは `form_start` / `form_abandon` のみ。
- イベント名は GTM 側で正規化。dataLayer のイベント名は `ce_` プレフィックスで GA4 イベント名（scroll_depth 等）と分離（無限ループ・名前衝突防止）。
- SQL 側（`scroll_pct` 統一）と完全一致するパラメータ名で送出。

---

## 1.5 STEP 0（5/17作業の最初に必ず実施・第4監査人指摘 #1）

> ⚠️ **本ステップを飛ばすと §5 のGA4イベントタグが発火・送信せず、5/17夜に「設計通り作ったのにDebugViewにすら出ない」が発生する。最優先・必須。**

### 背景（物理矛盾の解消）

BQ に `page_view` 802件 / `session_start` 414件 が来ている = **GTMコンテナのどこかで GA4（G-XXXXXXXXXX）を初期化している実体が必ず存在する**（初期化なしに page_view は飛ばない）。しかし5/15のタグ一覧では Custom HTML 3個しか確認できていない。この初期化実体（GA4設定タグ / Google タグ）の所在を特定しないと、新設する GA4 イベントタグが相乗りすべき初期化基盤を参照できない。

### 実施手順

1. GTM「タグ」一覧で **フィルタ無し・全件**表示（フォルダ折りたたみも展開）→ 「Google アナリティクス: GA4 設定」「Google タグ」種別のタグが無いか確認
2. 「変数」→ ユーザー定義変数に「Google アナリティクス設定」変数（`{{GA4 - 設定}}` 等）が無いか確認
3. GTM 上部「Google タグ」タブ（アカウント階層）→ `G-XXXXXXXXXX` の Google タグが管理されていないか確認
4. **判定**:

| 結果 | 対応 |
|------|------|
| GA4設定タグ or GA4設定変数が存在 | §5 のGA4イベントタグは「測定IDを入力」ではなく **その設定タグ/変数を参照**する方式に変更（測定ID一元管理・第4監査人 #1 + Gemini指摘） |
| アカウント階層 Google タグのみで初期化 | §5 のGA4イベントタグは測定ID直接入力 `G-XXXXXXXXXX` で可（但しプレビューで送信を必ず実証） |
| **初期化実体が一切見つからない** | 🔴 §5 の前に **GA4設定タグ（または Google タグ）1個を新設**（測定ID `G-XXXXXXXXXX`・トリガー All Pages）→ その後 §5 のイベントタグはそれを参照。**この新設が無いと一切送信されない** |

5. 特定/新設した初期化タグ名を本書 §8 に追記

---

## 2. STEP A: Custom HTML タグ3つを修正

### タグ① 「GA4 - スクロール深度計測」 を以下に**全文置換**

```html
<script>
/* v2.1 hardened 2026-05-15 (/harden: dataLayerガード冒頭化 / 90%後listener解除 / null安全) */
(function() {
  if (window.__ceScrollBound) return;
  window.__ceScrollBound = true;
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

### タグ② 「GA4 - CTAクリック計測」 を以下に**全文置換**

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

### タグ③ 「GA4 - フォーム操作計測」 を以下に**全文置換**

> contact_finish は既存 URL トリガーで稼働中のため、本タグからは送出しない（二重計上防止）。form_start / form_abandon のみ。

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

トリガーは現状のまま（①② = All Pages / ③ = Contact Page - Page View）で変更不要。
**ただし可能なら③のトリガーを「Contact Page - DOM Ready」に変更推奨**（上記DOMガードで動くが、DOM Readyトリガーなら更に確実）。

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

> ⚠️ **測定IDの指定方法は §1.5 STEP 0 の判定結果に従う（第4監査人 #1 + Gemini指摘）**:
> - GA4設定タグ/設定変数が存在 → 「測定 ID」欄で **その設定タグ/変数を選択**（測定ID直接入力しない・一元管理）
> - アカウント階層 Google タグのみ → 測定ID `G-XXXXXXXXXX` 直接入力可（プレビューで送信を必ず実証）
> - 初期化実体を §1.5 で新設した → 新設タグ/変数を参照
>
> 以下の表は「測定ID直接入力」ケースの値。設定タグ参照ケースは「測定ID」を「設定タグ: {特定した設定タグ名}」に読み替える。

### GA4イベントタグ① `GA4 Event - Scroll Depth`

| 項目 | 値 |
|------|-----|
| 測定 ID | `G-XXXXXXXXXX` |
| イベント名 | `scroll_depth` |
| イベントパラメータ | `scroll_pct` = `{{DLV - sd_scroll_pct}}` / `page_path` = `{{DLV - sd_page_path}}` |
| トリガー | `CE - Scroll Depth` |

### GA4イベントタグ② `GA4 Event - CTA Click`

| 項目 | 値 |
|------|-----|
| 測定 ID | `G-XXXXXXXXXX` |
| イベント名 | `cta_click` |
| イベントパラメータ | `cta_location`={{DLV - cc_cta_location}} / `cta_type`={{DLV - cc_cta_type}} / `cta_purpose`={{DLV - cc_cta_purpose}} / `cta_id`={{DLV - cc_cta_id}} / `cta_text`={{DLV - cc_cta_text}} / `page_path`={{DLV - cc_page_path}} |
| トリガー | `CE - CTA Click` |

### GA4イベントタグ③ `GA4 Event - Form`

| 項目 | 値 |
|------|-----|
| 測定 ID | `G-XXXXXXXXXX` |
| イベント名 | `{{DLV - fe_form_action}}`（= form_start / form_abandon に動的展開） |
| イベントパラメータ | `form_id`={{DLV - fe_form_id}} / `page_path`={{DLV - fe_page_path}} |
| トリガー | `CE - Form Event` |

---

## 6. STEP E: プレビュー → 公開 → BQ検証

### E-1. プレビュー（公開前 必須）

1. GTM 右上「プレビュー」→ `https://www.example.com/` を入力して Connect
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
bq query --use_legacy_sql=false --project_id=__ARK_PROJECT__ '
SELECT event_name, COUNT(*) cnt
FROM `__ARK_PROJECT__.__GA4_DATASET__.events_*`
WHERE _TABLE_SUFFIX >= "20260516"
  AND event_name IN ("scroll_depth","cta_click","form_start","form_abandon")
GROUP BY event_name ORDER BY cnt DESC'
```

### E-4. コンティンジェンシー（E-3 で依然 0件の場合・第4監査人 #2 で全面修正）

> ⚠️ **旧版の「副因＝BQエクスポートのevent制限」は鑑別不十分だった**。`user_engagement`・拡張計測 `scroll` すら BQ に無いのは、エクスポート側より **収集側（GA4 に届いていない）** の可能性が高い。**収集側を先に切り分ける**。

**切り分けは E-1 プレビュー段階（DebugView）で前倒し実施する**（BQ反映の48hを待たない＝クリティカルパス短縮・第4監査人 #3 対応）:

| DebugView での観察 | 判定 | 対処 |
|---|---|---|
| 3カスタムイベント + `user_engagement` + 拡張計測 `scroll` が**出る** | GTM修正成功・収集正常 | 公開 → BQ反映待ち（24-48h）。BQに出なければ初めてエクスポート側を疑う（下記★） |
| カスタムイベントは出るが `user_engagement`/拡張計測が**出ない** | 収集側の別問題（gtag修正とは別） | GA4: 管理→データストリーム→**拡張計測の実ON/OFF** / **データフィルタ（内部トラフィック・開発者トラフィック除外）** / **同意設定（Consent Mode）** / **Google シグナル** を確認 |
| 3カスタムイベントが**出ない** | GTM側がまだ不正（§1.5 の初期化タグ未参照が濃厚）| §1.5 STEP 0 に戻り初期化タグの参照を修正 |

★ BQ にだけ出ない場合のエクスポート側確認（**閲覧のみ・保存ボタンを押さない**＝GCP設定変更禁止ルール厳守）:
- GA4 管理 → サービス間のリンク設定 → BigQuery のリンク → 該当リンク → 「除外するイベント」設定の有無を**確認のみ**

> この設計により「①GTM側」「②収集側(consent/フィルタ/拡張計測)」「③エクスポート側」を DebugView 段階で切り分け、BQ反映48hをクリティカルパスから外す。

---

## 7. 完了チェックリスト

- [ ] **§1.5 STEP 0: GA4初期化タグ（設定/Googleタグ）の所在を特定 or 新設**（最優先・第4監査人 #1）
- [ ] タグ①②③ の HTML を §2 のコードに全文置換・保存
- [ ] DLV 11個 作成（§3）
- [ ] カスタムイベント トリガー 3個 作成（§4）
- [ ] GA4 イベントタグ 3個 作成（測定IDは §1.5 判定に従い設定タグ参照 or 直接入力）（§5）
- [ ] プレビューで3イベント + `user_engagement` + 拡張計測 `scroll` の DebugView 着弾を確認（§6 E-1 / E-4）
- [ ] 公開（バージョン名明記）（§6 E-2）
- [ ] 5/17 夜 DebugView で成否即判定（BQ反映を待たない・§6 E-4）
- [ ] 5/18 早朝 BQ 反映1次確認（§6 E-3）
- [ ] 不調なら §6 E-4 の3分岐切り分け → 必要なら **5/19 予備実作業日**で再修正
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
