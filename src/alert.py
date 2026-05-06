"""
alert.py
失敗時のLark通知（自動配信が空振りしたケースを五十嵐様が即時検知できるようにする）
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

import requests


def notify_failure(
    job: str,
    reason: str,
    context: dict[str, Any] | None = None,
) -> bool:
    """
    Lark Webhookでジョブ失敗を通知する。

    Args:
        job: 失敗したジョブ名（例: "weekly_report" / "monthly_report" / "daily_refresh"）
        reason: 失敗理由（例: "marts.daily_kpi_summary が空"）
        context: 補足情報（target_month, frequency等）

    Returns:
        通知成功時 True、Webhook URL未設定 or 失敗時 False
    """
    webhook_url = os.environ.get("LARK_WEBHOOK_URL", "")
    if not webhook_url:
        # 環境変数未設定時は標準出力にだけ出して False を返す（テスト/ローカル想定）
        print(f"[alert] LARK_WEBHOOK_URL 未設定のため通知スキップ: {job} / {reason}")
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
        f"対応: GitHub Actions ログを確認してください"
    )

    payload = {"msg_type": "text", "content": {"text": text}}

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        print(f"[alert] Lark通知送信完了: {job}")
        return True
    except Exception as e:
        print(f"[alert] Lark通知送信失敗: {e}")
        return False
