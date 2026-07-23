-- staging.stg_ga4_events
-- GA4 rawイベントを正規化・クレンジングするビュー
-- 更新: 毎日 AM 4:00 (Scheduled Query)
-- プロジェクト: __ARK_PROJECT__ / データセット: analytics___ARK_GA4_PROPID__

CREATE OR REPLACE VIEW `__ARK_PROJECT__.staging.stg_ga4_events` AS
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

  -- セッション通番（GA4標準 ga_session_number: ユーザー通算のセッション番号・初回=1）。
  -- 2026-07-09 定義書対応で追加: 主要分析「新規/リピーター」は
  -- 『訪問（セッション）が初回だったか、2回目以降だったか』のセッション単位定義のため、
  -- GA4ネイティブの通番で厳密判定する（日付粒度の近似だと同日2回目以降の訪問が
  -- 「新規」に混入する: 2026-06実測で35セッション過大）。
  (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_number')
                                                                                     AS ga_session_number,

  -- エンゲージメント
  (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'engaged_session_event')
                                                                                     AS engaged_session_event,
  (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'session_engaged')  AS session_engaged,
  (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'engagement_time_msec')
                                                                                     AS engagement_time_msec,

  -- コンバージョン判定（実際のイベント名に合わせて定義）
  event_name IN (
    'contact_finish',    -- お問い合わせ送信完了（実装済みカスタムイベント）
    'file_download',     -- 資料DL（旧定義・全期間0件。実際の資料DLは contact_finish + /document/ = conversion_type で分類）
    'book_appointment'   -- 相談申込（未実装・将来追加予定）
  )                                                                                  AS is_conversion,

  -- コンバージョン種別（2026-07-23 客様③「資料DLが計測されない」対応で追加）:
  --   資料DLフォーム（/document/#mailform）の送信完了は file_download ではなく、
  --   お問い合わせと同じ contact_finish イベントで発火する（本番実データで確認:
  --   file_download は全期間0件・contact_finish は page_location='.../document/?mode=finish'
  --   の行が存在。page_location の分布は /contact/ と /document/ の2種のみで NULL なし）。
  --   イベント名だけでは両者を区別できないため、page_location で種別を一元分類する。
  --   marts 側の「お問い合わせ」「資料DL」集計は必ず本列を参照すること
  --   （event_name = 'contact_finish' / 'file_download' の直接判定は二重定義＝定義ズレの温床）。
  --   ※ is_conversion（広義CV=何らかのCVか）は従来定義のまま不変（資料DLもCVに含むため）。
  CASE
    WHEN event_name = 'contact_finish'
      AND (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_location')
          LIKE '%/document/%'                THEN 'document_dl'  -- 資料DL送信完了（/document/?mode=finish）
    WHEN event_name = 'contact_finish'       THEN 'inquiry'      -- お問い合わせ送信完了（/contact/?mode=finish）
    WHEN event_name = 'file_download'        THEN 'document_dl'  -- 旧定義の資料DL経路（全期間0件・発火時も同カテゴリへ合流）
    WHEN event_name = 'book_appointment'     THEN 'appointment'  -- 相談申込（未実装・将来追加予定）
    ELSE NULL
  END                                                                                AS conversion_type,

  -- スクロール深度。2026-06-08 修正:
  --   GTM custom タグ① scroll_depth は event_params に深度値(scroll_pct)を送出できておらず
  --   全イベントで NULL になっていた（90%到達が常に0になる不具合）。
  --   そこで GA4 拡張計測の標準 scroll イベント（key='percent_scrolled'・90%到達時に発火）を
  --   正の供給源とし、custom の scroll_pct があればそれを優先する COALESCE 方式に変更。
  COALESCE(
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'scroll_pct'),
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'percent_scrolled')
  )                                                                                  AS scroll_pct,

  -- CTAクリック詳細パラメータ（GTM タグ②: GA4イベントタグ「GA4 Event - CTA Click」が
  -- cta_location / cta_type / cta_purpose / cta_id / cta_text として送出。docs/GTM_TAGS.md ② 参照）
  -- ※ marts.cta_breakdown_daily（CTA別の流入・項目8）が参照する。GTM反映後に値が入る。
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'cta_location') AS cta_location,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'cta_type')     AS cta_type,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'cta_purpose')  AS cta_purpose,
  -- ※ cta_id は GA4 が「数字だけの文字列」を数値型として格納するため
  --   （data-cta-id="09" → int_value=9・string_value=NULL を実データで確認）、
  --   string_value だけを読むと番号付きCTAが全て取りこぼされる。両方を COALESCE で拾う。
  --   ゼロ埋め（9→"09"）は marts.cta_number_breakdown_daily 側で正規化する。
  COALESCE(
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'cta_id'),
    CAST((SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'cta_id') AS STRING)
  )                                                                                  AS cta_id,
  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'cta_text')     AS cta_text

FROM
  `__ARK_PROJECT__.analytics___ARK_GA4_PROPID__.events_*`
WHERE
  _TABLE_SUFFIX BETWEEN
    FORMAT_DATE('%Y%m%d', DATE_SUB(CURRENT_DATE(), INTERVAL 13 MONTH))
    AND FORMAT_DATE('%Y%m%d', CURRENT_DATE())
;
