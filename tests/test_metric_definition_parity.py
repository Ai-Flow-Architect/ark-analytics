"""
回帰防止テスト: 検収R7で再発した「同一指標が複数オブジェクトで定義ドリフト」を構造的に防ぐ。

背景(2026-06-23 R7):
  ① 平均滞在時間(avg_time_on_page_sec)の修正(5/31)が週次 marts.page_performance にだけ適用され、
     Looker参照の日次 marts.page_performance_daily に旧バグ式(AVG(IF(page_view, engtime)))が残存し
     全null/0に再発した（落とし穴#30 週次→日次の定義移行漏れ）。
  ③ AIチャット(app.py / src/natural_language_qa.py)がファネルを直列前提で誤回答した
     （並列到達の定義がプロンプトに無く、生英語列名を注入していた）。

本テストは CL-9（同一指標の複数テーブル定義一致）/ CL-10（AIプロンプトにファネル構造前提を明記）を
コードで強制し、片方だけ修正・片経路だけ修正の取りこぼしを再発させない。
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel: str) -> str:
    path = os.path.join(ROOT, rel)
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def _avg_time_uses_sum_over_pv(sql: str) -> bool:
    """avg_time_on_page_sec が『SUM(engagement_time_msec) / COUNTIF(page_view)』式かを判定。"""
    # 正しい式: SAFE_DIVIDE(SUM(engagement_time_msec), COUNTIF(event_name = 'page_view'))
    return bool(
        re.search(r"SAFE_DIVIDE\(\s*SUM\(engagement_time_msec\)", sql)
    ) and "AS avg_time_on_page_sec" in sql


def test_avg_time_formula_parity_weekly_vs_daily():
    """① 週次 page_performance と 日次 page_performance_daily の平均滞在式が一致していること。"""
    weekly = _read("sql/marts/page_performance.sql")
    daily = _read("sql/marts/page_performance_daily.sql")
    assert _avg_time_uses_sum_over_pv(weekly), "週次 page_performance の avg_time 式が想定外"
    assert _avg_time_uses_sum_over_pv(daily), (
        "日次 page_performance_daily の avg_time が SUM/COUNTIF 式でない＝旧バグ式の再混入の疑い"
    )


def test_avg_time_no_buggy_pageview_avg():
    """① 旧バグ式 AVG(IF(event_name='page_view', engagement_time_msec...)) が残っていないこと。"""
    for rel in ("sql/marts/page_performance.sql", "sql/marts/page_performance_daily.sql"):
        sql = _read(rel)
        buggy = re.search(r"AVG\(\s*IF\(\s*event_name\s*=\s*'page_view'\s*,\s*engagement_time_msec", sql)
        assert not buggy, f"{rel} に旧バグ式 AVG(IF(page_view, engagement_time_msec)) が残存"


def test_ai_chat_has_funnel_structure_caveat():
    """③ AIチャット両経路のプロンプトにファネル構造（並列到達）の注意書きがあること。"""
    for rel in ("app.py", "src/natural_language_qa.py"):
        src = _read(rel)
        assert "ファネルの構造" in src, f"{rel} のプロンプトにファネル構造の注意書きが無い"
        assert "並列" in src, f"{rel} のプロンプトに『並列』到達の説明が無い"


def test_ai_chat_funnel_uses_incl_columns():
    """③ AIチャット両経路のファネルクエリが包含定義(incl)列で統一されていること（非単調逆転防止）。"""
    for rel in ("app.py", "src/natural_language_qa.py"):
        src = _read(rel)
        assert "step3_contact_reach_incl" in src, f"{rel} が step3_contact_reach_incl を使っていない"
        assert "step4_form_start_incl" in src, f"{rel} が step4_form_start_incl を使っていない"
