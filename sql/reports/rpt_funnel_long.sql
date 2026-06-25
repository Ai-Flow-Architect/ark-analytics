-- reports.rpt_funnel_long
-- 主ファネル（5段・長尺/縦持ち）= Looker「ファネル分析」ページ接続用 VIEW。
-- marts.conversion_funnel_daily を (step_order, step_name, sessions) に縦展開する。
--
-- ★2026-06-17 修正（検収）:
--   STEP4 を独立カウント step4_form_start（form_start イベントのみ）から
--   包含定義 step4_form_start_incl（form_start ∪ contact_finish）へ差し替え。
--   form_start タグの取りこぼしにより「送信完了(104) > フォーム入力開始(79)」という
--   非単調逆転が発生し、総合ビュー(rpt_funnel_overview=138)とも食い違っていたため。
--   step4_form_start_incl は定義上 必ず step5_submission を内包する＝全期間で単調を保証。
--
-- ★2026-06-25 修正（検収 R8-2）:
--   STEP3 を独立カウント step3_contact_page（/contact・/inquiry の page_view のみ）から
--   包含定義 step3_contact_reach_incl（PV ∪ form_start ∪ contact_finish）へ差し替え＋
--   ラベルを「STEP3 問合せページ」→「STEP3 お問い合わせ到達」へ統一。
--   理由: 総合ビュー(rpt_funnel_overview.contact_reach=step3_contact_reach_incl=191)と
--   ファネル分析STEP3(step3_contact_page=183)が「同名指標で数値不一致」とクライアント指摘。
--   差8件＝/contact PV取りこぼしだがフォーム操作済のセッション。総合ビューと同一の包含定義へ
--   揃えることで両ビューを完全一致させ、かつ 到達(STEP3)⊇入力開始(STEP4)⊇完了(STEP5) の
--   単調性を構造保証する（R5-⑧でSTEP4を包含化したのと同じ思想の延長）。
--   STEP1/2/5 は原定義のまま不変。
-- ※このVIEWは従来 BigQuery 上で直接作成されリポジトリ未追跡だった。本ファイルで正本化し、
--   2026-06-25 から daily_refresh.sh の自動反映対象へ追加（定義移行漏れ＝落とし穴#30の再発防止）。
CREATE OR REPLACE VIEW `__ARK_PROJECT__.reports.rpt_funnel_long` AS
SELECT report_date, 1 AS step_order, 'STEP1 全訪問'         AS step_name,
       CAST(step1_sessions        AS INT64) AS sessions
FROM `__ARK_PROJECT__.marts.conversion_funnel_daily`
UNION ALL
SELECT report_date, 2, 'STEP2 サービス閲覧',
       CAST(step2b_service_view   AS INT64)
FROM `__ARK_PROJECT__.marts.conversion_funnel_daily`
UNION ALL
SELECT report_date, 3, 'STEP3 お問い合わせ到達',
       CAST(step3_contact_reach_incl AS INT64)   -- ← 包含定義へ統一（総合ビューと一致・2026-06-25 R8-2）
FROM `__ARK_PROJECT__.marts.conversion_funnel_daily`
UNION ALL
SELECT report_date, 4, 'STEP4 フォーム入力開始',
       CAST(step4_form_start_incl AS INT64)   -- ← 包含定義（旧 step4_form_start から修正）
FROM `__ARK_PROJECT__.marts.conversion_funnel_daily`
UNION ALL
SELECT report_date, 5, 'STEP5 送信完了',
       CAST(step5_submission      AS INT64)
FROM `__ARK_PROJECT__.marts.conversion_funnel_daily`
;
