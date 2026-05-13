-- marts.page_performance
-- ページ別パフォーマンス（週次更新）
-- 更新: 毎週月曜 AM 5:00

CREATE OR REPLACE TABLE `__ARK_PROJECT__.marts.page_performance`
PARTITION BY week_start
AS
SELECT
  DATE_TRUNC(event_date, WEEK(MONDAY))                                   AS week_start,
  page_path,
  ANY_VALUE(page_title)                                                  AS page_title,

  -- PV指標
  COUNTIF(event_name = 'page_view')                                     AS pageviews,
  COUNT(DISTINCT IF(event_name = 'page_view', session_id, NULL))        AS unique_pageviews,

  -- 滞在・スクロール
  ROUND(AVG(
    IF(event_name = 'page_view', engagement_time_msec / 1000, NULL)
  ), 1)                                                                  AS avg_time_on_page_sec,
  -- GTM タグ①: gtag('event', 'scroll_depth', {scroll_pct: 25|50|75|90})
  COUNTIF(event_name = 'scroll_depth' AND scroll_pct >= 90)       AS scroll_90pct_count,
  ROUND(SAFE_DIVIDE(
    COUNTIF(event_name = 'scroll_depth' AND scroll_pct >= 90),
    COUNTIF(event_name = 'page_view')
  ), 4)                                                                  AS scroll_90pct_rate,

  -- CTAクリック: GTM タグ② gtag('event', 'cta_click', {cta_location, cta_type, ...})
  COUNTIF(event_name = 'cta_click')                                     AS cta_clicks,
  ROUND(SAFE_DIVIDE(
    COUNTIF(event_name = 'cta_click'),
    COUNTIF(event_name = 'page_view')
  ), 4)                                                                  AS cta_click_rate,

  -- このページ起点のコンバージョン数（page_viewが最初に来るセッション）
  COUNT(DISTINCT IF(is_conversion, session_id, NULL))                   AS conversions_from_page,

  -- デバイス別内訳
  COUNTIF(event_name = 'page_view' AND device_category = 'mobile')     AS mobile_pageviews,
  COUNTIF(event_name = 'page_view' AND device_category = 'desktop')    AS desktop_pageviews

FROM `__ARK_PROJECT__.staging.stg_ga4_events`
WHERE page_path IS NOT NULL
  AND page_path != ''
GROUP BY week_start, page_path
;
