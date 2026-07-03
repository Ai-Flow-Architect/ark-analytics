-- [次フェーズ 🔵 スキャフォールド・未デプロイ] reports/marts.sc_search_terms_daily
-- クライアント要望 (4) 検索ワードの可視化（Search Console連携）
--
-- ⚠️ これは「投入準備済みスキャフォールド」であり daily_refresh.sh には未配線。
--    トリガー（GSC一括エクスポート有効化→searchdata_* 生成・docs/SC_BOUNDARY.md）成立後、
--    本ファイルを sql/marts/ へ移動し daily_refresh に1行追加するだけで <1時間で本番化できる。
--
-- 前提テーブル（GSC Bulk Data Export が出力）:
--   __ARK_SC_DATASET__.searchdata_site_impression  … サイト全体 × クエリ × デバイス × 国 の日次明細
--   列: data_date, query, is_anonymized_query, country, search_type, device,
--       impressions, clicks, sum_top_position
--   平均掲載順位 = sum_top_position / impressions + 1（GSC公式定義）
--
-- 移動先（本番）:  marts.sc_search_terms_daily
-- 更新（本番化後）: 毎日 AM 5:00（GSCエクスポート反映後）

CREATE OR REPLACE TABLE `__ARK_PROJECT__.marts.sc_search_terms_daily`
PARTITION BY data_date
CLUSTER BY query
AS
SELECT
  data_date,
  query,
  search_type,
  -- 実数
  SUM(impressions)                                                   AS impressions,
  SUM(clicks)                                                        AS clicks,
  -- CTR（素値 0.xx / 0〜100）
  ROUND(SAFE_DIVIDE(SUM(clicks), SUM(impressions)), 4)              AS ctr,
  ROUND(SAFE_DIVIDE(SUM(clicks), SUM(impressions)) * 100, 2)        AS ctr_pct,
  -- 平均掲載順位（GSC定義: sum_top_position/impressions + 1。低いほど上位）
  ROUND(SAFE_DIVIDE(SUM(sum_top_position), SUM(impressions)) + 1, 1) AS avg_position
FROM `__ARK_PROJECT__.__ARK_SC_DATASET__.searchdata_site_impression`
WHERE query IS NOT NULL
  AND is_anonymized_query = FALSE   -- 匿名化クエリ（個人特定回避でGSCが伏せる行）は除外
GROUP BY data_date, query, search_type
;
