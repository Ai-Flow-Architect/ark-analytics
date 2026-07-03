"""
verify_breakdown.py — 次フェーズ 🟢 新規テーブルの実データ整合性を機械検証する

新規 marts/reports を実データで読み、以下を検証する（read-only・partition絞りで低コスト）:
  A. traffic_breakdown_daily のディメンション別 sessions/conversions
  B. 全体を分割するディメンション（device/channel/user_type/landing_page）の sessions 合計が
     互いに一致し、かつ daily_kpi_summary の sessions 合計とも一致する（整合性の核）
  C. 新規/リピーターの内訳・チャネル別CV・デバイス別流入のサンプル
  D. funnel_overview / cta_breakdown_daily / page_performance_daily の存在＆サンプル

使い方:
  ARK_GCP_PROJECT_ID=... GOOGLE_APPLICATION_CREDENTIALS=/path/sa.json \
  python3 scripts/verify_breakdown.py [--start 2026-05-01]
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys


def _bq() -> str:
    for c in (os.path.expanduser("~/google-cloud-sdk/bin/bq"), shutil.which("bq") or ""):
        if c and os.path.exists(c):
            return c
    print("[FATAL] bq が見つかりません", file=sys.stderr)
    sys.exit(2)


def run(bq: str, project: str, location: str, label: str, sql: str) -> None:
    print(f"\n--- {label} ---")
    proc = subprocess.run(
        [bq, "query", "--use_legacy_sql=false", f"--location={location}",
         f"--project_id={project}", "--format=pretty", "--max_rows=50"],
        input=sql, text=True, capture_output=True,
    )
    if proc.returncode == 0:
        print(proc.stdout.strip() or "(0 rows)")
    else:
        print("[FAIL] " + (proc.stderr or proc.stdout or "").strip()[:800])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-05-01")
    args = ap.parse_args()

    project = os.environ.get("ARK_GCP_PROJECT_ID", "").strip()
    location = os.environ.get("ARK_BQ_LOCATION", "asia-northeast1").strip()
    if not project:
        print("[FATAL] ARK_GCP_PROJECT_ID 未設定", file=sys.stderr)
        return 2
    bq = _bq()
    p = project
    s = args.start
    win = f"report_date BETWEEN '{s}' AND CURRENT_DATE()"

    run(bq, p, location, "A. traffic_breakdown_daily ディメンション別 合計",
        f"""SELECT dimension_type,
              SUM(sessions) AS sessions,
              SUM(conversions) AS conversions,
              SUM(new_users) AS new_users,
              COUNT(DISTINCT dimension_value) AS n_values
            FROM `{p}.marts.traffic_breakdown_daily`
            WHERE {win}
            GROUP BY dimension_type ORDER BY dimension_type""")

    run(bq, p, location, "B. 整合性: 全体分割ディメンションの sessions 合計 vs daily_kpi_summary",
        f"""WITH bd AS (
              SELECT dimension_type, SUM(sessions) AS sessions
              FROM `{p}.marts.traffic_breakdown_daily`
              WHERE {win} AND dimension_type IN ('device','channel','user_type','landing_page')
              GROUP BY dimension_type
            ), kpi AS (
              SELECT 'daily_kpi_summary' AS dimension_type, SUM(sessions) AS sessions
              FROM `{p}.marts.daily_kpi_summary` WHERE {win}
            )
            SELECT * FROM bd UNION ALL SELECT * FROM kpi ORDER BY dimension_type""")

    run(bq, p, location, "C-1. (5) チャネル別 流入・CV",
        f"""SELECT dimension_value AS channel, SUM(sessions) AS sessions, SUM(conversions) AS conversions
            FROM `{p}.marts.traffic_breakdown_daily`
            WHERE {win} AND dimension_type='channel'
            GROUP BY 1 ORDER BY sessions DESC""")

    run(bq, p, location, "C-2. (6) デバイス別 流入",
        f"""SELECT dimension_value AS device, SUM(sessions) AS sessions, SUM(conversions) AS conversions
            FROM `{p}.marts.traffic_breakdown_daily`
            WHERE {win} AND dimension_type='device'
            GROUP BY 1 ORDER BY sessions DESC""")

    run(bq, p, location, "C-3. (15) 新規/リピーター 流入",
        f"""SELECT dimension_value AS user_type, SUM(sessions) AS sessions,
              ROUND(SAFE_DIVIDE(SUM(conversions), SUM(sessions))*100, 2) AS cvr_pct
            FROM `{p}.marts.traffic_breakdown_daily`
            WHERE {win} AND dimension_type='user_type'
            GROUP BY 1 ORDER BY sessions DESC""")

    run(bq, p, location, "C-4. (7) 検索エンジン別 / (10) Referral別 (上位)",
        f"""SELECT dimension_type, dimension_value, SUM(sessions) AS sessions
            FROM `{p}.marts.traffic_breakdown_daily`
            WHERE {win} AND dimension_type IN ('search_engine','referral')
            GROUP BY 1,2 ORDER BY sessions DESC LIMIT 15""")

    run(bq, p, location, "D-1. (9) LP別 流入 (上位5)",
        f"""SELECT dimension_value AS landing_path, SUM(sessions) AS sessions, SUM(conversions) AS conversions
            FROM `{p}.marts.traffic_breakdown_daily`
            WHERE {win} AND dimension_type='landing_page'
            GROUP BY 1 ORDER BY sessions DESC LIMIT 5""")

    run(bq, p, location, "D-2. (11) page_performance_daily 上位ページ",
        f"""SELECT page_path, SUM(pageviews) AS pv, SUM(unique_pageviews) AS uu,
              SUM(conversions_from_page) AS cv
            FROM `{p}.marts.page_performance_daily`
            WHERE {win}
            GROUP BY 1 ORDER BY pv DESC LIMIT 5""")

    run(bq, p, location, "D-3. (12) rpt_funnel_overview 直近",
        f"""SELECT report_date, stage1_cta_click, stage2_form_reach, stage3_completion,
              contact_page_reach
            FROM `{p}.reports.rpt_funnel_overview`
            WHERE {win}
            ORDER BY report_date DESC LIMIT 7""")

    run(bq, p, location, "D-4. (8) cta_breakdown_daily 件数（GTM反映待ちなら 0 が正常）",
        f"""SELECT COUNT(*) AS n_rows, SUM(cta_clicks) AS clicks, SUM(click_sessions) AS click_sessions
            FROM `{p}.marts.cta_breakdown_daily`
            WHERE {win}""")

    print("\n=== verify_breakdown 完了 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
