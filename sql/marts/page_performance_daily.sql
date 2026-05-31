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
  ROUND(AVG(
    IF(event_name = 'page_view', engagement_time_msec / 1000, NULL)
  ), 1)                                                                 AS avg_time_on_page_sec,

  -- ── スクロール（実数 + 率） ────────────────────────────────
  COUNTIF(event_name = 'scroll_depth' AND scroll_pct >= 90)            AS scroll_90pct_count,
  ROUND(SAFE_DIVIDE(
    COUNTIF(event_name = 'scroll_depth' AND scroll_pct >= 90),
    COUNTIF(event_name = 'page_view')
  ), 4)                                                                 AS scroll_90pct_rate,
  ROUND(SAFE_DIVIDE(
    COUNTIF(event_name = 'scroll_depth' AND scroll_pct >= 90),
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
