-- marts.channel_kpi_monthly
-- 月次×チャネル別パフォーマンス（経営層レポート用）
-- 更新: 毎月1日 AM 6:00

CREATE OR REPLACE TABLE `__ARK_PROJECT__.marts.channel_kpi_monthly`
PARTITION BY report_month
AS
-- お問い合わせ完了（contact_finish）セッション（2026-07-10 R10-C 横断整合対応）。
-- 定義書2026-07-09 チャネル分析「コンバージョン数 = お問い合わせ完了のみ」に合わせ、
-- traffic_breakdown_daily.inquiry_conversions と同一定義の列を本マートにも用意する。
-- 本マートは AIチャット(app.py)・月次メール(data_collector.get_channel_breakdown)・
-- 自然言語QA が参照するため、ここが広義CV（has_conversion = contact_finish/file_download/
-- book_appointment）のままだと、資料DL計測開始後に Looker（inquiry基準）と
-- 「同名指標なのに画面によって数値が違う」乖離を生む（現状は DL/予約 0件のため同値）。
WITH inquiry_sessions AS (
  SELECT DISTINCT session_id AS inq_session_id
  FROM `__ARK_PROJECT__.staging.stg_ga4_events`
  WHERE event_name = 'contact_finish'
    AND session_id IS NOT NULL
)
SELECT
  DATE_TRUNC(s.session_date, MONTH)                              AS report_month,
  s.channel_grouping,
  COUNT(DISTINCT s.session_id)                                   AS sessions,
  COUNT(DISTINCT s.user_pseudo_id)                               AS users,
  COUNTIF(s.is_engaged)                                          AS engaged_sessions,
  ROUND(SAFE_DIVIDE(COUNTIF(s.is_engaged), COUNT(DISTINCT s.session_id)), 4)
                                                                 AS engagement_rate,
  SUM(s.page_view_count)                                         AS pageviews,
  -- 旧列（後方互換で残置）: 広義CV（contact_finish + file_download + book_appointment）
  COUNTIF(s.has_conversion)                                      AS conversions,
  ROUND(SAFE_DIVIDE(COUNTIF(s.has_conversion), COUNT(DISTINCT s.session_id)), 4)
                                                                 AS conversion_rate,
  -- コンバージョン数【定義書2026-07-09 準拠版・お問い合わせ完了のみ】
  COUNTIF(inq.inq_session_id IS NOT NULL)                        AS inquiry_conversions,
  ROUND(SAFE_DIVIDE(COUNTIF(inq.inq_session_id IS NOT NULL), COUNT(DISTINCT s.session_id)), 4)
                                                                 AS inquiry_conversion_rate,
  ROUND(AVG(s.session_duration_sec), 1)                          AS avg_session_duration

FROM `__ARK_PROJECT__.staging.stg_sessions` s
LEFT JOIN inquiry_sessions inq ON s.session_id = inq.inq_session_id
GROUP BY report_month, channel_grouping
;
