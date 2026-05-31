-- marts.cta_breakdown_daily
-- CTA別の流入（クリック計測・日次）= クライアント要望 (8) CTA別の流入
-- GTM タグ②（cta_click）が送る cta_location / cta_type / cta_purpose / cta_id / cta_text を
-- 軸に、クリック数・クリックしたセッション数・ユーザー数・うちCV到達を集計する。
-- ※ scroll/cta/form のGTM反映は 2026-05-23〜24 に進行中（docs/GTM_TAGS.md）。
--   反映完了までは 0 行/0件になり得るが、SQLは正しく、データ到着後そのまま埋まる。
-- 更新: 毎日 AM 5:00（staging.stg_ga4_events 完了後）
--
-- 期間集計の率は ratio of sums（Looker計算フィールドで SUM(cv_sessions)/SUM(click_sessions)）。

CREATE OR REPLACE TABLE `__ARK_PROJECT__.marts.cta_breakdown_daily`
PARTITION BY report_date
CLUSTER BY cta_location, cta_purpose
AS
WITH cta_clicks AS (
  SELECT
    event_date                                       AS report_date,
    session_id,
    user_pseudo_id,
    COALESCE(NULLIF(cta_location, ''), '(未設定)')   AS cta_location,
    COALESCE(NULLIF(cta_type, ''),     '(未設定)')   AS cta_type,
    COALESCE(NULLIF(cta_purpose, ''),  '(未設定)')   AS cta_purpose
  FROM `__ARK_PROJECT__.staging.stg_ga4_events`
  WHERE event_name = 'cta_click'
    AND session_id IS NOT NULL
),

-- このセッションが最終的にCVしたか（contact_finish / file_download / book_appointment）
converting_sessions AS (
  SELECT DISTINCT session_id
  FROM `__ARK_PROJECT__.staging.stg_ga4_events`
  WHERE is_conversion
    AND session_id IS NOT NULL
)

SELECT
  c.report_date,
  c.cta_location,
  c.cta_type,
  c.cta_purpose,

  -- 実数
  COUNT(*)                                                           AS cta_clicks,
  COUNT(DISTINCT c.session_id)                                       AS click_sessions,
  COUNT(DISTINCT c.user_pseudo_id)                                   AS click_users,
  COUNT(DISTINCT IF(cv.session_id IS NOT NULL, c.session_id, NULL))  AS converting_click_sessions,

  -- CTAクリック後のCV到達率（素値 0.xx）
  ROUND(SAFE_DIVIDE(
    COUNT(DISTINCT IF(cv.session_id IS NOT NULL, c.session_id, NULL)),
    COUNT(DISTINCT c.session_id)
  ), 4)                                                              AS cta_to_cv_rate,
  -- CTAクリック後のCV到達率（0〜100・単日表示用）
  ROUND(SAFE_DIVIDE(
    COUNT(DISTINCT IF(cv.session_id IS NOT NULL, c.session_id, NULL)),
    COUNT(DISTINCT c.session_id)
  ) * 100, 2)                                                        AS cta_to_cv_rate_pct

FROM cta_clicks c
LEFT JOIN converting_sessions cv ON c.session_id = cv.session_id
GROUP BY c.report_date, c.cta_location, c.cta_type, c.cta_purpose
;
