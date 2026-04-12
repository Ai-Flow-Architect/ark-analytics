-- marts.daily_kpi_summary
-- 日次KPIサマリー（Looker Studioのメイン接続先）
-- 更新: 毎日 AM 5:00

CREATE OR REPLACE TABLE `ark-hd-analytics.marts.daily_kpi_summary`
PARTITION BY report_date
AS
WITH daily_sessions AS (
  SELECT
    session_date                                                       AS report_date,
    COUNT(DISTINCT session_id)                                         AS sessions,
    COUNT(DISTINCT user_pseudo_id)                                     AS users,
    COUNT(DISTINCT IF(
      -- 新規ユーザー判定（初回セッション = セッション日=最初のイベント日）
      NOT EXISTS (
        SELECT 1 FROM `ark-hd-analytics.staging.stg_sessions` s2
        WHERE s2.user_pseudo_id = s.user_pseudo_id
          AND s2.session_date < s.session_date
      ), session_id, NULL
    ))                                                                 AS new_users,
    COUNTIF(is_engaged)                                                AS engaged_sessions,
    SUM(page_view_count)                                               AS pageviews,
    ROUND(AVG(session_duration_sec), 1)                                AS avg_session_duration,
    ROUND(AVG(page_view_count), 2)                                     AS pages_per_session,
    COUNTIF(has_conversion)                                            AS converting_sessions

  FROM `ark-hd-analytics.staging.stg_sessions` s
  GROUP BY session_date
),

daily_events AS (
  SELECT
    event_date                                                         AS report_date,
    COUNTIF(event_name = 'contact_finish')                             AS contact_form_submissions,
    COUNTIF(event_name = 'file_download')                             AS document_downloads,
    COUNTIF(event_name = 'book_appointment')                          AS appointment_bookings,
    COUNTIF(event_name = 'page_view'
      AND page_path LIKE '%/contact%')                                AS contact_form_views,
    COUNTIF(event_name = 'scroll'
      AND percent_scrolled >= 90)                                      AS scroll_90pct_count,
    COUNT(DISTINCT IF(is_conversion, session_id, NULL))               AS total_conversions

  FROM `ark-hd-analytics.staging.stg_ga4_events`
  GROUP BY event_date
)

SELECT
  s.report_date,
  s.sessions,
  s.users,
  s.new_users,
  s.engaged_sessions,
  s.pageviews,
  ROUND(s.avg_session_duration, 1)                                     AS avg_session_duration,
  ROUND(s.pages_per_session, 2)                                        AS pages_per_session,

  -- 算出指標
  ROUND(SAFE_DIVIDE(s.engaged_sessions, s.sessions), 4)               AS engagement_rate,
  ROUND(SAFE_DIVIDE(s.new_users, s.users), 4)                         AS new_user_rate,
  ROUND(1 - SAFE_DIVIDE(s.engaged_sessions, s.sessions), 4)           AS bounce_rate,

  -- コンバージョン指標
  e.contact_form_views,
  e.contact_form_submissions,
  e.document_downloads,
  e.appointment_bookings,
  e.scroll_90pct_count,
  (e.contact_form_submissions + e.document_downloads + e.appointment_bookings)
                                                                       AS total_conversions,
  ROUND(SAFE_DIVIDE(
    e.contact_form_submissions, NULLIF(e.contact_form_views, 0)
  ), 4)                                                                AS contact_form_cr,
  ROUND(SAFE_DIVIDE(
    e.contact_form_submissions + e.document_downloads, s.sessions
  ), 4)                                                                AS overall_cvr

FROM daily_sessions s
LEFT JOIN daily_events e ON s.report_date = e.report_date
;
