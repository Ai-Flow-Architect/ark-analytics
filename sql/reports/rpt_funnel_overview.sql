-- reports.rpt_funnel_overview
-- 総合ビューのファネル = クライアント要望 (12)
--   CTAクリック → フォーム到達 → 完了 の「数」と「率」
-- conversion_funnel_daily（日次）を、クライアントの3段階の言葉に整形した
-- Looker ファネルチャート／スコアカード接続用 VIEW。
-- 更新: 毎日 AM 5:30（marts.conversion_funnel_daily 完了後の rpt 層で再作成）
--
-- ┌──────────────────────────────────────────────────────────────┐
-- │ 期間集計（Looker）: 率は必ず raw 段階数の ratio of sums で算出 │
-- │   例) フォーム到達率 = SUM(stage2_form_reach)/SUM(stage1_cta)  │
-- │   _pct 列（*_rate_pct）は単日表示専用（AVG禁止）。            │
-- │ ※ scroll/cta/form のGTM反映は 2026-05-23〜24 進行中。反映前は │
-- │   stage1/stage2 が 0 になり得る（SQLは正・データ到着で埋まる）。│
-- └──────────────────────────────────────────────────────────────┘

CREATE OR REPLACE VIEW `__ARK_PROJECT__.reports.rpt_funnel_overview` AS
SELECT
  report_date,

  -- ── 3段階の「数」（実数・セッションベース） ─────────────────
  step2a_cta_click                                      AS stage1_cta_click,     -- CTAクリック
  step4_form_start                                      AS stage2_form_reach,    -- フォーム到達（入力開始）
  step5_submission                                      AS stage3_completion,    -- 完了（送信完了）

  -- 参考: CTAクリック延べ回数 / お問い合わせページ到達（フォーム到達の代替指標）
  step2a_cta_click_total                                AS stage1_cta_click_total,
  step3_contact_page                                    AS contact_page_reach,

  -- ── 3段階の「率」（素値 0.xx・単日/後方互換） ───────────────
  ROUND(SAFE_DIVIDE(step4_form_start, step2a_cta_click), 4)  AS cta_to_form_rate,
  ROUND(SAFE_DIVIDE(step5_submission, step4_form_start), 4)  AS form_to_complete_rate,
  ROUND(SAFE_DIVIDE(step5_submission, step2a_cta_click), 4)  AS cta_to_complete_rate,

  -- ── 3段階の「率」（0〜100・Looker scorecard 単日表示用） ─────
  ROUND(SAFE_DIVIDE(step4_form_start, step2a_cta_click) * 100, 2)  AS cta_to_form_rate_pct,
  ROUND(SAFE_DIVIDE(step5_submission, step4_form_start) * 100, 2)  AS form_to_complete_rate_pct,
  ROUND(SAFE_DIVIDE(step5_submission, step2a_cta_click) * 100, 2)  AS cta_to_complete_rate_pct

FROM `__ARK_PROJECT__.marts.conversion_funnel_daily`
;
