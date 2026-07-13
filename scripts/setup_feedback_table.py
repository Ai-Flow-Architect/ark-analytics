"""
AIチャットの👍👎フィードバック保存先を用意する（1回だけ実行）。
marts(分析データ)には一切触れず、独立した ops データセットに chat_feedback を作る。
冪等: 既存なら何もしない（CREATE IF NOT EXISTS 相当）。

実行: GOOGLE_APPLICATION_CREDENTIALS を SA鍵にして
      python3 scripts/setup_feedback_table.py
"""
from __future__ import annotations

import os
import sys

from google.cloud import bigquery

DATASET = "ops"
TABLE = "chat_feedback"
LOCATION = "asia-northeast1"

SCHEMA = [
    bigquery.SchemaField("inserted_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("verdict", "STRING", mode="REQUIRED"),      # 'up' / 'down'
    bigquery.SchemaField("question", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("answer", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("model", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("session_id", "STRING", mode="NULLABLE"),
]


def main() -> int:
    client = bigquery.Client()
    project = client.project

    ds_id = f"{project}.{DATASET}"
    dataset = bigquery.Dataset(ds_id)
    dataset.location = LOCATION
    client.create_dataset(dataset, exists_ok=True)
    print(f"dataset ready: {ds_id} ({LOCATION})")

    tbl_id = f"{project}.{DATASET}.{TABLE}"
    table = bigquery.Table(tbl_id, schema=SCHEMA)
    client.create_table(table, exists_ok=True)
    print(f"table ready:   {tbl_id}")
    return 0


if __name__ == "__main__":
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        print("ERROR: GOOGLE_APPLICATION_CREDENTIALS を SA鍵に設定してください", file=sys.stderr)
        sys.exit(2)
    sys.exit(main())
