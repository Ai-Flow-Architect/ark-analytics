-- marts.conversion_funnel_daily
-- コンバージョンファネル進行状況（日次）
-- Step1: サイト訪問 → Step2: サービスページ閲覧 → Step3: お問合せページ到達
-- → Step4: フォーム入力開始 → Step5: フォーム送信完了 → Step6: 成約
-- 更新: 毎日 AM 5:00

CREATE OR REPLACE TABLE `ark-hd-analytics.marts.conversion_funnel_daily`
PARTITION BY report_date
AS
WITH funnel_steps AS (
  SELECT
    event_date                                                             AS report_date,

    -- Step1: 全セッション（サイト訪問）
    COUNT(DISTINCT session_id)                                             AS step1_sessions,

    -- Step2: サービスページ閲覧（/service/ 配下）
    COUNT(DISTINCT IF(
      event_name = 'page_view' AND page_path LIKE '%/service%',
      session_id, NULL
    ))                                                                     AS step2_service_view,

    -- Step3: お問い合わせページ到達
    COUNT(DISTINCT IF(
      event_name = 'page_view' AND (
        page_path LIKE '%/contact%' OR
        page_path LIKE '%/inquiry%'
      ),
      session_id, NULL
    ))                                                                     AS step3_contact_page,

    -- Step4: フォーム入力開始（form_start イベント）
    COUNT(DISTINCT IF(event_name = 'form_start', session_id, NULL))       AS step4_form_start,

    -- Step5: フォーム送信完了（contact_finish）
    COUNT(DISTINCT IF(event_name = 'contact_finish', session_id, NULL))   AS step5_submission,

    -- Step6: 資料DL（並行CVルート）
    COUNT(DISTINCT IF(event_name = 'file_download', session_id, NULL))    AS step5b_download

  FROM `ark-hd-analytics.staging.stg_ga4_events`
  GROUP BY event_date
)

SELECT
  report_date,
  step1_sessions,
  step2_service_view,
  step3_contact_page,
  step4_form_start,
  step5_submission,
  step5b_download,

  -- ステップ別離脱率
  ROUND(SAFE_DIVIDE(step2_service_view, step1_sessions), 4)              AS step1_to_2_rate,
  ROUND(SAFE_DIVIDE(step3_contact_page, step2_service_view), 4)          AS step2_to_3_rate,
  ROUND(SAFE_DIVIDE(step4_form_start, step3_contact_page), 4)            AS step3_to_4_rate,
  ROUND(SAFE_DIVIDE(step5_submission, step4_form_start), 4)              AS step4_to_5_rate,
  -- 全体CVR（訪問 → 問合せ）
  ROUND(SAFE_DIVIDE(step5_submission, step1_sessions), 4)                AS overall_inquiry_cvr,
  -- 全体CVR（訪問 → 資料DL）
  ROUND(SAFE_DIVIDE(step5b_download, step1_sessions), 4)                 AS overall_download_cvr

FROM funnel_steps
;
