"""
delivery.py
レポートをGmail・Google Drive・Larkに配信するモジュール
"""
from __future__ import annotations

import io
import json
import os
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
import yaml


def _load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class ReportDelivery:
    """レポート配信クラス（Gmail / Google Drive / Lark）"""

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or _load_config()

    # ─── Gmail 送信 ─────────────────────────────────────────
    def send_gmail(
        self,
        month: str,
        html_body: str,
        to_email: str | None = None,
        cc_emails: list[str] | None = None,
    ) -> bool:
        """
        Gmailでレポートを送信する
        GMAIL_ADDRESS / GMAIL_APP_PASSWORD を環境変数に設定する
        （通常パスワードではなくGoogleアカウントの「アプリパスワード」を使用）
        """
        sender = os.environ.get("GMAIL_ADDRESS", "")
        app_password = os.environ.get("GMAIL_APP_PASSWORD", "")
        if not sender or not app_password:
            print("⚠️  GMAIL_ADDRESS / GMAIL_APP_PASSWORD が未設定です")
            return False

        recipient = to_email or os.environ.get("ARK_CLIENT_EMAIL", "")
        if not recipient:
            print("⚠️  送信先メールアドレスが未設定です")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"【自動レポート】{month} Webサイト分析 | ark-hd.co.jp"
        msg["From"] = sender
        msg["To"] = recipient
        if cc_emails:
            msg["Cc"] = ", ".join(cc_emails)

        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                smtp.login(sender, app_password)
                all_recipients = [recipient] + (cc_emails or [])
                smtp.sendmail(sender, all_recipients, msg.as_string())
            print(f"✅ Gmail送信完了 → {recipient}")
            return True
        except Exception as e:
            print(f"❌ Gmail送信失敗: {e}")
            return False

    # ─── Google Drive 保存 ──────────────────────────────────
    def save_to_drive(self, month: str, markdown_content: str) -> str | None:
        """
        MarkdownレポートをGoogle Driveに保存する
        GOOGLE_ACCESS_TOKEN または サービスアカウントキー を使用
        """
        access_token = os.environ.get("GOOGLE_ACCESS_TOKEN", "")
        folder_id = os.environ.get("ARK_DRIVE_FOLDER_ID", "")

        if not access_token:
            print("⚠️  GOOGLE_ACCESS_TOKEN が未設定です。Drive保存をスキップします")
            return None

        file_name = f"ark-analytics_{month}_report.md"
        metadata = {
            "name": file_name,
            "mimeType": "application/vnd.google-apps.document",
            "parents": [folder_id] if folder_id else [],
        }

        files_data = [
            ("metadata", ("metadata.json", json.dumps(metadata), "application/json")),
            ("media", (file_name, markdown_content.encode("utf-8"), "text/plain")),
        ]

        try:
            resp = requests.post(
                "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                headers={"Authorization": f"Bearer {access_token}"},
                files=files_data,
                timeout=30,
            )
            resp.raise_for_status()
            file_id = resp.json().get("id", "")
            url = f"https://docs.google.com/document/d/{file_id}"
            print(f"✅ Drive保存完了 → {url}")
            return url
        except Exception as e:
            print(f"❌ Drive保存失敗: {e}")
            return None

    # ─── Lark通知 ────────────────────────────────────────────
    def notify_lark(
        self,
        month: str,
        kpi: dict,
        drive_url: str | None = None,
    ) -> bool:
        """
        Lark Webhookでレポート完了通知を送信する
        LARK_WEBHOOK_URL を環境変数に設定する
        """
        webhook_url = os.environ.get(
            "LARK_WEBHOOK_URL",
            self.config["report"].get("lark_webhook", ""),
        )
        if not webhook_url:
            print("⚠️  LARK_WEBHOOK_URL が未設定です")
            return False

        sessions = int(kpi.get("sessions", 0))
        inquiries = int(kpi.get("inquiries", 0))
        sessions_rate = sessions / 5000 * 100
        inquiry_rate = inquiries / 9 * 100

        drive_text = f"\n📄 レポートURL: {drive_url}" if drive_url else ""

        payload = {
            "msg_type": "text",
            "content": {
                "text": (
                    f"📊 {month} 月次レポート自動生成完了\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"セッション: {sessions:,} ({sessions_rate:.1f}% / 目標5,000)\n"
                    f"お問い合わせ: {inquiries}件 ({inquiry_rate:.1f}% / 目標9件)\n"
                    f"資料DL: {int(kpi.get('downloads', 0))}件\n"
                    f"CVR: {round(float(kpi.get('contact_cr', 0)) * 100, 2)}%"
                    f"{drive_text}"
                )
            },
        }

        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            resp.raise_for_status()
            print("✅ Lark通知完了")
            return True
        except Exception as e:
            print(f"❌ Lark通知失敗: {e}")
            return False
