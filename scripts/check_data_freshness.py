"""
check_data_freshness.py
marts.daily_kpi_summary の鮮度を監視する。
MAX(report_date) が today - threshold_days より古ければ Lark通知 + sys.exit(1)。

呼び出し方:
  python3 scripts/check_data_freshness.py [--threshold-days 2] [--source pre_report|post_refresh]

環境変数:
  GOOGLE_APPLICATION_CREDENTIALS  必須（GitHub Actionsでは auth ステップで設定済）
  ARK_GCP_PROJECT_ID               必須（src._config_loader.get_project_id で解決）
  GOOGLE_CLOUD_PROJECT             任意（ARK_GCP_PROJECT_ID 未設定時のフォールバック）
  LARK_APP_ID/SECRET/CHAT_ID       通知用（src/alert.py 経由）

終了コード:
  0: 鮮度OK（threshold以内）
  1: データが古い・テーブルなし → Lark通知済み
  2: 引数エラー / プロジェクトID未解決（=設定不備）
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
from src._config_loader import get_project_id, make_bq_client  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold-days", type=int, default=2,
                        help="許容遅延日数（既定: 2日。今日-threshold より古いと異常）")
    parser.add_argument("--source", default="post_refresh",
                        help="呼び出し元を識別する任意文字列（通知の context に入る）")
    args = parser.parse_args()

    try:
        project_id = get_project_id()
    except RuntimeError as e:
        notify_failure(
            job="data_freshness_check",
            reason=f"GCPプロジェクトID未解決: {e}",
            context={"source": args.source},
        )
        return 2

    try:
        import google.cloud.bigquery  # noqa: F401
    except ImportError:
        notify_failure(
            job="data_freshness_check",
            reason="google-cloud-bigquery が未インストール",
            context={"source": args.source, "project": project_id},
        )
        return 1

    # quota project を project_id に固定（ローカルADC汚染による403を防止）
    client = make_bq_client(project_id)
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

    # ── 欠落日（中抜け）検知 ─────────────────────────────────────
    # MAX(report_date) 監視は「単日だけ欠ける」事象（例: 2026-06-01 の
    # GA4→BQ Export 単日未生成）を原理的に検知できないため、
    # 直近14日窓の歯抜けを別途検査する（末尾 threshold 日は正常ラグとして除外）。
    gap_rc = _check_date_gaps(client, project_id, today, args)
    if gap_rc != 0:
        return gap_rc
    return 0


# Google側で確認済みの既知欠落日（再通知しない）
KNOWN_GAPS = {"2026-06-01"}


def _check_date_gaps(client, project_id: str, today: date, args) -> int:
    gap_query = f"""
    SELECT FORMAT_DATE('%Y-%m-%d', d) AS missing_date
    FROM UNNEST(GENERATE_DATE_ARRAY(
        DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 14 DAY),
        DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL {args.threshold_days + 1} DAY)
    )) AS d
    LEFT JOIN (
        SELECT DISTINCT report_date FROM `{project_id}.marts.daily_kpi_summary`
    ) t ON t.report_date = d
    WHERE t.report_date IS NULL
    ORDER BY d
    """
    try:
        gap_df = client.query(gap_query).to_dataframe()
    except Exception as e:
        notify_failure(
            job="data_freshness_check",
            reason=f"欠落日検査クエリ失敗: {e}",
            context={"source": args.source, "project": project_id},
        )
        return 1

    gaps = [g for g in gap_df["missing_date"].tolist() if g not in KNOWN_GAPS]
    if gaps:
        notify_failure(
            job="data_freshness_check",
            reason=(
                f"daily_kpi_summary に欠落日（中抜け）を検出: {', '.join(gaps)}。"
                f"GA4→BigQuery Export の単日未生成が疑われます"
                f"（GA4本体にデータがあるかは GA4 Data API/管理画面で確認）。"
            ),
            context={"source": args.source, "missing_dates": ", ".join(gaps)},
        )
        return 1

    print(f"[freshness] gap-check OK (known gaps excluded: {sorted(KNOWN_GAPS)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
