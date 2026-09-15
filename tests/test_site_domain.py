"""
レポートの件名・本文に出すサイト名（ARK_SITE_DOMAIN）のテスト

2026-09-11 インシデント由来：
公開リポ化の伏字 `example.invalid` が件名（src/delivery.py）と本文（src/report_formatter.py）に
直書きされ、客様宛の週次・月次メールに 6/30〜9/7 で13通そのまま載っていた。
→ サイト名は Secrets の ARK_SITE_DOMAIN から読み、未設定・伏字なら表示しない。

実行:
    pytest tests/test_site_domain.py -v
"""
from __future__ import annotations

import email
import os
import sys
from email.header import decode_header, make_header

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src import delivery as D  # noqa: E402
from src._config_loader import get_site_domain  # noqa: E402
from src.report_formatter import ReportFormatter  # noqa: E402

DOMAIN = "client-site.test"  # テスト用（実在しない .test ドメイン）
KPI = {"sessions": 1385, "inquiries": 5, "downloads": 13, "inquiry_cvr": 0.0036,
       "period_start": "2026-08-01", "period_end": "2026-08-31"}


def test_domain_is_read_from_env(monkeypatch):
    monkeypatch.setenv("ARK_SITE_DOMAIN", f"  {DOMAIN} ")
    assert get_site_domain() == DOMAIN


@pytest.mark.parametrize("value", ["", "   ", "example.invalid", "foo.invalid",
                                   "REDACTED-SITE", "www.example.com", "<site>"])
def test_empty_or_placeholder_is_hidden(monkeypatch, value):
    monkeypatch.setenv("ARK_SITE_DOMAIN", value)
    assert get_site_domain() == ""


def test_unset_is_hidden(monkeypatch):
    monkeypatch.delenv("ARK_SITE_DOMAIN", raising=False)
    assert get_site_domain() == ""


def _render(monkeypatch, domain):
    if domain is None:
        monkeypatch.delenv("ARK_SITE_DOMAIN", raising=False)
    else:
        monkeypatch.setenv("ARK_SITE_DOMAIN", domain)
    f = ReportFormatter()
    return f.to_html("2026-08", KPI, "総評", "詳細"), f.to_markdown("2026-08", KPI, "総評", "詳細")


def test_body_shows_domain_when_set(monkeypatch):
    html, md = _render(monkeypatch, DOMAIN)
    assert f"{DOMAIN} | データ取得日時" in html
    assert f"{DOMAIN} | データ取得日時" in md
    assert "example.invalid" not in html + md


def test_body_without_domain_has_no_placeholder(monkeypatch):
    html, md = _render(monkeypatch, None)
    assert "データ取得日時" in html and "データ取得日時" in md
    assert "example.invalid" not in html + md
    assert "| データ取得日時" not in html + md  # 区切りだけ残らない


def test_body_with_placeholder_env_hides_it(monkeypatch):
    html, md = _render(monkeypatch, "example.invalid")
    assert "example.invalid" not in html + md


class _FakeSMTP:
    """実際には送信しない（宛先・件名を記録するだけ）。"""
    sent: list = []

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, *a):
        pass

    def sendmail(self, sender, recipients, raw):
        _FakeSMTP.sent.append((sender, recipients, raw))


def _subject(monkeypatch, domain):
    _FakeSMTP.sent = []
    monkeypatch.setattr(D.smtplib, "SMTP_SSL", _FakeSMTP)
    monkeypatch.setenv("GMAIL_ADDRESS", "sender@client-site.test")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "dummy")
    monkeypatch.setenv("ARK_CLIENT_EMAIL", "to@client-site.test")
    if domain is None:
        monkeypatch.delenv("ARK_SITE_DOMAIN", raising=False)
    else:
        monkeypatch.setenv("ARK_SITE_DOMAIN", domain)
    assert D.ReportDelivery().send_gmail("2026-08", "<p>body</p>") is True
    assert len(_FakeSMTP.sent) == 1
    msg = email.message_from_string(_FakeSMTP.sent[0][2])
    return str(make_header(decode_header(msg["Subject"])))


def test_subject_shows_domain_when_set(monkeypatch):
    assert _subject(monkeypatch, DOMAIN) == f"【自動レポート】2026-08 Webサイト分析 | {DOMAIN}"


def test_subject_without_domain_has_no_placeholder(monkeypatch):
    assert _subject(monkeypatch, None) == "【自動レポート】2026-08 Webサイト分析"


def test_subject_with_placeholder_env_hides_it(monkeypatch):
    assert "example.invalid" not in _subject(monkeypatch, "example.invalid")
