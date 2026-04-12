-- staging.stg_ga4_events
-- GA4 rawイベントを正規化・クレンジングするビュー
-- 更新: 毎日 AM 4:00 (Scheduled Query)
-- プロジェクト: ark-hd-analytics / データセット: analytics_386840839

CREATE OR REPLACE VIEW `ark-hd-analytics.staging.stg_ga4_events` AS
SELECT
  PARSE_DATE('%Y%m%d', event_date)                                                   AS event_date,
  TIMESTAMP_MICROS(event_timestamp)                                                  AS event_timestamp,
  event_name,
  user_pseudo_id,
  CONCAT(
    user_pseudo_id, '_',
    CAST(
      (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id')
      AS STRING
    )
  )                                                                                  AS session_id,

  -- ページ情報
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_location') AS page_location,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_title')    AS page_title,
  REGEXP_EXTRACT(
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_location'),
    r'https?://[^/]+(/.*)?\??.*'
  )                                                                                  AS page_path,

  -- 流入元
  traffic_source.medium                                                              AS traffic_source_medium,
  traffic_source.source                                                              AS traffic_source_source,
  traffic_source.name                                                                AS traffic_source_campaign,

  -- デバイス・地域
  device.category                                                                    AS device_category,
  device.operating_system                                                            AS device_os,
  geo.country                                                                        AS country,
  geo.region                                                                         AS region,

  -- エンゲージメント
  (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'engaged_session_event')
                                                                                     AS engaged_session_event,
  (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'session_engaged')  AS session_engaged,
  (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'engagement_time_msec')
                                                                                     AS engagement_time_msec,

  -- コンバージョン判定（実際のイベント名に合わせて定義）
  event_name IN (
    'contact_finish',    -- お問い合わせ送信完了（実装済みカスタムイベント）
    'file_download',     -- 資料DL（未実装・将来追加予定）
    'book_appointment'   -- 相談申込（未実装・将来追加予定）
  )                                                                                  AS is_conversion,

  -- スクロール・CTA
  (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'percent_scrolled') AS percent_scrolled

FROM
  `ark-hd-analytics.analytics_386840839.events_*`
WHERE
  _TABLE_SUFFIX BETWEEN
    FORMAT_DATE('%Y%m%d', DATE_SUB(CURRENT_DATE(), INTERVAL 13 MONTH))
    AND FORMAT_DATE('%Y%m%d', CURRENT_DATE())
;
