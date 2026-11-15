"""
alert.py
Lark Bot 経由でジョブ失敗を通知する（既存lark_notify_claudecode.pyと同方式）。

呼び出し方:
  - Pythonから: from src.alert import notify_failure; notify_failure(job, reason, context)
  - シェルから: python3 src/alert.py <job> <reason> [key1=value1 key2=value2 ...]

同じ件の二重通知を止める（2026-11-15）:
  notify_failure(..., dedupe_key="<件を表す文字列>") を渡すと、BigQuery の
  `<project>.ops.alert_state` に「通知済み」を記録し、同じ key は2回目から送らない。
  復旧したら clear_incidents("<key の頭>") で記録を消す＝次に同じ事が起きたらまた1回知らせる。
  記録が読めない・書けない時は「送る」側に倒す（障害を黙らせない）。

環境変数（GitHub Secrets / .bashrc）:
  LARK_APP_ID        必須
  LARK_APP_SECRET    必須
  LARK_CHAT_ID       省略時 ClaudeCode-Bot (oc_82797e277db9f5e20d3bfb18d0e0534f)
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.request
from datetime import datetime
from typing import Any

DEFAULT_CHAT_ID = "oc_82797e277db9f5e20d3bfb18d0e0534f"  # ClaudeCode-Bot
STATE_TABLE = "ops.alert_state"


def _get_tenant_token(app_id: str, app_secret: str, ctx: ssl.SSLContext) -> str | None:
    payload = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(
        "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            data = json.loads(r.read())
        return data.get("tenant_access_token")
    except Exception as e:
        print(f"[alert] tenant_access_token 取得失敗: {e}")
        return None


# ── 通知済みの記録（BigQuery ops.alert_state）────────────────────────────
def _state_client():
    """(client, table_id) を返す。用意できなければ (None, None)＝記録なしで送る側に倒す。"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from src._config_loader import get_project_id, make_bq_client
        project_id = get_project_id()
        client = make_bq_client(project_id)
        table_id = f"{project_id}.{STATE_TABLE}"
        client.query(
            f"CREATE TABLE IF NOT EXISTS `{table_id}` ("
            "alert_key STRING, first_seen TIMESTAMP, last_seen TIMESTAMP, seen_count INT64)"
        ).result()
        return client, table_id
    except Exception as e:  # noqa: BLE001
        print(f"[alert] 通知済みの記録を使えません（送る側に倒します）: {e}")
        return None, None


def _already_notified(client, table_id: str, key: str) -> bool:
    from google.cloud import bigquery
    cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("k", "STRING", key)])
    rows = list(client.query(
        f"SELECT seen_count FROM `{table_id}` WHERE alert_key = @k LIMIT 1", job_config=cfg).result())
    return bool(rows)


def _record_seen(client, table_id: str, key: str) -> None:
    from google.cloud import bigquery
    cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("k", "STRING", key)])
    client.query(
        f"MERGE `{table_id}` t USING (SELECT @k AS alert_key) s ON t.alert_key = s.alert_key "
        "WHEN MATCHED THEN UPDATE SET last_seen = CURRENT_TIMESTAMP(), seen_count = t.seen_count + 1 "
        "WHEN NOT MATCHED THEN INSERT (alert_key, first_seen, last_seen, seen_count) "
        "VALUES (@k, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), 1)",
        job_config=cfg,
    ).result()


def clear_incidents(prefix: str) -> None:
    """復旧した時に呼ぶ。prefix で始まる記録を消す（次の発生でまた1回知らせるため）。失敗しても止めない。"""
    client, table_id = _state_client()
    if client is None:
        return
    try:
        from google.cloud import bigquery
        cfg = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("p", "STRING", prefix)])
        client.query(f"DELETE FROM `{table_id}` WHERE STARTS_WITH(alert_key, @p)", job_config=cfg).result()
    except Exception as e:  # noqa: BLE001
        print(f"[alert] 通知済みの記録を消せませんでした（次回の通知に影響なし）: {e}")


def notify_failure(
    job: str,
    reason: str,
    context: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> bool:
    if dedupe_key:
        client, table_id = _state_client()
        if client is not None:
            try:
                seen = _already_notified(client, table_id, dedupe_key)
                _record_seen(client, table_id, dedupe_key)
                if seen:
                    print(f"[alert] 同じ件は通知済みのため送りません: {dedupe_key}")
                    return True
            except Exception as e:  # noqa: BLE001
                print(f"[alert] 通知済みの確認に失敗（送る側に倒します）: {e}")

    app_id = os.environ.get("LARK_APP_ID", "")
    app_secret = os.environ.get("LARK_APP_SECRET", "")
    chat_id = os.environ.get("LARK_CHAT_ID", DEFAULT_CHAT_ID)

    if not app_id or not app_secret:
        print(f"[alert] LARK_APP_ID/SECRET 未設定のため通知スキップ: {job} / {reason}")
        return False

    ctx = ssl.create_default_context()
    token = _get_tenant_token(app_id, app_secret, ctx)
    if not token:
        return False

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ctx_lines = ""
    if context:
        ctx_lines = "\n" + "\n".join(f"  - {k}: {v}" for k, v in context.items())
    once_note = "\n（同じ件はこの1回だけ通知します。復旧後に再発したら、また通知します）" if dedupe_key else ""

    text = (
        f"❌ ark-analytics ジョブ失敗\n"
        f"━━━━━━━━━━━━━━\n"
        f"job: {job}\n"
        f"reason: {reason}\n"
        f"time: {timestamp}{ctx_lines}\n"
        f"━━━━━━━━━━━━━━\n"
        f"GitHub Actions ログ: https://github.com/Ai-Flow-Architect/ark-analytics/actions"
        f"{once_note}"
    )

    payload = json.dumps({
        "receive_id": chat_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}),
    }).encode()

    req = urllib.request.Request(
        "https://open.larksuite.com/open-apis/im/v1/messages?receive_id_type=chat_id",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            result = json.loads(r.read())
        if result.get("code") == 0:
            print(f"[alert] Lark通知送信完了: {job}")
            return True
        print(f"[alert] Lark送信失敗: {result.get('msg')}")
        return False
    except Exception as e:
        print(f"[alert] Lark送信例外: {e}")
        return False


def _cli() -> int:
    if len(sys.argv) < 3:
        print("Usage: python3 src/alert.py <job> <reason> [key=value ...]", file=sys.stderr)
        return 2
    job = sys.argv[1]
    reason = sys.argv[2]
    context: dict[str, Any] = {}
    for arg in sys.argv[3:]:
        if "=" in arg:
            k, v = arg.split("=", 1)
            context[k] = v
    ok = notify_failure(job=job, reason=reason, context=context or None)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_cli())
