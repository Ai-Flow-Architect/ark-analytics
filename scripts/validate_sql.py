"""
validate_sql.py — BigQuery SQL ファイルの構文・参照・権限を機械検証する

daily_refresh.sh と同じプレースホルダ展開（__ARK_PROJECT__ / __ARK_GA4_PROPID__）を
行ったうえで、各 SQL ファイルを `bq query --dry_run` に通す。dry_run は課金ゼロで
構文・参照テーブル存在・権限を検証できるため、本番へ副作用を出さずに
「このSQLは実行可能か」を機械判定できる（DoD: 本番副作用ありは dry-run で検証）。

使い方:
  # dry-run のみ（既定・課金ゼロ・本番無副作用）
  ARK_GCP_PROJECT_ID=... ARK_GA4_PROPERTY_ID=... \
  GOOGLE_APPLICATION_CREDENTIALS=/path/sa.json \
  python3 scripts/validate_sql.py sql/marts/foo.sql sql/reports/bar.sql

  # 実デプロイ（CREATE OR REPLACE を実際に流す。依存順に並べること）
  ... python3 scripts/validate_sql.py --execute sql/...

環境変数:
  ARK_GCP_PROJECT_ID            必須（GCPプロジェクトID）
  ARK_GA4_PROPERTY_ID           必須（GA4プロパティID。analytics_<propid> 展開に使用）
  GOOGLE_APPLICATION_CREDENTIALS 必須（SA鍵JSON。bq の認証）
  ARK_BQ_LOCATION               任意（既定 asia-northeast1）

終了コード:
  0: 全ファイル成功
  1: 1件以上失敗
  2: 設定不備（環境変数・bqバイナリ不在 等）
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys


def _resolve_bq() -> str | None:
    """bq バイナリのパスを解決する。"""
    for cand in (
        os.path.expanduser("~/google-cloud-sdk/bin/bq"),
        shutil.which("bq") or "",
    ):
        if cand and os.path.exists(cand):
            return cand
    return None


def _render(sql: str, project: str, propid: str) -> str:
    return sql.replace("__ARK_PROJECT__", project).replace("__ARK_GA4_PROPID__", propid)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", help="検証する .sql ファイル（依存順）")
    parser.add_argument("--execute", action="store_true",
                        help="dry_run せず実際に CREATE OR REPLACE を流す")
    args = parser.parse_args()

    project = os.environ.get("ARK_GCP_PROJECT_ID", "").strip()
    propid = os.environ.get("ARK_GA4_PROPERTY_ID", "").strip()
    location = os.environ.get("ARK_BQ_LOCATION", "asia-northeast1").strip()
    creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()

    if not project or not propid:
        print("[FATAL] ARK_GCP_PROJECT_ID / ARK_GA4_PROPERTY_ID を環境変数で指定してください", file=sys.stderr)
        return 2
    if not creds or not os.path.exists(creds):
        print("[FATAL] GOOGLE_APPLICATION_CREDENTIALS が未設定または不在です", file=sys.stderr)
        return 2

    bq = _resolve_bq()
    if not bq:
        print("[FATAL] bq バイナリが見つかりません（~/google-cloud-sdk/bin/bq）", file=sys.stderr)
        return 2

    base_cmd = [bq, "query", "--use_legacy_sql=false", f"--location={location}",
                f"--project_id={project}"]
    if not args.execute:
        base_cmd.append("--dry_run")

    mode = "EXECUTE(本番反映)" if args.execute else "DRY-RUN(課金ゼロ検証)"
    print(f"=== validate_sql [{mode}] project={project} files={len(args.files)} ===")

    failures = 0
    for path in args.files:
        if not os.path.exists(path):
            print(f"  [FAIL] {path} : ファイルが存在しません")
            failures += 1
            continue
        with open(path, encoding="utf-8") as f:
            rendered = _render(f.read(), project, propid)
        proc = subprocess.run(
            base_cmd,
            input=rendered,
            text=True,
            capture_output=True,
        )
        if proc.returncode == 0:
            print(f"  [OK]   {path}")
        else:
            failures += 1
            err = (proc.stderr or proc.stdout or "").strip()
            print(f"  [FAIL] {path}\n         {err[:1500]}")

    print(f"=== 結果: {len(args.files) - failures}/{len(args.files)} OK / 失敗 {failures} ===")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
