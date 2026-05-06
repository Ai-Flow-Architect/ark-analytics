"""
alert.py
Lark Bot 経由でジョブ失敗を通知する（既存lark_notify_claudecode.pyと同方式）。

呼び出し方:
  - Pythonから: from src.alert import notify_failure; notify_failure(job, reason, context)
  - シェルから: python3 src/alert.py <job> <reason> [key1=value1 key2=value2 ...]

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


def notify_failure(
    job: str,
    reason: str,
    context: dict[str, Any] | None = None,
) -> bool:
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

    text = (
        f"❌ ark-analytics ジョブ失敗\n"
        f"━━━━━━━━━━━━━━\n"
        f"job: {job}\n"
        f"reason: {reason}\n"
        f"time: {timestamp}{ctx_lines}\n"
        f"━━━━━━━━━━━━━━\n"
        f"GitHub Actions ログ: https://github.com/Ai-Flow-Architect/ark-analytics/actions"
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
