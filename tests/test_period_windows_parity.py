"""
test_period_windows_parity.py
客様⑤(2026-07-23): AIチャットの期間指定質問（直近30日/今月/先月）対応の回帰テスト。

app.py（Streamlit=客様が触る本番）と src/natural_language_qa.py（CLI）は
コンテキスト供給が別実装。片方だけ修正すると「画面では答えるがCLIでは答えない」
定義ドリフトになる（[[feedback_same_guard_two_implementations]]）。
app.py は import 時に Streamlit UI を実行するため import できない＝ASTで静的に比較する。

強制する内容:
① 期間窓の4定義（PERIOD_WINDOWS/_requested_period_windows/_period_kpi_sql/_period_funnel_sql）
   が両ファイルでAST完全一致（どちらか片方だけの変更を即検出）
② 期間窓のWHERE句が仕様通り（30日=当日含む30日/今月=月初〜/先月=前月1日〜末日の半開区間）
③ SQLが確定値作法（MIN/MAX period・ratio of sums・AVG禁止・空期間ガード）
④ 両経路が期間ブロックを実際に供給配線していること（検知呼出し・SQL使用・ラベル）
⑤ プロンプトに期間引用ルールが両経路にあること
"""
from __future__ import annotations

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.natural_language_qa import (  # noqa: E402
    PERIOD_WINDOWS,
    _period_funnel_sql,
    _period_kpi_sql,
    _requested_period_windows,
)

PATHS = ("app.py", "src/natural_language_qa.py")
SHARED_DEFS = (
    "PERIOD_WINDOWS",
    "_requested_period_windows",
    "_period_kpi_sql",
    "_period_funnel_sql",
)


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _node(tree: ast.Module, name: str):
    """モジュール直下の代入 or 関数定義ノードを取得（無ければ失敗）。"""
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return node.value
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"モジュール直下に {name} が無い")


def test_period_definitions_ast_identical_across_both_paths():
    """① 4定義が両ファイルでAST完全一致（片経路だけの修正＝定義ドリフトを即検出）"""
    trees = {rel: ast.parse(_read(rel)) for rel in PATHS}
    for name in SHARED_DEFS:
        dumps = {rel: ast.dump(_node(tree, name)) for rel, tree in trees.items()}
        assert dumps["app.py"] == dumps["src/natural_language_qa.py"], (
            f"{name} が app.py と src/natural_language_qa.py で不一致（定義ドリフト）。"
            "両ファイルに同一テキストで置くこと"
        )


def test_period_window_where_clauses_exact():
    """② WHERE句が仕様通り（文字単位照合＝ミューテーションで落ちる）"""
    w = {name: (where, kws, suffix) for name, where, kws, suffix in PERIOD_WINDOWS}
    assert set(w) == {"直近30日", "今月", "先月"}
    # 当日を含めて30日 ＝ INTERVAL 29 DAY
    assert w["直近30日"][0] == (
        "report_date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 29 DAY)"
    )
    assert w["今月"][0] == "report_date >= DATE_TRUNC(CURRENT_DATE('Asia/Tokyo'), MONTH)"
    # 先月＝前月1日以上・当月1日未満の半開区間（末日を取りこぼさず当月を混ぜない）
    assert w["先月"][0] == (
        "report_date >= DATE_TRUNC(DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 1 MONTH), MONTH)"
        " AND report_date < DATE_TRUNC(CURRENT_DATE('Asia/Tokyo'), MONTH)"
    )


def test_period_keyword_routing():
    """② 期間語がある時だけ該当窓を返し、無ければ空（既存挙動・トークン量の維持）"""
    def names(q: str) -> list:
        return [n for n, _, _ in _requested_period_windows(q.lower())]

    assert names("直近30日のセッション数は？") == ["直近30日"]
    assert names("今月のCVRは先月と比べてどうですか？") == ["今月", "先月"]
    assert names("前月のファネルを見せて") == ["先月"]
    assert names("どのページが離脱多い？") == []   # 期間語なし＝供給しない
    assert names("直近14日の傾向は？") == []       # 14日は既存ブロックの担当


def test_period_sql_follows_confirmed_value_conventions():
    """③ 確定値作法: MIN/MAX period・ratio of sums・AVG禁止・空期間ガード・対象テーブル"""
    where = PERIOD_WINDOWS[0][1]
    kpi = _period_kpi_sql("proj", where)
    fun = _period_funnel_sql("proj", where)
    for sql, table in ((kpi, "marts.daily_kpi_summary"), (fun, "marts.conversion_funnel_daily")):
        assert "MIN(report_date) AS period_start" in sql
        assert "MAX(report_date) AS period_end" in sql
        assert f"`proj.{table}`" in sql
        assert f"WHERE {where}" in sql, "期間WHERE句がSQLに注入されていない"
        assert "HAVING COUNT(*) > 0" in sql, "空期間でNULL行を供給しないガードが無い"
        assert "AVG(" not in sql, "率は日次平均でなくratio of sumsで出す（AVG禁止）"
    # 率はratio of sums（SUM/SUM）＝Looker真値定義と一致
    assert "SAFE_DIVIDE(SUM(engaged_sessions), SUM(sessions))" in kpi
    assert "SAFE_DIVIDE(SUM(contact_form_submissions)+SUM(document_downloads), SUM(sessions))" in kpi
    assert "SAFE_DIVIDE(SUM(new_users), SUM(users))" in kpi
    assert "SAFE_DIVIDE(SUM(step5_submission), SUM(step1_sessions))" in fun
    # ファネルは包含定義(incl)列（非単調逆転の防止＝test_metric_definition_parityと同方針）
    assert "step3_contact_reach_incl" in fun
    assert "step4_form_start_incl" in fun


def test_both_paths_wire_period_blocks_into_context():
    """④ 両経路がKPI・ファネルの期間ブロックを実際に供給配線していること"""
    for rel in PATHS:
        code = _read(rel)
        assert "_requested_period_windows(q)" in code, f"{rel} が期間語検知を呼んでいない"
        assert "_period_kpi_sql(project_id, where_sql)" in code, f"{rel} がKPI期間SQLを使っていない"
        assert "_period_funnel_sql(project_id, where_sql)" in code, f"{rel} がファネル期間SQLを使っていない"
        assert code.count("{name} 期間集計（{suffix}）") >= 2, f"{rel} の期間ブロックラベル配線が不足"
        assert "ファネル{name} 期間集計（{suffix}）" in code, f"{rel} にファネル期間ラベルが無い"


def test_both_prompts_have_period_citation_rules():
    """⑤ プロンプトの期間引用ルールが両経路にあること"""
    for rel in PATHS:
        code = _read(rel)
        assert "【期間指定質問への回答（直近14日／直近30日／今月／先月）】" in code, (
            f"{rel} に期間指定ルールの見出しが無い"
        )
        assert "『今月』は月初〜直近確定日まで（月途中）" in code, f"{rel} に今月＝月途中の注記が無い"
        assert "『先月』は前月1日〜末日" in code, f"{rel} に先月の期間定義が無い"
        assert "他期間の値を流用せず" in code, f"{rel} に確定値なし時の流用禁止ルールが無い"
