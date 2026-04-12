#!/bin/bash
# daily_refresh.sh
# ark-analytics BQテーブル日次自動更新スクリプト
# cron設定例: 0 4 * * * /home/kosuke_igarashi/projects/ark-analytics/scripts/daily_refresh.sh

set -e
PROJECT="ark-hd-analytics"
LOG_DIR="/home/kosuke_igarashi/projects/ark-analytics/logs"
SQL_DIR="/home/kosuke_igarashi/projects/ark-analytics/sql"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/refresh_$(date '+%Y%m%d').log"

echo "[$DATE] === ark-analytics 日次更新開始 ===" >> "$LOG"

run_sql() {
    local label=$1
    local file=$2
    echo "[$DATE] $label 開始..." >> "$LOG"
    if bq query --project_id="$PROJECT" --use_legacy_sql=false < "$file" >> "$LOG" 2>&1; then
        echo "[$DATE] $label 完了" >> "$LOG"
    else
        echo "[$DATE] ERROR: $label 失敗" >> "$LOG"
        exit 1
    fi
}

# staging（VIEW更新不要・stg_sessionsテーブルのみ）
run_sql "staging.stg_sessions"    "$SQL_DIR/staging/stg_sessions.sql"

# marts（VIEW→TABLE順）
run_sql "marts.daily_kpi_summary"     "$SQL_DIR/marts/daily_kpi_summary.sql"
run_sql "marts.conversion_funnel_daily" "$SQL_DIR/marts/conversion_funnel_daily.sql"
run_sql "marts.channel_kpi_monthly"   "$SQL_DIR/marts/channel_kpi_monthly.sql"
run_sql "marts.page_performance"      "$SQL_DIR/marts/page_performance.sql"

echo "[$DATE] === 日次更新完了 ===" >> "$LOG"
echo "[$DATE] 完了" >> "$LOG"
