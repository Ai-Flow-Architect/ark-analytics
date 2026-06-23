-- marts.page_performance_daily
-- ページ別パフォーマンス（日次・実数併記）= クライアント要望 (11) ページ別パフォーマンスの実数併記
-- 既存 marts.page_performance は週次grain（week_start）で期間コントロールに同期しないため、
-- 本テーブルは report_date 日次grain で同一の期間コントロール (3) に同期させる。
-- 「率」だけでなく「実数（PV・UU・スクロール到達数・CTAクリック数・CV数）」を併記する。
-- 更新: 毎日 AM 5:00（staging.stg_ga4_events 完了後）

CREATE OR REPLACE TABLE `__ARK_PROJECT__.marts.page_performance_daily`
PARTITION BY report_date
CLUSTER BY page_path
AS
SELECT
  event_date                                                            AS report_date,
  page_path,
  ANY_VALUE(page_title)                                                 AS page_title,

  -- ── 実数（PV指標） ─────────────────────────────────────────
  COUNTIF(event_name = 'page_view')                                    AS pageviews,
  COUNT(DISTINCT IF(event_name = 'page_view', session_id, NULL))       AS unique_pageviews,
  COUNT(DISTINCT IF(event_name = 'page_view', user_pseudo_id, NULL))   AS unique_users,

  -- ── 滞在 ───────────────────────────────────────────────────
  -- 平均エンゲージメント時間（秒）。
  -- 旧実装は page_view の engagement_time_msec を AVG していたが、GA4 では
  -- engagement_time_msec が page_view にはほぼ付与されず（実測: 直近30日 page_view 1,223件中 付与は2件のみ）、
  -- 結果が全 null/0 になっていた（2026-06-23 検収R7で本番実データ検出・305/307行 null）。
  -- 週次 marts.page_performance は 2026-05-31 に修正済みだったが、本日次テーブル新設時に旧バグ式をコピーしていた
  -- （週次→日次の定義移行漏れ＝落とし穴#30）。週次と同一の「ページ上の全イベントの
  --   engagement_time_msec 合算 ÷ ページビュー数」へ統一する（GA4標準の考え方）。
  ROUND(SAFE_DIVIDE(
    SUM(engagement_time_msec),
    COUNTIF(event_name = 'page_view')
  ) / 1000, 1)                                                          AS avg_time_on_page_sec,

  -- ── スクロール（実数 + 率） ────────────────────────────────
  COUNTIF(event_name IN ('scroll', 'scroll_depth') AND scroll_pct >= 90)            AS scroll_90pct_count,
  ROUND(SAFE_DIVIDE(
    COUNTIF(event_name IN ('scroll', 'scroll_depth') AND scroll_pct >= 90),
    COUNTIF(event_name = 'page_view')
  ), 4)                                                                 AS scroll_90pct_rate,
  ROUND(SAFE_DIVIDE(
    COUNTIF(event_name IN ('scroll', 'scroll_depth') AND scroll_pct >= 90),
    COUNTIF(event_name = 'page_view')
  ) * 100, 2)                                                           AS scroll_90pct_rate_pct,

  -- ── CTAクリック（実数 + 率） ───────────────────────────────
  COUNTIF(event_name = 'cta_click')                                    AS cta_clicks,
  ROUND(SAFE_DIVIDE(
    COUNTIF(event_name = 'cta_click'),
    COUNTIF(event_name = 'page_view')
  ), 4)                                                                 AS cta_click_rate,
  ROUND(SAFE_DIVIDE(
    COUNTIF(event_name = 'cta_click'),
    COUNTIF(event_name = 'page_view')
  ) * 100, 2)                                                           AS cta_click_rate_pct,

  -- ── コンバージョン（実数） ─────────────────────────────────
  COUNT(DISTINCT IF(is_conversion, session_id, NULL))                  AS conversions_from_page,

  -- ── デバイス別 実数内訳 ────────────────────────────────────
  COUNTIF(event_name = 'page_view' AND device_category = 'desktop')    AS desktop_pageviews,
  COUNTIF(event_name = 'page_view' AND device_category = 'mobile')     AS mobile_pageviews,
  COUNTIF(event_name = 'page_view' AND device_category = 'tablet')     AS tablet_pageviews

FROM `__ARK_PROJECT__.staging.stg_ga4_events`
WHERE page_path IS NOT NULL
  AND page_path != ''
GROUP BY report_date, page_path
;
