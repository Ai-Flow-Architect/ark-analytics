"""同じ件の二重通知を止める（2026-11-15）。

- 同じ dedupe_key の2回目は Lark へ送らない
- 通知済みの記録が使えない時は送る（障害を黙らせない）
- dedupe_key なしの呼び出しは従来どおり毎回送る
外部（BigQuery・Lark）には一切つながない。
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import src.alert as alert  # noqa: E402


class _FakeState:
    def __init__(self):
        self.keys = set()


def _wire(monkeypatch, state, available=True):
    sent = []
    monkeypatch.setattr(alert, "_state_client", lambda: ("c", "t") if available else (None, None))
    monkeypatch.setattr(alert, "_already_notified", lambda c, t, k: k in state.keys)
    monkeypatch.setattr(alert, "_record_seen", lambda c, t, k: state.keys.add(k))
    monkeypatch.setattr(alert, "_get_tenant_token", lambda *a: "tok")
    monkeypatch.setenv("LARK_APP_ID", "x")
    monkeypatch.setenv("LARK_APP_SECRET", "y")

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"code": 0}'

    def _urlopen(req, **kw):
        sent.append(req)
        return _Resp()

    monkeypatch.setattr(alert.urllib.request, "urlopen", _urlopen)
    return sent


def test_same_key_is_sent_once(monkeypatch):
    state = _FakeState()
    sent = _wire(monkeypatch, state)
    for _ in range(3):
        assert alert.notify_failure("data_freshness_check", "古い", dedupe_key="k:2026-11-11")
    assert len(sent) == 1


def test_new_key_is_sent_again(monkeypatch):
    state = _FakeState()
    sent = _wire(monkeypatch, state)
    alert.notify_failure("j", "r", dedupe_key="k:2026-11-11")
    alert.notify_failure("j", "r", dedupe_key="k:2026-11-12")
    assert len(sent) == 2


def test_state_unavailable_fails_open(monkeypatch):
    state = _FakeState()
    sent = _wire(monkeypatch, state, available=False)
    alert.notify_failure("j", "r", dedupe_key="k")
    alert.notify_failure("j", "r", dedupe_key="k")
    assert len(sent) == 2


def test_no_key_keeps_old_behavior(monkeypatch):
    state = _FakeState()
    sent = _wire(monkeypatch, state)
    alert.notify_failure("j", "r")
    alert.notify_failure("j", "r")
    assert len(sent) == 2
