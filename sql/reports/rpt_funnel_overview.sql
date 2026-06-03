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

-- ★主ファネル正本（2026-06-03 改定）:
--   セッション → お問合せ到達(incl) → フォーム入力開始(incl) → 完了
--   包含定義により 到達 ⊇ 入力開始 ⊇ 完了 が保証され、全率が必ず 0〜100% に収まる。
--   旧「CTAクリック → フォーム → 完了」は CTA が導線の一部しか捕捉せず（form_start の
--   多くが CTA 非経由）率が構造的に100%超になっていたため、CTA は「主ファネルの段」から外し
--   独立のエンゲージメント指標（cta_click / cta_click_rate）に格下げした。
--   旧 stage1_cta_click / cta_to_form_rate_pct 等は後方互換のため温存（Looker旧接続/テスト用・非推奨）。
CREATE OR REPLACE VIEW `__ARK_PROJECT__.reports.rpt_funnel_overview` AS
SELECT
  report_date,
  step1_sessions                                        AS sessions,

  -- ══ 主ファネル（単調・推奨・Looker総合ビューはこちらを使用） ══════════
  -- 数（実数・セッションベース）
  step3_contact_reach_incl                              AS contact_reach,        -- ① お問合せ到達
  step4_form_start_incl                                 AS form_reach,           -- ② フォーム入力開始
  step5_submission                                      AS completion,           -- ③ 完了（送信完了）

  -- 率（素値 0.xx・単日/後方互換。期間集計はLookerで SUM/SUM = ratio of sums）
  ROUND(SAFE_DIVIDE(step4_form_start_incl, step3_contact_reach_incl), 4)  AS contact_to_form_rate,
  ROUND(SAFE_DIVIDE(step5_submission, step4_form_start_incl), 4)          AS form_to_complete_rate_main,
  ROUND(SAFE_DIVIDE(step5_submission, step3_contact_reach_incl), 4)       AS contact_to_complete_rate,

  -- 率（0〜100・Looker scorecard 単日表示用・必ず≤100%）
  ROUND(SAFE_DIVIDE(step4_form_start_incl, step3_contact_reach_incl) * 100, 2)  AS contact_to_form_rate_pct,
  ROUND(SAFE_DIVIDE(step5_submission, step4_form_start_incl) * 100, 2)          AS form_to_complete_rate_main_pct,
  ROUND(SAFE_DIVIDE(step5_submission, step3_contact_reach_incl) * 100, 2)       AS contact_to_complete_rate_pct,

  -- ══ CTA = 独立エンゲージメント指標（主ファネルの段ではない） ══════════
  step2a_cta_click                                      AS cta_click,            -- CTAクリックしたセッション数
  step2a_cta_click_total                                AS cta_click_total,      -- CTAクリック延べ回数
  ROUND(SAFE_DIVIDE(step2a_cta_click, step1_sessions), 4)        AS cta_click_rate,       -- セッションに対するCTAクリック率
  ROUND(SAFE_DIVIDE(step2a_cta_click, step1_sessions) * 100, 2)  AS cta_click_rate_pct,

  -- ══ 後方互換（非推奨・旧Looker接続/テスト維持用。CTAを段に置くため100%超あり） ══
  step2a_cta_click                                      AS stage1_cta_click,
  step4_form_start                                      AS stage2_form_reach,
  step5_submission                                      AS stage3_completion,
  step2a_cta_click_total                                AS stage1_cta_click_total,
  step3_contact_page                                    AS contact_page_reach,
  ROUND(SAFE_DIVIDE(step4_form_start, step2a_cta_click), 4)        AS cta_to_form_rate,
  ROUND(SAFE_DIVIDE(step5_submission, step4_form_start), 4)        AS form_to_complete_rate,
  ROUND(SAFE_DIVIDE(step5_submission, step2a_cta_click), 4)        AS cta_to_complete_rate,
  ROUND(SAFE_DIVIDE(step4_form_start, step2a_cta_click) * 100, 2)  AS cta_to_form_rate_pct,
  ROUND(SAFE_DIVIDE(step5_submission, step4_form_start) * 100, 2)  AS form_to_complete_rate_pct,
  ROUND(SAFE_DIVIDE(step5_submission, step2a_cta_click) * 100, 2)  AS cta_to_complete_rate_pct

FROM `__ARK_PROJECT__.marts.conversion_funnel_daily`
;
