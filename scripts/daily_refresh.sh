#!/bin/bash
# daily_refresh.sh
# ark-analytics BQテーブル日次自動更新スクリプト
#
# 実行環境:
#   - GitHub Actions (.github/workflows/daily_refresh.yml から呼ばれる)
#   - 手動実行 (cd ~/projects/ark-analytics && ./scripts/daily_refresh.sh)
#
# 環境変数:
#   - ARK_GCP_PROJECT_ID    必須（GitHub Secrets > ARK_GCP_PROJECT_ID）
#   - ARK_GA4_RAW_DATASET   必須（GA4 raw dataset 名・例: analytics_123456789）
#   - LARK_APP_ID/SECRET/CHAT_ID  失敗時の通知用（省略時はskip）
#
# SQLファイル内の以下プレースホルダは実行時に sed で展開される（ベタ書き禁止）:
#   __ARK_PROJECT__       → $ARK_GCP_PROJECT_ID
#   __ARK_GA4_PROPID__    → $ARK_GA4_PROPERTY_ID (analytics_${PROPID} の形でも展開可)

set -euo pipefail
PROJECT="${ARK_GCP_PROJECT_ID:-}"
GA4_PROPID="${ARK_GA4_PROPERTY_ID:-}"
if [[ -z "$PROJECT" || "$PROJECT" == *REDACTED* || "$PROJECT" == __ARK* ]]; then
    echo "[FATAL] ARK_GCP_PROJECT_ID が未設定またはプレースホルダ値です: '$PROJECT'" >&2
    echo "        GitHub Actions の場合は Secrets > ARK_GCP_PROJECT_ID を確認してください。" >&2
    exit 2
fi
if [[ -z "$GA4_PROPID" || "$GA4_PROPID" == *REDACTED* || "$GA4_PROPID" == __ARK* ]]; then
    echo "[FATAL] ARK_GA4_PROPERTY_ID が未設定またはプレースホルダ値です: '$GA4_PROPID'" >&2
    exit 2
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$BASE_DIR/logs"
SQL_DIR="$BASE_DIR/sql"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/refresh_$(date '+%Y%m%d').log"

echo "[$DATE] === ark-analytics 日次更新開始 (project=$PROJECT) ===" | tee -a "$LOG"

notify_lark_failure() {
    local label=$1
    # Bot API方式（src/alert.py）。LARK_APP_ID/SECRET未設定時は alert側でskip
    python3 "$BASE_DIR/src/alert.py" "daily_refresh" "$label step失敗" \
        "project=$PROJECT" "step=$label" "time=$DATE" 2>/dev/null || true
}

run_sql() {
    local label=$1
    local file=$2
    echo "[$DATE] $label 開始..." | tee -a "$LOG"
    # SQLファイル内のプレースホルダを実行時展開（ベタ書き禁止ルール準拠）
    local rendered
    rendered=$(sed -e "s/__ARK_PROJECT__/${PROJECT}/g" -e "s/__ARK_GA4_PROPID__/${GA4_PROPID}/g" "$file")
    if echo "$rendered" | bq query --project_id="$PROJECT" --use_legacy_sql=false >> "$LOG" 2>&1; then
        echo "[$DATE] $label 完了" | tee -a "$LOG"
    else
        echo "[$DATE] ERROR: $label 失敗" | tee -a "$LOG"
        notify_lark_failure "$label"
        exit 1
    fi
}

# staging（VIEW: definition変更を確実に反映するため毎日 CREATE OR REPLACE）
run_sql "staging.stg_ga4_events (VIEW)"   "$SQL_DIR/staging/stg_ga4_events.sql"
run_sql "staging.stg_sessions"            "$SQL_DIR/staging/stg_sessions.sql"

# marts（VIEW→TABLE順）
run_sql "marts.daily_kpi_summary"         "$SQL_DIR/marts/daily_kpi_summary.sql"
run_sql "marts.conversion_funnel_daily"   "$SQL_DIR/marts/conversion_funnel_daily.sql"
run_sql "marts.channel_kpi_monthly"       "$SQL_DIR/marts/channel_kpi_monthly.sql"
run_sql "marts.page_performance"          "$SQL_DIR/marts/page_performance.sql"

# marts（次フェーズ 🟢 追加: ディメンション別 流入/CV・CTA別・ページ別日次）
run_sql "marts.traffic_breakdown_daily"   "$SQL_DIR/marts/traffic_breakdown_daily.sql"
run_sql "marts.cta_breakdown_daily"       "$SQL_DIR/marts/cta_breakdown_daily.sql"
run_sql "marts.page_performance_daily"    "$SQL_DIR/marts/page_performance_daily.sql"

# reports（VIEW: Looker Studio接続先・definition変更を毎日反映）
run_sql "reports.rpt_looker_main (VIEW)"  "$SQL_DIR/reports/rpt_looker_main.sql"
run_sql "reports.rpt_funnel_overview (VIEW)" "$SQL_DIR/reports/rpt_funnel_overview.sql"

echo "[$DATE] === 日次更新完了 → 鮮度チェック ===" | tee -a "$LOG"

# データ鮮度監視: MAX(report_date) が today-2 より古ければ alert.py で通知＋exit 1
if python3 "$BASE_DIR/scripts/check_data_freshness.py" --threshold-days 2 --source post_refresh 2>&1 | tee -a "$LOG"; then
    echo "[$DATE] === 鮮度チェックOK ===" | tee -a "$LOG"
else
    echo "[$DATE] === 鮮度チェック失敗（GA4→BQ Export 異常の可能性） ===" | tee -a "$LOG"
    exit 1
fi
