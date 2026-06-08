-- marts.daily_kpi_summary
-- 日次KPIサマリー（Looker Studioのメイン接続先）
-- 更新: 毎日 AM 5:00

CREATE OR REPLACE TABLE `__ARK_PROJECT__.marts.daily_kpi_summary`
PARTITION BY report_date
AS
WITH daily_sessions AS (
  SELECT
    session_date                                                       AS report_date,
    COUNT(DISTINCT session_id)                                         AS sessions,
    COUNT(DISTINCT user_pseudo_id)                                     AS users,
    COUNT(DISTINCT IF(
      -- 新規ユーザー判定: その日に「初回セッション」を持つ DISTINCT ユーザー数。
      -- 旧実装は session_id を数えていたため、新規ユーザーが同日に複数セッションを
      -- 持つと new_users > users となり new_user_rate が 100% を超えるバグがあった。
      -- → user_pseudo_id を数えることで new_users ≤ users を保証（2026-05-21 修正）。
      NOT EXISTS (
        SELECT 1 FROM `__ARK_PROJECT__.staging.stg_sessions` s2
        WHERE s2.user_pseudo_id = s.user_pseudo_id
          AND s2.session_date < s.session_date
      ), user_pseudo_id, NULL
    ))                                                                 AS new_users,
    COUNTIF(is_engaged)                                                AS engaged_sessions,
    SUM(page_view_count)                                               AS pageviews,
    ROUND(AVG(session_duration_sec), 1)                                AS avg_session_duration,
    ROUND(AVG(page_view_count), 2)                                     AS pages_per_session,
    COUNTIF(has_conversion)                                            AS converting_sessions

  FROM `__ARK_PROJECT__.staging.stg_sessions` s
  GROUP BY session_date
),

daily_events AS (
  SELECT
    event_date                                                         AS report_date,
    -- 完了はセッション単位（同一セッションの重複completeを1とカウント）
    COUNT(DISTINCT IF(event_name = 'contact_finish', session_id, NULL)) AS contact_form_submissions,
    COUNTIF(event_name = 'file_download')                             AS document_downloads,
    COUNTIF(event_name = 'book_appointment')                          AS appointment_bookings,
    -- フォーム閲覧（=お問合せ到達）。2026-06-08 修正:
    --   旧実装は /contact の「延べページビュー数」(COUNTIF) を分母にしており、
    --   分子(完了=セッション単位)と粒度が不一致 → contact_form_cr が実態の約半分(19%)に
    --   見える不具合があった（同一セッションが /contact を平均2.3回閲覧して分母が膨張）。
    --   ファネルの step3_contact_reach_incl と同一の「お問合せ到達セッション数（包含）」に統一し、
    --   主要分析・ファネル・総合ビューで『到達→完了率』が単一値に一致するようにする。
    COUNT(DISTINCT IF(
      (event_name = 'page_view' AND (page_path LIKE '%/contact%' OR page_path LIKE '%/inquiry%'))
      OR event_name = 'form_start'
      OR event_name = 'contact_finish',
      session_id, NULL
    ))                                                                 AS contact_form_views,
    -- スクロール90%到達。2026-06-08 修正: custom scroll_depth は深度値未送出のため
    -- GA4標準 scroll(percent_scrolled=90)を含めて集計（stg側でscroll_pctにCOALESCE済）。
    COUNTIF(event_name IN ('scroll', 'scroll_depth')
      AND scroll_pct >= 90)                                      AS scroll_90pct_count,
    COUNT(DISTINCT IF(is_conversion, session_id, NULL))               AS total_conversions

  FROM `__ARK_PROJECT__.staging.stg_ga4_events`
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
