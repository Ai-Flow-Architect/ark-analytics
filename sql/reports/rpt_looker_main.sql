-- reports.rpt_looker_main
-- Looker Studio メインダッシュボード接続用ビュー
-- 日次KPI + ファネル を1テーブルに統合（Looker Studioはシングルソース推奨）
-- 更新: 毎日 AM 5:30（daily_kpi_summary / conversion_funnel_daily 完了後）
--
-- ┌─────────────────────────────────────────────────────────────┐
-- │ 単位ルール（Looker Studio 計算フィールド作成時に必須遵守）   │
-- ├─────────────────────────────────────────────────────────────┤
-- │ ・素値列（engagement_rate / overall_cvr / *_rate 等）        │
-- │     型: 0.0xxx の小数（例: 0.0909 = 9.09%）                  │
-- │     用途: 集計せずSQL層のままで参照する場合のみ              │
-- │     ※ Looker側で「数値書式: %」を当てると自動 ×100 表示      │
-- │                                                             │
-- │ ・_pct 列（engagement_rate_pct / overall_cvr_pct 等）        │
-- │     型: 0〜100 の小数2桁（例: 9.09）                         │
-- │     用途: Looker scorecard / 表で「9.09%」と表示する場合     │
-- │     ※ Lookerの「数値書式: %」は使わないこと（二重100化）    │
-- │                                                             │
-- │ ・期間集計の真値CVR/エンゲージメント率（Simpson's paradox回避）│
-- │     Looker計算フィールドで                                    │
-- │     `SUM(contact_form_submissions)/SUM(sessions)*100`        │
-- │     のように「ratio of sums」で定義する（AVG禁止）            │
-- └─────────────────────────────────────────────────────────────┘

CREATE OR REPLACE VIEW `__ARK_PROJECT__.reports.rpt_looker_main` AS
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

  -- 素値（0.xx）/ 後方互換のため残置
  k.engagement_rate,
  k.new_user_rate,
  k.bounce_rate,

  -- パーセント表記（0〜100）/ Looker scorecard 推奨
  ROUND(k.engagement_rate * 100, 2)          AS engagement_rate_pct,
  ROUND(k.new_user_rate    * 100, 2)         AS new_user_rate_pct,
  ROUND(k.bounce_rate      * 100, 2)         AS bounce_rate_pct,

  -- ── コンバージョン ────────────────────────────────────
  k.contact_form_views,
  k.contact_form_submissions,
  k.document_downloads,
  k.appointment_bookings,
  k.total_conversions,

  -- 素値（0.xx）/ 後方互換
  k.contact_form_cr,
  k.overall_cvr,

  -- パーセント表記（0〜100）
  ROUND(k.contact_form_cr * 100, 2)          AS contact_form_cr_pct,
  ROUND(k.overall_cvr     * 100, 2)          AS overall_cvr_pct,

  -- 厳密 CVR（送信のみ / 資料DLを含まない・クライアントの直観に合致）
  ROUND(SAFE_DIVIDE(
    k.contact_form_submissions, k.sessions
  ) * 100, 2)                                AS inquiry_only_cvr_pct,

  -- ── ファネル ──────────────────────────────────────────
  f.step1_sessions          AS funnel_step1_sessions,
  -- 中間行動: 記事内CTAクリック（GTMタグ②設置後から計測）
  f.step2a_cta_click        AS funnel_cta_click_sessions,
  f.step2a_cta_click_total  AS funnel_cta_click_total,

  -- 素値（0.xx）
  f.step1_to_cta_rate       AS funnel_cta_click_rate,
  f.cta_to_contact_rate     AS funnel_cta_to_contact_rate,
  -- サービスページ経由ルート
  f.step2b_service_view     AS funnel_step2_service_view,
  f.step3_contact_page      AS funnel_step3_contact_page,
  f.step4_form_start        AS funnel_step4_form_start,
  f.step5_submission        AS funnel_step5_submission,
  f.step1_to_2b_rate        AS funnel_rate_1to2,
  f.step2b_to_3_rate        AS funnel_rate_2to3,
  f.step3_to_4_rate         AS funnel_rate_3to4,
  f.step4_to_5_rate         AS funnel_rate_4to5,
  f.overall_inquiry_cvr     AS funnel_overall_cvr,

  -- パーセント表記（0〜100）/ Looker ファネル可視化推奨
  ROUND(f.step1_to_cta_rate    * 100, 2)     AS funnel_cta_click_rate_pct,
  ROUND(f.cta_to_contact_rate  * 100, 2)     AS funnel_cta_to_contact_rate_pct,
  ROUND(f.step1_to_2b_rate     * 100, 2)     AS funnel_rate_1to2_pct,
  ROUND(f.step2b_to_3_rate     * 100, 2)     AS funnel_rate_2to3_pct,
  ROUND(f.step3_to_4_rate      * 100, 2)     AS funnel_rate_3to4_pct,
  ROUND(f.step4_to_5_rate      * 100, 2)     AS funnel_rate_4to5_pct,
  ROUND(f.overall_inquiry_cvr  * 100, 2)     AS funnel_overall_cvr_pct

FROM `__ARK_PROJECT__.marts.daily_kpi_summary` k
LEFT JOIN `__ARK_PROJECT__.marts.conversion_funnel_daily` f
  ON k.report_date = f.report_date
;
