-- marts.traffic_breakdown_daily
-- ディメンション別 流入・コンバージョン（日次・縦持ち long format）
-- 1テーブルで以下のクライアント要望を満たす（次フェーズ 🟢 追加費用なし範囲）:
--   (5)  チャンネル別のコンバージョン数        dimension_type = 'channel'
--   (6)  PC／スマホ別の流入                    dimension_type = 'device'
--   (7)  主要検索エンジン別の流入              dimension_type = 'search_engine'
--   (9)  LP別の流入                            dimension_type = 'landing_page'
--   (10) Referral別の流入                      dimension_type = 'referral'
--   (15) 新規／リピーターの流入数・率          dimension_type = 'user_type'
--   (16) 離脱ページ別セッション                dimension_type = 'exit_page'
--        （セッション最後の page_view のパス。2026-06-11 検収⑦対応で追加）
-- (3) 全ページ全期間/期間指定: report_date 日次grain のため Looker レポートレベルの
--     期間コントロール1つで全ディメンションページが同一期間に同期する。
-- 更新: 毎日 AM 5:00（staging.stg_sessions 完了後）
--
-- ┌──────────────────────────────────────────────────────────────┐
-- │ 期間集計の単位ルール（Looker 計算フィールド必須・Simpson回避）│
-- │  ・率を期間集計するときは AVG 禁止。raw 列で ratio of sums:    │
-- │     コンバージョン率 = SUM(conversions)/SUM(sessions)*100      │
-- │     エンゲージ率     = SUM(engaged_sessions)/SUM(sessions)*100 │
-- │  ・_pct 列（conversion_rate_pct 等）は単日表示専用（0〜100）。 │
-- │     期間をまたぐ scorecard では使わない。                      │
-- │  ・期間ユニークユーザー（users 列の期間合計）は日次ユニークの  │
-- │     合計のため重複過大。期間ユニークは GA4 本体値を使うこと。  │
-- └──────────────────────────────────────────────────────────────┘

CREATE OR REPLACE TABLE `__ARK_PROJECT__.marts.traffic_breakdown_daily`
PARTITION BY report_date
CLUSTER BY dimension_type
AS
WITH user_first AS (
  -- 各ユーザーの初回セッション日（新規/リピーター判定の単一定義）
  SELECT
    user_pseudo_id,
    MIN(session_date) AS first_session_date
  FROM `__ARK_PROJECT__.staging.stg_sessions`
  GROUP BY user_pseudo_id
),

-- お問い合わせ完了（contact_finish）セッション（2026-07-09 定義書対応）。
-- 定義書のチャネル分析「コンバージョン数 = 各チャネル経由でお問い合わせ完了した件数」は
-- お問い合わせ完了のみが対象。既存 conversions 列（has_conversion）は
-- file_download / book_appointment も含む広義CVのため、定義書準拠の専用列を分離する
-- （現状は DL/予約 が0件のため両列は同値だが、DL計測開始後に乖離する）。
inquiry_sessions AS (
  SELECT DISTINCT session_id AS inq_session_id
  FROM `__ARK_PROJECT__.staging.stg_ga4_events`
  WHERE conversion_type = 'inquiry'  -- 2026-07-23: /document/の資料DLを除外（お問い合わせのみ）
    AND session_id IS NOT NULL
),

sess AS (
  SELECT
    s.session_date                                    AS report_date,
    s.session_id,
    s.user_pseudo_id,
    s.is_engaged,
    s.has_conversion,
    (inq.inq_session_id IS NOT NULL)                  AS has_inquiry_conversion,
    s.page_view_count,
    (s.session_date = uf.first_session_date)          AS is_new_user_session,
    -- 新規/リピーター（セッション単位・2026-07-09 定義書対応）:
    --   定義書「訪問（セッション）が初回だったか、2回目以降だったか」に厳密一致させるため
    --   GA4ネイティブ ga_session_number=1 で判定（param欠損セッションのみ日付粒度に
    --   フォールバック）。日付粒度のみだと同日2回目以降の再訪が「新規」に混入する
    --   （2026-06実測: 新規477→442 の35セッション差）。
    COALESCE(s.is_first_session,
             s.session_date = uf.first_session_date)  AS is_first_session,
    s.channel_grouping,
    s.source,
    s.medium,

    -- (6) デバイス日本語ラベル
    CASE s.device_category
      WHEN 'desktop' THEN 'PC'
      WHEN 'mobile'  THEN 'スマホ'
      WHEN 'tablet'  THEN 'タブレット'
      ELSE 'その他'
    END                                               AS device_label,

    -- (7) 主要検索エンジン分類（Organic/Paid Search のセッションのみ）
    CASE
      WHEN s.medium = 'organic'
        OR s.channel_grouping IN ('Organic Search', 'Paid Search') THEN
        CASE
          WHEN LOWER(s.source) LIKE '%google%'     THEN 'Google'
          WHEN LOWER(s.source) LIKE '%yahoo%'      THEN 'Yahoo!'
          WHEN LOWER(s.source) LIKE '%bing%'       THEN 'Bing'
          WHEN LOWER(s.source) LIKE '%duckduckgo%' THEN 'DuckDuckGo'
          WHEN LOWER(s.source) LIKE '%baidu%'      THEN 'Baidu'
          WHEN LOWER(s.source) LIKE '%naver%'      THEN 'Naver'
          WHEN LOWER(s.source) LIKE '%ecosia%'     THEN 'Ecosia'
          ELSE 'その他検索エンジン'
        END
      ELSE NULL
    END                                               AS search_engine,

    -- (9) ランディングページ（URL → パス正規化。クエリ/フラグメント除去）
    COALESCE(
      NULLIF(REGEXP_EXTRACT(s.landing_page, r'https?://[^/]+([^?#]*)'), ''),
      '(not set)'
    )                                                 AS landing_path,

    -- (16) 離脱ページ（セッション最後の page_view。landing と同じパス正規化）
    COALESCE(
      NULLIF(REGEXP_EXTRACT(s.exit_page, r'https?://[^/]+([^?#]*)'), ''),
      '(not set)'
    )                                                 AS exit_path

  FROM `__ARK_PROJECT__.staging.stg_sessions` s
  JOIN user_first uf USING (user_pseudo_id)
  LEFT JOIN inquiry_sessions inq ON s.session_id = inq.inq_session_id
),

exploded AS (
  -- stg_sessions を1回だけスキャンし、7ディメンションを配列UNNESTで縦持ち化する。
  -- （UNION ALL 7本だと sess=stg_sessions を7回スキャンするため、配列展開で単一スキャンに最適化）
  --   (6)device / (5)channel / (7)search_engine / (9)landing_page / (10)referral / (15)user_type / (16)exit_page
  SELECT
    report_date,
    dim.dimension_type,
    dim.dimension_value,
    session_id, user_pseudo_id, is_engaged, has_conversion, has_inquiry_conversion,
    page_view_count, is_new_user_session, is_first_session
  FROM sess,
  UNNEST([
    STRUCT('device'        AS dimension_type, device_label                          AS dimension_value),
    STRUCT('channel'       AS dimension_type, channel_grouping                      AS dimension_value),
    STRUCT('search_engine' AS dimension_type, search_engine                         AS dimension_value),
    STRUCT('landing_page'  AS dimension_type, landing_path                          AS dimension_value),
    STRUCT('referral'      AS dimension_type,
           IF(channel_grouping = 'Referral', COALESCE(NULLIF(source, ''), '(not set)'), NULL) AS dimension_value),
    -- user_type は 2026-07-09 にセッション単位判定（is_first_session）へ切替（定義書準拠）。
    -- 旧: is_new_user_session（日付粒度・同日2回目以降も新規扱い）
    STRUCT('user_type'     AS dimension_type, IF(is_first_session, '新規', 'リピーター')      AS dimension_value),
    STRUCT('exit_page'     AS dimension_type, exit_path                             AS dimension_value)
  ]) AS dim
  -- search_engine は Organic/Paid Search のみ・referral は Referral チャネルのみ（それ以外は NULL）
  -- → 元の UNION ALL 各 WHERE と等価。NULL を落とすことで部分集合ディメンションを再現する。
  WHERE dim.dimension_value IS NOT NULL
)

SELECT
  report_date,
  dimension_type,
  dimension_value,

  -- ── 実数（Looker の期間集計＝SUM はこの raw 列で行う） ───────
  COUNT(DISTINCT session_id)                                          AS sessions,
  COUNT(DISTINCT user_pseudo_id)                                      AS users,
  COUNT(DISTINCT IF(is_new_user_session, user_pseudo_id, NULL))       AS new_users,
  COUNTIF(is_engaged)                                                 AS engaged_sessions,
  SUM(page_view_count)                                                AS pageviews,
  COUNTIF(has_conversion)                                             AS conversions,
  -- コンバージョン数【定義書2026-07-09 準拠版・お問い合わせ完了のみ】
  --   Looker のチャネル別/LP別「コンバージョン数」「CV率」はこちらを使うこと。
  --   CV率（期間集計）= SUM(inquiry_conversions)/SUM(sessions)*100（ratio of sums）。
  COUNTIF(has_inquiry_conversion)                                     AS inquiry_conversions,

  -- ── 率（素値 0.xx・後方互換／単日参照用） ───────────────────
  ROUND(SAFE_DIVIDE(COUNTIF(is_engaged), COUNT(DISTINCT session_id)), 4)
                                                                      AS engagement_rate,
  ROUND(SAFE_DIVIDE(COUNTIF(has_conversion), COUNT(DISTINCT session_id)), 4)
                                                                      AS conversion_rate,

  -- ── 率（0〜100・Looker scorecard 単日表示用） ───────────────
  ROUND(SAFE_DIVIDE(COUNTIF(is_engaged), COUNT(DISTINCT session_id)) * 100, 2)      AS engagement_rate_pct,
  ROUND(SAFE_DIVIDE(COUNTIF(has_conversion), COUNT(DISTINCT session_id)) * 100, 2)  AS conversion_rate_pct

FROM exploded
GROUP BY report_date, dimension_type, dimension_value
;
