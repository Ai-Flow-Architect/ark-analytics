-- reports.looker_executive_view
-- 経営層向けLooker Studio 直接参照用ビュー（クエリ単純化）
-- 更新: 毎日 AM 5:30（daily_kpi_summary + channel_kpi_monthly完了後）

CREATE OR REPLACE VIEW `ark-analytics-2026.reports.looker_executive_view` AS

WITH monthly_agg AS (
  SELECT
    DATE_TRUNC(report_date, MONTH)                                       AS report_month,
    SUM(sessions)                                                        AS monthly_sessions,
    SUM(new_users)                                                       AS monthly_new_users,
    ROUND(AVG(engagement_rate), 4)                                       AS monthly_engagement_rate,
    SUM(contact_form_submissions)                                        AS monthly_inquiries,
    SUM(document_downloads)                                              AS monthly_downloads,
    SUM(appointment_bookings)                                            AS monthly_appointments,
    SUM(total_conversions)                                               AS monthly_conversions,
    ROUND(SAFE_DIVIDE(
      SUM(contact_form_submissions), SUM(NULLIF(contact_form_views, 0))
    ), 4)                                                                AS monthly_contact_cr
  FROM `ark-analytics-2026.marts.daily_kpi_summary`
  GROUP BY report_month
)

SELECT
  -- 日次データ（Looker Studioの日付フィルター用）
  d.report_date,
  DATE_TRUNC(d.report_date, MONTH)                                       AS report_month,
  d.sessions,
  d.new_users,
  d.engaged_sessions,
  d.pageviews,
  d.avg_session_duration,
  ROUND(d.engagement_rate * 100, 2)                                      AS engagement_rate_pct,
  ROUND(d.bounce_rate * 100, 2)                                          AS bounce_rate_pct,
  ROUND(d.new_user_rate * 100, 2)                                        AS new_user_rate_pct,
  d.contact_form_submissions,
  d.document_downloads,
  d.appointment_bookings,
  d.total_conversions,
  ROUND(d.contact_form_cr * 100, 2)                                      AS contact_cr_pct,
  ROUND(d.overall_cvr * 100, 2)                                          AS overall_cvr_pct,

  -- 月次集計（KGI進捗確認用）
  m.monthly_sessions,
  m.monthly_inquiries,
  m.monthly_downloads,
  m.monthly_conversions,

  -- 目標値（経営層の閾値表示用）
  5000                                                                   AS target_monthly_sessions,
  9                                                                      AS target_monthly_inquiries,
  3                                                                      AS target_monthly_contracts,

  -- 目標達成率
  ROUND(SAFE_DIVIDE(m.monthly_sessions, 5000) * 100, 1)                 AS sessions_target_rate_pct,
  ROUND(SAFE_DIVIDE(m.monthly_inquiries, 9) * 100, 1)                   AS inquiry_target_rate_pct

FROM `ark-analytics-2026.marts.daily_kpi_summary` d
LEFT JOIN monthly_agg m
  ON DATE_TRUNC(d.report_date, MONTH) = m.report_month
ORDER BY d.report_date DESC
;
