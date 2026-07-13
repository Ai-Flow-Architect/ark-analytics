"""
AIチャットの👍👎フィードバックを ops.chat_feedback に記録する。
best-effort: 書き込みに失敗しても例外を投げない（UIを絶対に止めない）。
marts(分析データ)には触れない・独立した ops データセットのみ。
"""
from __future__ import annotations

from datetime import datetime, timezone

DATASET = "ops"
TABLE = "chat_feedback"


def build_row(*, verdict: str, question: str | None, answer: str | None,
              model: str | None, session_id: str | None,
              now: datetime | None = None) -> dict:
    """記録する1行を組み立てる（純関数・テスト可能）。"""
    ts = (now or datetime.now(timezone.utc)).isoformat()
    return {
        "inserted_at": ts,
        "verdict": verdict,                        # 'up' / 'down'
        "question": (question or "")[:2000],
        "answer": (answer or "")[:5000],
        "model": model or "",
        "session_id": session_id or "",
    }


def record_feedback(bq_client, project_id: str, *, verdict: str,
                    question: str | None = None, answer: str | None = None,
                    model: str | None = None, session_id: str | None = None) -> bool:
    """1行をBQへ挿入。成功=True。失敗・例外は握りつぶしてFalse（UIは止めない）。"""
    try:
        row = build_row(verdict=verdict, question=question, answer=answer,
                        model=model, session_id=session_id)
        table_id = f"{project_id}.{DATASET}.{TABLE}"
        errors = bq_client.insert_rows_json(table_id, [row])
        return not errors
    except Exception:
        return False
