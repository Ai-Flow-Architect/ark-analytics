"""
check_data_freshness.py
marts.daily_kpi_summary の鮮度を監視する。
MAX(report_date) が today - threshold_days より古ければ Lark通知 + sys.exit(1)。

呼び出し方:
  python3 scripts/check_data_freshness.py [--threshold-days 2] [--source pre_report|post_refresh]

環境変数:
  GOOGLE_APPLICATION_CREDENTIALS  必須（GitHub Actionsでは auth ステップで設定済）
  GOOGLE_CLOUD_PROJECT             省略時 ark-hd-analytics
  LARK_APP_ID/SECRET/CHAT_ID       通知用（src/alert.py 経由）

終了コード:
  0: 鮮度OK（threshold以内）
  1: データが古い・テーブルなし → Lark通知済み
  2: 引数エラー
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

# プロジェクトルート（scripts/からの相対）をパスに追加
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from src.alert import notify_failure  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold-days", type=int, default=2,
                        help="許容遅延日数（既定: 2日。今日-threshold より古いと異常）")
    parser.add_argument("--source", default="post_refresh",
                        choices=["pre_report", "post_refresh"],
                        help="呼び出し元を識別する文字列（通知の context に入る）")
    args = parser.parse_args()

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "ark-hd-analytics")

    try:
        from google.cloud import bigquery
    except ImportError:
        notify_failure(
            job="data_freshness_check",
            reason="google-cloud-bigquery が未インストール",
            context={"source": args.source},
        )
        return 1

    client = bigquery.Client(project=project_id)
    query = f"""
    SELECT MAX(report_date) AS max_date, COUNT(*) AS row_count
    FROM `{project_id}.marts.daily_kpi_summary`
    """
    try:
        df = client.query(query).to_dataframe()
    except Exception as e:
        notify_failure(
            job="data_freshness_check",
            reason=f"marts.daily_kpi_summary クエリ失敗: {e}",
            context={"source": args.source, "project": project_id},
        )
        return 1

    if df.empty or df.iloc[0]["row_count"] == 0:
        notify_failure(
            job="data_freshness_check",
            reason="marts.daily_kpi_summary が空（行数0）",
            context={"source": args.source, "project": project_id},
        )
        return 1

    max_date_val = df.iloc[0]["max_date"]
    if max_date_val is None:
        notify_failure(
            job="data_freshness_check",
            reason="marts.daily_kpi_summary の MAX(report_date) が NULL",
            context={"source": args.source, "project": project_id},
        )
        return 1

    # to_dataframe() は datetime.date を返す
    max_date = max_date_val if isinstance(max_date_val, date) else max_date_val.date()

    today = date.today()
    threshold = today - timedelta(days=args.threshold_days)

    if max_date < threshold:
        delay_days = (today - max_date).days
        notify_failure(
            job="data_freshness_check",
            reason=(
                f"marts.daily_kpi_summary の最新データが {max_date} "
                f"（今日 {today} から {delay_days} 日前）。"
                f"GA4→BigQuery Export の遅延・停止 か daily_refresh の障害が疑われます。"
            ),
            context={
                "source": args.source,
                "max_date": str(max_date),
                "today": str(today),
                "threshold_days": str(args.threshold_days),
            },
        )
        return 1

    delay_days = (today - max_date).days
    print(f"[freshness] OK max_date={max_date} delay={delay_days}d source={args.source}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
