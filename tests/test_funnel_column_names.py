"""
回帰防止テスト: marts.conversion_funnel_daily の列名ドリフト再発防止。

背景(2026-05-22発見):
  SQLビュー conversion_funnel_daily が step2→step2b 等に再構成された際、
  Python側のクエリが旧列名(step2_service_view 等)を参照したままになり、
  BigQuery BadRequest 400 (Unrecognized name) でファネル系機能が全滅していた。
  app.py / natural_language_qa.py / priority_scorer.py で発生。

正しい列名: step2b_service_view / step1_to_2b_rate / step2b_to_3_rate
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel: str) -> str:
    path = os.path.join(ROOT, rel)
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def test_funnel_no_buggy_source_columns():
    """削除済み列名のソース参照パターンが残っていないこと(BadRequest 400の原因)。

    ※ alias出力名(... AS step2_service_view)・dictキー("step2_service_view")は
      正当なので、ソース参照になる固有パターンのみを検出する。
    """
    bad_patterns = {
        "app.py": ["step1_sessions, step2_service_view"],
        "src/natural_language_qa.py": ["step1_sessions, step2_service_view"],
        "src/priority_scorer.py": [
            "AVG(step2_service_view)",
            "AVG(step1_to_2_rate)",
            "AVG(step2_to_3_rate)",
        ],
    }
    offenders = []
    for rel, patterns in bad_patterns.items():
        src = _read(rel)
        for pat in patterns:
            if pat in src:
                offenders.append(f"{rel}: 旧列名のソース参照 '{pat}'")
    assert not offenders, (
        "conversion_funnel_daily の削除済み列をソース参照しています(BQ 400の原因)。\n"
        "正: step2b_service_view / step1_to_2b_rate / step2b_to_3_rate\n"
        + "\n".join(offenders)
    )


def test_funnel_correct_columns_present():
    """正しい新列名が使われていること(旧列名へ戻す逆退行のガード)。"""
    for rel in ("app.py", "src/natural_language_qa.py"):
        assert "step2b_service_view" in _read(rel), f"{rel} に step2b_service_view が無い"

    ps = _read("src/priority_scorer.py")
    for col in ("step2b_service_view", "step1_to_2b_rate", "step2b_to_3_rate"):
        assert col in ps, f"priority_scorer.py に {col} が無い"
