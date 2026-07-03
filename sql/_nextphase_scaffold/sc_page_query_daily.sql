-- [次フェーズ 🔵 スキャフォールド・未デプロイ] marts.sc_page_query_daily
-- クライアント要望 (4) の発展: ページ別 × 検索クエリ（URL粒度・追加範囲 docs/SC_BOUNDARY.md ④）
--
-- ⚠️ 投入準備済みスキャフォールド。daily_refresh.sh 未配線。
--    GSCエクスポート有効化後、sql/marts/ へ移動＋1行配線で <1時間 本番化。
--
-- 前提テーブル: __ARK_SC_DATASET__.searchdata_url_impression
--   列: data_date, url, query, is_anonymized_query, country, search_type, device,
--       impressions, clicks, sum_top_position
--   ※ GA4 page_path との結合キーは url → REGEXP でパス抽出して page_path 化（GA4 staging と整合）

CREATE OR REPLACE TABLE `__ARK_PROJECT__.marts.sc_page_query_daily`
PARTITION BY data_date
CLUSTER BY page_path
AS
SELECT
  data_date,
  -- GA4 staging.stg_ga4_events.page_path と同じパス正規化（クエリ/フラグメント除去）
  COALESCE(NULLIF(REGEXP_EXTRACT(url, r'https?://[^/]+([^?#]*)'), ''), '(not set)') AS page_path,
  query,
  SUM(impressions)                                                   AS impressions,
  SUM(clicks)                                                        AS clicks,
  ROUND(SAFE_DIVIDE(SUM(clicks), SUM(impressions)) * 100, 2)        AS ctr_pct,
  ROUND(SAFE_DIVIDE(SUM(sum_top_position), SUM(impressions)) + 1, 1) AS avg_position
FROM `__ARK_PROJECT__.__ARK_SC_DATASET__.searchdata_url_impression`
WHERE query IS NOT NULL
  AND is_anonymized_query = FALSE
GROUP BY data_date, page_path, query
;
