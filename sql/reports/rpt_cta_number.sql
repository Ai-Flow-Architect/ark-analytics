-- reports.rpt_cta_number
-- Looker Studio「CTA番号別内訳」ページ接続用 VIEW。
-- marts.cta_number_breakdown_daily をそのまま Looker 向けに公開する薄いラッパー。
--   （Looker はシングルソース接続が前提のため、mart直参照でなく reports VIEW 経由に統一する
--     ＝定義変更を daily_refresh.sh で毎日確実に反映するルール準拠）
--
-- 単位ルール（rpt_looker_main と同一）:
--   ・cta_to_cv_rate     … 素値 0.xx（Lookerで「数値書式: %」を当てると自動 ×100 表示）
--   ・cta_to_cv_rate_pct … 0〜100 の小数2桁（Lookerの「%書式」は使わない＝二重100化回避）
--   ・期間集計の真値到達率は Looker計算フィールドで
--       SUM(inquiry_cv_click_sessions)/SUM(click_sessions)*100（ratio of sums・AVG禁止）
-- 更新: 毎日 AM 5:30（marts.cta_number_breakdown_daily 完了後）
CREATE OR REPLACE VIEW `__ARK_PROJECT__.reports.rpt_cta_number` AS
SELECT
  report_date,
  cta_id,
  cta_label,
  page_group,
  page_path_label,
  position_label,
  purpose_label,
  sample_cta_text,
  cta_clicks,
  click_sessions,
  click_users,
  inquiry_cv_click_sessions,
  cta_to_cv_rate,
  cta_to_cv_rate_pct
FROM `__ARK_PROJECT__.marts.cta_number_breakdown_daily`
;
