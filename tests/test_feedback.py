"""feedback モジュールのテスト（BQには接続しない・フェイククライアント）。"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from feedback import build_row, record_feedback  # noqa: E402


def test_build_row_basic():
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    row = build_row(verdict="up", question="Q", answer="A",
                    model="gpt-4o", session_id="s1", now=now)
    assert row["verdict"] == "up"
    assert row["question"] == "Q"
    assert row["answer"] == "A"
    assert row["model"] == "gpt-4o"
    assert row["session_id"] == "s1"
    assert row["inserted_at"] == "2026-07-13T12:00:00+00:00"


def test_build_row_truncates_and_defaults():
    row = build_row(verdict="down", question="x" * 5000, answer="y" * 9000,
                    model=None, session_id=None)
    assert len(row["question"]) == 2000
    assert len(row["answer"]) == 5000
    assert row["model"] == ""
    assert row["session_id"] == ""


class _FakeBQOk:
    def insert_rows_json(self, table_id, rows):
        assert table_id.endswith(".ops.chat_feedback")
        assert len(rows) == 1
        return []  # BQ: 空リスト=成功


class _FakeBQErr:
    def insert_rows_json(self, table_id, rows):
        return [{"index": 0, "errors": [{"reason": "boom"}]}]


class _FakeBQRaise:
    def insert_rows_json(self, table_id, rows):
        raise RuntimeError("network down")


def test_record_feedback_success():
    assert record_feedback(_FakeBQOk(), "proj", verdict="up", question="q", answer="a") is True


def test_record_feedback_insert_error_returns_false():
    assert record_feedback(_FakeBQErr(), "proj", verdict="down") is False


def test_record_feedback_never_raises():
    # 例外は握りつぶしてFalse（UIを止めない契約）
    assert record_feedback(_FakeBQRaise(), "proj", verdict="up") is False
