-- marts.cta_number_breakdown_daily
-- CTAボタン「番号別（data-cta-id 01〜19）」の内訳・日次
--   クライアント要望（2026-07-14）: 同一文言のボタン（ヘッダー/フッターの
--   「お問い合わせ」など）を取り違えなく、付与された番号どおり正確に計測する。
--
-- 仕組み: 御社サイトの各CTAボタンに付与された HTML属性 data-cta-id="01".."19" を
--   GTMタグ②（GA4 Event - CTA Click）が cta_id パラメータとして送出し、
--   staging.stg_ga4_events.cta_id に格納される（docs/GTM_TAGS.md ②・getCtaId=el.dataset.ctaId）。
--   GTM version10（2026-07-13 公開）でセレクタ配列に [data-cta-id] を追加済のため、
--   番号付与済ボタンのクリックが確実に発火する。
--
-- 番号 → ページ/位置/種別 の対応表は client 提供の番号票（2026-07-13）が正本。
--   ※ 削除予定ボタン（営業メリットFVの資料DL / 導入事例 / サービス紹介・営業戦略内）は
--     付与対象外＝番号なしのため本martには現れない（正しい挙動）。
--
-- 集計: 番号（cta_id）を主軸に、クリック数・クリックセッション数・ユーザー数・
--   CTA経由CV（お問い合わせ完了）到達セッション数と到達率を出す。
--   率は ratio of sums（Looker計算フィールドで SUM(cv)/SUM(click_sessions)）。
-- 更新: 毎日 AM 5:00（staging.stg_ga4_events 完了後）
--
-- ※ data-cta-id の本番付与は 2026-07-14、テスト操作は 2026-07-22 予定。
--   それまでは番号付き行は 0 行になり得るが、SQLは正しく、データ到着後そのまま埋まる
--   （既存 marts.cta_breakdown_daily と同じ設計思想）。

CREATE OR REPLACE TABLE `__ARK_PROJECT__.marts.cta_number_breakdown_daily`
PARTITION BY report_date
CLUSTER BY cta_id
AS
WITH
-- ── 番号対応表（client 番号票 2026-07-13 が正本・ハードコードのマスタ）──────────
cta_number_master AS (
  SELECT * FROM UNNEST([
    STRUCT('01' AS cta_id, '全ページ共通' AS page_group, '/(全ページ)' AS page_path_label, 'ヘッダー'        AS position_label, '資料ダウンロード' AS purpose_label),
    STRUCT('02', '全ページ共通', '/(全ページ)', 'フッター',            'お問い合わせ'),
    STRUCT('03', '全ページ共通', '/(全ページ)', 'フローティング(追従)', '資料ダウンロード'),
    STRUCT('04', '全ページ共通', '/(全ページ)', 'フローティング(追従)', 'お問い合わせ'),
    STRUCT('05', 'TOP',          '/',            'ファーストビュー',    '資料ダウンロード'),
    STRUCT('06', 'TOP',          '/',            'ファーストビュー',    'お問い合わせ'),
    STRUCT('07', 'TOP',          '/',            '最下部',              '資料ダウンロード'),
    STRUCT('08', 'TOP',          '/',            '最下部',              'お問い合わせ'),
    STRUCT('09', 'サービス詳細',  '/service/',    '本文',                '資料ダウンロード'),
    STRUCT('10', 'サービス詳細',  '/service/',    '本文',                'お問い合わせ'),
    STRUCT('11', '営業メリット',  '/sales-flow/', '本文',                '資料ダウンロード'),
    STRUCT('12', '営業メリット',  '/sales-flow/', '本文',                'お問い合わせ'),
    STRUCT('13', '収益モデル',    '/revenue-model/', 'ファーストビュー', '資料ダウンロード'),
    STRUCT('14', '収益モデル',    '/revenue-model/', '最下部',           '資料ダウンロード'),
    STRUCT('15', '収益モデル',    '/revenue-model/', '最下部',           'お問い合わせ'),
    STRUCT('16', 'パートナー制度', '/partner-program/', '本文',          '資料ダウンロード'),
    STRUCT('17', 'パートナー制度', '/partner-program/', '本文',          'お問い合わせ'),
    STRUCT('18', 'Q&A',          '/faq/',        '本文',                '資料ダウンロード'),
    STRUCT('19', 'Q&A',          '/faq/',        '本文',                'お問い合わせ')
  ])
),

-- ── 番号付きCTAクリック（cta_id が 01〜19 のもののみを対象）───────────────
cta_clicks AS (
  SELECT
    event_date       AS report_date,
    session_id,
    user_pseudo_id,
    -- 番号は "01".."19" 形式で送出される想定。前後空白を除去し、
    -- 1桁数字で来た場合（"1"）も 2桁ゼロ埋めに正規化して対応表と確実に突合する。
    CASE
      WHEN REGEXP_CONTAINS(TRIM(cta_id), r'^[0-9]{1,2}$')
        THEN LPAD(TRIM(cta_id), 2, '0')
      ELSE NULL
    END              AS cta_id_norm,
    cta_text
  FROM `__ARK_PROJECT__.staging.stg_ga4_events`
  WHERE event_name = 'cta_click'
    AND session_id IS NOT NULL
),

-- このセッションが最終的にお問い合わせ完了（contact_finish）まで到達したか
converting_sessions AS (
  SELECT
    session_id,
    LOGICAL_OR(event_name = 'contact_finish') AS has_inquiry
  FROM `__ARK_PROJECT__.staging.stg_ga4_events`
  WHERE is_conversion
    AND session_id IS NOT NULL
  GROUP BY session_id
),

agg AS (
  SELECT
    c.report_date,
    c.cta_id_norm                                                      AS cta_id,
    -- 参考: そのボタンで実際に送出された文言（最頻値）。番号と実ボタンの突合確認用。
    APPROX_TOP_COUNT(c.cta_text, 1)[OFFSET(0)].value                   AS sample_cta_text,

    COUNT(*)                                                           AS cta_clicks,
    COUNT(DISTINCT c.session_id)                                       AS click_sessions,
    COUNT(DISTINCT c.user_pseudo_id)                                   AS click_users,
    COUNT(DISTINCT IF(cv.has_inquiry, c.session_id, NULL))            AS inquiry_cv_click_sessions
  FROM cta_clicks c
  LEFT JOIN converting_sessions cv ON c.session_id = cv.session_id
  WHERE c.cta_id_norm IS NOT NULL
  GROUP BY c.report_date, c.cta_id_norm
)

SELECT
  a.report_date,
  a.cta_id,
  -- 対応表ラベル（未知番号=対応表外の番号が来た場合は (対応表外) と明示）
  COALESCE(m.page_group,     '(対応表外)')                            AS page_group,
  COALESCE(m.page_path_label, '(対応表外)')                          AS page_path_label,
  COALESCE(m.position_label,  '(対応表外)')                          AS position_label,
  COALESCE(m.purpose_label,   '(対応表外)')                          AS purpose_label,
  -- 表示用ラベル: 「01 ヘッダー 資料ダウンロード」形式
  CONCAT(a.cta_id, ' ',
         COALESCE(m.position_label, ''), ' ',
         COALESCE(m.purpose_label, ''))                              AS cta_label,
  a.sample_cta_text,

  a.cta_clicks,
  a.click_sessions,
  a.click_users,
  a.inquiry_cv_click_sessions,

  -- CTA番号経由のお問い合わせCV到達率（素値 0.xx）
  ROUND(SAFE_DIVIDE(a.inquiry_cv_click_sessions, a.click_sessions), 4)      AS cta_to_cv_rate,
  -- 同（0〜100・単日表示用）
  ROUND(SAFE_DIVIDE(a.inquiry_cv_click_sessions, a.click_sessions) * 100, 2) AS cta_to_cv_rate_pct

FROM agg a
LEFT JOIN cta_number_master m ON a.cta_id = m.cta_id
;
