"""
notify_mail.py
GitHub Actions composite action `notify-failure` から呼ばれる SMTP 送信スクリプト。
依存ゼロ（標準ライブラリのみ）でサプライチェーン攻撃面を最小化する。

環境変数:
  SMTP_USER, SMTP_PASS         : Gmail App Password など
  ALERT_RECIPIENTS              : カンマ区切り宛先
  WORKFLOW_NAME, RUN_URL, FAILED_STEP, SEVERITY, COMMIT_SHA, ACTOR : 通知ペイロード
"""
from __future__ import annotations
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage


def main() -> int:
    user = os.environ.get("SMTP_USER", "").strip()
    pw   = os.environ.get("SMTP_PASS", "").strip()
    to   = [a.strip() for a in os.environ.get("ALERT_RECIPIENTS", "").split(",") if a.strip()]

    if not (user and pw and to):
        print("[notify_mail] SMTP_USER / SMTP_PASS / ALERT_RECIPIENTS のいずれか未設定。スキップ。")
        return 0  # continue-on-error と整合（失敗扱いにしない）

    wf  = os.environ.get("WORKFLOW_NAME", "unknown")
    url = os.environ.get("RUN_URL", "")
    step = os.environ.get("FAILED_STEP", "unknown")
    sev = os.environ.get("SEVERITY", "critical")
    sha = os.environ.get("COMMIT_SHA", "")
    actor = os.environ.get("ACTOR", "")

    msg = EmailMessage()
    msg["Subject"] = f"[AIフローアーキテクト][ALERT] {wf} 失敗 (sev={sev})"
    msg["From"] = f"AIフローアーキテクト 監視Bot <{user}>"
    msg["To"] = ", ".join(to)
    msg.set_content(
        "ark-analytics 監視冗長化システムからの通知です。\n\n"
        f"Workflow   : {wf}\n"
        f"Failed step: {step}\n"
        f"Severity   : {sev}\n"
        f"Commit SHA : {sha}\n"
        f"Actor      : {actor}\n"
        f"Run URL    : {url}\n\n"
        "復旧手順:\n"
        "  1) Run URL のログを確認\n"
        "  2) 24h以内なら GitHub Issue (label: monitoring-alert) にも記録あり\n"
        "  3) 修正後、該当Issueを手動closeしてください\n\n"
        "-- AIフローアーキテクト 監視冗長化システム"
    )

    ctx = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=20) as s:
            s.login(user, pw)
            s.send_message(msg)
        print(f"[notify_mail] sent to {len(to)} recipient(s)")
        return 0
    except Exception as e:
        # 機密(pw)をstderrに混ぜないため repr せずクラス名のみ
        print(f"[notify_mail] SMTP送信失敗: {type(e).__name__}", file=sys.stderr)
        return 0  # composite action 全体は止めない（他チェーン優先）


if __name__ == "__main__":
    sys.exit(main())
