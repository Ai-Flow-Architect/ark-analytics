-- marts.channel_kpi_monthly
-- 月次×チャネル別パフォーマンス（経営層レポート用）
-- 更新: 毎月1日 AM 6:00

CREATE OR REPLACE TABLE `ark-hd-analytics.marts.channel_kpi_monthly`
PARTITION BY report_month
AS
SELECT
  DATE_TRUNC(session_date, MONTH)                                AS report_month,
  channel_grouping,
  COUNT(DISTINCT session_id)                                     AS sessions,
  COUNT(DISTINCT user_pseudo_id)                                 AS users,
  COUNTIF(is_engaged)                                            AS engaged_sessions,
  ROUND(SAFE_DIVIDE(COUNTIF(is_engaged), COUNT(DISTINCT session_id)), 4)
                                                                 AS engagement_rate,
  SUM(page_view_count)                                           AS pageviews,
  COUNTIF(has_conversion)                                        AS conversions,
  ROUND(SAFE_DIVIDE(COUNTIF(has_conversion), COUNT(DISTINCT session_id)), 4)
                                                                 AS conversion_rate,
  ROUND(AVG(session_duration_sec), 1)                           AS avg_session_duration

FROM `ark-hd-analytics.staging.stg_sessions`
GROUP BY report_month, channel_grouping
;
