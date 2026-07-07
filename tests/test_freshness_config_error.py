"""
鮮度チェックの「プロジェクトID未解決(=設定不備)」時の通知挙動テスト

2026-07-06 インシデント由来：
ローカル(WSL)で `main.py --report-type monthly` を手動実行した際、
ARK_GCP_PROJECT_ID が env に無く get_project_id() が RuntimeError を送出。
check_data_freshness.py がこれを notify_failure で Lark に通知し、
運用アラートチャンネルへ誤ページングした（本番=GHAは正常・データ障害ではない）。

恒久修正：設定不備(rc=2)の Lark通知は CI(GITHUB_ACTIONS)実行時のみに限定する。
  - CI          : Secret欠落など真の異常 → notify_failure を呼ぶ
  - ローカル実行: 開発者の env未export → stderr出力のみ・通知しない
どちらも exit code 2 は維持（fail-fast）。
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import scripts.check_data_freshness as cdf  # noqa: E402


def _force_project_id_unresolved(monkeypatch):
    """get_project_id() を必ず RuntimeError にする。"""
    def _raise():
        raise RuntimeError(
            "GCPプロジェクトIDが解決できません。環境変数 ARK_GCP_PROJECT_ID を設定してください"
        )
    monkeypatch.setattr(cdf, "get_project_id", _raise)


def test_config_error_local_does_not_notify(monkeypatch, capsys):
    """ローカル実行(GITHUB_ACTIONS未設定)は Lark通知せず exit 2。"""
    _force_project_id_unresolved(monkeypatch)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    called = {"notify": False}
    monkeypatch.setattr(
        cdf, "notify_failure",
        lambda **kw: called.__setitem__("notify", True),
    )
    monkeypatch.setattr(sys, "argv", ["check_data_freshness.py", "--source", "unit_test"])

    rc = cdf.main()

    assert rc == 2
    assert called["notify"] is False, "ローカルでは運用アラートを鳴らしてはいけない"
    assert "ARK_GCP_PROJECT_ID" in capsys.readouterr().err


def test_config_error_in_ci_notifies(monkeypatch):
    """CI(GITHUB_ACTIONS=true)は Secret欠落の真の異常として Lark通知し exit 2。"""
    _force_project_id_unresolved(monkeypatch)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    called = {"notify": False, "job": None}

    def _fake_notify(**kw):
        called["notify"] = True
        called["job"] = kw.get("job")

    monkeypatch.setattr(cdf, "notify_failure", _fake_notify)
    monkeypatch.setattr(sys, "argv", ["check_data_freshness.py", "--source", "unit_test"])

    rc = cdf.main()

    assert rc == 2
    assert called["notify"] is True, "CIでは真のSecret欠落として通知する"
    assert called["job"] == "data_freshness_check"
