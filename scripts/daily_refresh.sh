#!/bin/bash
# daily_refresh.sh
# ark-analytics BQテーブル日次自動更新スクリプト
#
# 実行環境:
#   - GitHub Actions (.github/workflows/daily_refresh.yml から呼ばれる)
#   - 手動実行 (cd ~/projects/ark-analytics && ./scripts/daily_refresh.sh)
#
# 環境変数:
#   - PROJECT_ID         (省略時 "ark-hd-analytics")
#   - LARK_WEBHOOK_URL   (失敗時の通知用・省略時はskip)

set -e
PROJECT="${PROJECT_ID:-ark-hd-analytics}"
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
    if [ -n "${LARK_WEBHOOK_URL:-}" ]; then
        local payload
        payload=$(printf '{"msg_type":"text","content":{"text":"❌ ark-analytics daily_refresh FAILED\\nstep: %s\\nproject: %s\\ntime: %s"}}' "$label" "$PROJECT" "$DATE")
        curl -s -X POST -H "Content-Type: application/json" -d "$payload" "$LARK_WEBHOOK_URL" >/dev/null || true
    fi
}

run_sql() {
    local label=$1
    local file=$2
    echo "[$DATE] $label 開始..." | tee -a "$LOG"
    if bq query --project_id="$PROJECT" --use_legacy_sql=false < "$file" >> "$LOG" 2>&1; then
        echo "[$DATE] $label 完了" | tee -a "$LOG"
    else
        echo "[$DATE] ERROR: $label 失敗" | tee -a "$LOG"
        notify_lark_failure "$label"
        exit 1
    fi
}

# staging（VIEW更新不要・stg_sessionsテーブルのみ）
run_sql "staging.stg_sessions"            "$SQL_DIR/staging/stg_sessions.sql"

# marts（VIEW→TABLE順）
run_sql "marts.daily_kpi_summary"         "$SQL_DIR/marts/daily_kpi_summary.sql"
run_sql "marts.conversion_funnel_daily"   "$SQL_DIR/marts/conversion_funnel_daily.sql"
run_sql "marts.channel_kpi_monthly"       "$SQL_DIR/marts/channel_kpi_monthly.sql"
run_sql "marts.page_performance"          "$SQL_DIR/marts/page_performance.sql"

echo "[$DATE] === 日次更新完了 ===" | tee -a "$LOG"
