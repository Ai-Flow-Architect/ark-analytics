-- staging.stg_sessions
-- セッション単位に集約（1行=1セッション）
-- 更新: 毎日 AM 4:30 (stg_ga4_events完了後)

CREATE OR REPLACE TABLE `ark-hd-analytics.staging.stg_sessions`
PARTITION BY session_date
CLUSTER BY channel_grouping, device_category
AS
WITH session_base AS (
  SELECT
    session_id,
    user_pseudo_id,
    MIN(event_date)                                            AS session_date,
    MIN(event_timestamp)                                       AS session_start_ts,
    MAX(event_timestamp)                                       AS session_end_ts,
    ANY_VALUE(traffic_source_source)                           AS source,
    ANY_VALUE(traffic_source_medium)                           AS medium,
    ANY_VALUE(traffic_source_campaign)                         AS campaign,
    ANY_VALUE(device_category)                                 AS device_category,
    ANY_VALUE(country)                                         AS country,
    MAX(session_engaged)                                       AS is_engaged,

    -- ランディングページ（最初のpage_view）
    ARRAY_AGG(
      page_location ORDER BY event_timestamp ASC LIMIT 1
    )[SAFE_OFFSET(0)]                                          AS landing_page,

    -- 離脱ページ（最後のpage_view）
    ARRAY_AGG(
      page_location ORDER BY event_timestamp DESC LIMIT 1
    )[SAFE_OFFSET(0)]                                          AS exit_page,

    -- PV数
    COUNTIF(event_name = 'page_view')                         AS page_view_count,

    -- エンゲージメント時間（ms）
    SUM(engagement_time_msec)                                  AS total_engagement_msec,

    -- コンバージョン
    MAX(CAST(is_conversion AS INT64))                          AS has_conversion,
    ARRAY_AGG(
      IF(is_conversion, event_name, NULL) IGNORE NULLS
      ORDER BY event_timestamp ASC LIMIT 1
    )[SAFE_OFFSET(0)]                                          AS first_conversion_event

  FROM `ark-hd-analytics.staging.stg_ga4_events`
  WHERE session_id IS NOT NULL
  GROUP BY session_id, user_pseudo_id
)

SELECT
  s.session_date,
  s.session_id,
  s.user_pseudo_id,
  s.source,
  s.medium,
  s.campaign,
  -- チャネルグルーピング（GA4標準に近い定義）
  CASE
    WHEN s.medium = 'organic'                          THEN 'Organic Search'
    WHEN s.medium IN ('cpc', 'ppc', 'paid')            THEN 'Paid Search'
    WHEN s.medium = 'referral'                         THEN 'Referral'
    WHEN s.medium IN ('social', 'social-network')      THEN 'Organic Social'
    WHEN s.medium = 'email'                            THEN 'Email'
    WHEN s.medium = '(none)' AND s.source = '(direct)' THEN 'Direct'
    ELSE 'Other'
  END                                                  AS channel_grouping,
  s.device_category,
  s.country,
  s.landing_page,
  s.exit_page,
  s.page_view_count,
  ROUND(s.total_engagement_msec / 1000, 1)             AS session_duration_sec,
  CAST(s.is_engaged AS BOOL)                           AS is_engaged,
  CAST(s.has_conversion AS BOOL)                       AS has_conversion,
  s.first_conversion_event

FROM session_base s
;
