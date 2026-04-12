-- reports.rpt_looker_main
-- Looker Studio メインダッシュボード接続用ビュー
-- 日次KPI + ファネル を1テーブルに統合（Looker Studioはシングルソース推奨）
-- 更新: 毎日 AM 5:30（daily_kpi_summary / conversion_funnel_daily 完了後）

CREATE OR REPLACE VIEW `ark-hd-analytics.reports.rpt_looker_main` AS
SELECT
  k.report_date,

  -- ── セッション・ユーザー ───────────────────────────────
  k.sessions,
  k.users,
  k.new_users,
  k.engaged_sessions,
  k.pageviews,
  k.avg_session_duration,
  k.pages_per_session,
  k.engagement_rate,
  k.new_user_rate,
  k.bounce_rate,

  -- ── コンバージョン ────────────────────────────────────
  k.contact_form_views,
  k.contact_form_submissions,
  k.document_downloads,
  k.appointment_bookings,
  k.total_conversions,
  k.contact_form_cr,
  k.overall_cvr,

  -- ── ファネル ──────────────────────────────────────────
  f.step1_sessions        AS funnel_step1_sessions,
  f.step2_service_view    AS funnel_step2_service_view,
  f.step3_contact_page    AS funnel_step3_contact_page,
  f.step4_form_start      AS funnel_step4_form_start,
  f.step5_submission      AS funnel_step5_submission,
  f.step1_to_2_rate       AS funnel_rate_1to2,
  f.step2_to_3_rate       AS funnel_rate_2to3,
  f.step3_to_4_rate       AS funnel_rate_3to4,
  f.step4_to_5_rate       AS funnel_rate_4to5,
  f.overall_inquiry_cvr   AS funnel_overall_cvr

FROM `ark-hd-analytics.marts.daily_kpi_summary` k
LEFT JOIN `ark-hd-analytics.marts.conversion_funnel_daily` f
  ON k.report_date = f.report_date
;
