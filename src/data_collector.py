"""
data_collector.py
BigQueryから分析用KPIデータを取得するモジュール
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

import pandas as pd
import yaml
from google.cloud import bigquery
from google.oauth2 import service_account


from src._config_loader import get_project_id, load_config as _load_config, make_bq_client


class GA4DataCollector:
    """BigQueryからGA4分析データを取得するクラス"""

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or _load_config()
        self.project_id = get_project_id(self.config)

        # サービスアカウントキーがあればそれを使用、なければADC
        key_path = self.config["gcp"].get("service_account_key", "")
        if key_path and os.path.exists(key_path):
            credentials = service_account.Credentials.from_service_account_file(
                key_path,
                scopes=["https://www.googleapis.com/auth/bigquery.readonly"],
            )
            self.client = make_bq_client(self.project_id, credentials=credentials)
        else:
            # Application Default Credentials（ローカル開発時は gcloud auth login）
            # quota project を project_id に固定（ローカルADC汚染による403を防止）
            self.client = make_bq_client(self.project_id)

    def get_monthly_kpi(self, target_month: str) -> dict[str, Any]:
        """
        月次KPI集計を返す
        target_month: '2026-04' 形式
        """
        # 率指標は日次率の単純平均(AVG)ではなく期間加重比(SUM分子/SUM分母=ratio of sums)で算出する。
        # AVGだと少セッション日の率が過大評価され期間比から乖離する（CVR/エンゲージメント率の水増しバグの真因）。
        # period_start/period_end は「月初〜送信日」ではなく実際にデータが存在する集計範囲(MIN/MAX report_date)。
        query = f"""
        SELECT
          FORMAT_DATE('%Y-%m', MIN(report_date))    AS month,
          MIN(report_date)                          AS period_start,
          MAX(report_date)                          AS period_end,
          SUM(sessions)                             AS sessions,
          SUM(users)                                AS users,
          SUM(new_users)                            AS new_users,
          SUM(engaged_sessions)                     AS engaged_sessions,
          ROUND(SAFE_DIVIDE(SUM(engaged_sessions), SUM(sessions)), 4)         AS engagement_rate,
          ROUND(SAFE_DIVIDE(SUM(new_users), NULLIF(SUM(users), 0)), 4)        AS new_user_rate,
          SUM(contact_form_views)                   AS contact_form_views,
          SUM(contact_form_submissions)             AS inquiries,
          SUM(document_downloads)                   AS downloads,
          SUM(appointment_bookings)                 AS appointments,
          SUM(total_conversions)                    AS total_conversions,
          ROUND(SAFE_DIVIDE(SUM(contact_form_submissions), NULLIF(SUM(contact_form_views), 0)), 4)  AS contact_cr,
          ROUND(SAFE_DIVIDE(SUM(contact_form_submissions) + SUM(document_downloads), NULLIF(SUM(sessions), 0)), 4)  AS overall_cvr
        FROM `{self.project_id}.marts.daily_kpi_summary`
        WHERE FORMAT_DATE('%Y-%m', report_date) = @target_month
        HAVING COUNT(*) > 0
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("target_month", "STRING", target_month)
            ]
        )
        df = self.client.query(query, job_config=job_config).to_dataframe()
        if df.empty:
            return {}
        return df.iloc[0].to_dict()

    def get_channel_breakdown(self, target_month: str) -> pd.DataFrame:
        """チャネル別月次内訳を返す"""
        query = f"""
        SELECT
          channel_grouping,
          sessions,
          conversions,
          ROUND(conversion_rate * 100, 2)  AS conversion_rate_pct,
          ROUND(engagement_rate * 100, 2)  AS engagement_rate_pct
        FROM `{self.project_id}.marts.channel_kpi_monthly`
        WHERE FORMAT_DATE('%Y-%m', report_month) = @target_month
        ORDER BY sessions DESC
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("target_month", "STRING", target_month)
            ]
        )
        return self.client.query(query, job_config=job_config).to_dataframe()

    def get_mom_comparison(self, target_month: str) -> dict[str, Any]:
        """前月比データを返す（当月 vs 前月）"""
        from dateutil.relativedelta import relativedelta

        year, month = map(int, target_month.split("-"))
        prev_month = date(year, month, 1) - relativedelta(months=1)
        prev_month_str = prev_month.strftime("%Y-%m")

        current = self.get_monthly_kpi(target_month)
        previous = self.get_monthly_kpi(prev_month_str)

        if not current or not previous:
            return {"current": current, "previous": previous, "diff": {}}

        diff = {}
        for key in current:
            if key == "month":
                continue
            try:
                prev_val = float(previous.get(key, 0) or 0)
                curr_val = float(current.get(key, 0) or 0)
                diff[f"{key}_mom"] = (
                    round((curr_val - prev_val) / prev_val * 100, 1)
                    if prev_val != 0
                    else 0.0
                )
            except (TypeError, ValueError):
                diff[f"{key}_mom"] = 0.0

        return {"current": current, "previous": previous, "diff": diff}

    def get_top_pages(self, target_month: str, limit: int = 10) -> pd.DataFrame:
        """PV上位ページを返す"""
        query = f"""
        SELECT
          page_path,
          page_title,
          SUM(pageviews)                          AS pageviews,
          ROUND(AVG(avg_time_on_page_sec), 1)     AS avg_time_sec,
          ROUND(AVG(scroll_90pct_rate) * 100, 1)  AS scroll_90pct_rate_pct,
          ROUND(AVG(cta_click_rate) * 100, 1)     AS cta_click_rate_pct,
          SUM(conversions_from_page)              AS conversions
        FROM `{self.project_id}.marts.page_performance`
        WHERE week_start >= DATE_TRUNC(
          DATE(CONCAT(@target_month, '-01')), MONTH
        )
        AND week_start < DATE_ADD(
          DATE_TRUNC(DATE(CONCAT(@target_month, '-01')), MONTH), INTERVAL 1 MONTH
        )
        GROUP BY page_path, page_title
        ORDER BY pageviews DESC
        LIMIT @lim
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("target_month", "STRING", target_month),
                bigquery.ScalarQueryParameter("lim", "INT64", limit),
            ]
        )
        return self.client.query(query, job_config=job_config).to_dataframe()

    def get_funnel_summary(self, target_month: str) -> dict[str, Any]:
        """ファネル集計（月次平均）"""
        query = f"""
        SELECT
          ROUND(AVG(step1_sessions), 0)       AS avg_sessions,
          ROUND(AVG(step3_contact_page), 0)   AS avg_contact_page,
          ROUND(AVG(step4_form_start), 0)     AS avg_form_start,
          ROUND(AVG(step5_submission), 0)     AS avg_submission,
          ROUND(AVG(step1_to_2b_rate)*100, 2)  AS step1_to_2_pct,
          ROUND(AVG(step2b_to_3_rate)*100, 2)  AS step2_to_3_pct,
          ROUND(AVG(step3_to_4_rate)*100, 2)  AS step3_to_4_pct,
          ROUND(AVG(step4_to_5_rate)*100, 2)  AS step4_to_5_pct,
          ROUND(AVG(overall_inquiry_cvr)*100, 2) AS overall_inquiry_cvr_pct
        FROM `{self.project_id}.marts.conversion_funnel_daily`
        WHERE FORMAT_DATE('%Y-%m', report_date) = @target_month
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("target_month", "STRING", target_month)
            ]
        )
        df = self.client.query(query, job_config=job_config).to_dataframe()
        return df.iloc[0].to_dict() if not df.empty else {}
