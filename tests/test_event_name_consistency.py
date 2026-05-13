"""
GTMタグ ⇔ BQ SQL の整合性チェック

2026-05-13 インシデント由来：
GTMタグが送信するイベント名・パラメータ名と、BQ集計SQLが期待する名前が
ズレており、過去30日 scroll_90pct_count / cta_clicks / step4_form_start が
全て 0 件のまま放置されていた（クライアントレビューで発覚）。

このテストは GTM タグ定義（docs/GTM_TAGS.md）と SQL の event_name / event_param
参照が物理的に一致していることを CI でブロックする。

実行:
    pytest tests/test_event_name_consistency.py -v
"""
from __future__ import annotations

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# GTM タグから送出される正規イベント名（docs/GTM_TAGS.md と一致させる）
GTM_EVENT_NAMES = {
    "scroll_depth",     # タグ① スクロール深度
    "cta_click",        # タグ② CTAクリック
    "form_start",       # タグ③ フォーム入力開始
    "contact_finish",   # タグ③ フォーム送信完了（既存）
    "form_abandon",     # タグ③ 入力途中離脱
}

# 旧バグ由来の禁止イベント名（SQL に残ってはいけない）
FORBIDDEN_EVENT_NAMES = {
    "scroll",   # 正: scroll_depth
    "click",    # 正: cta_click（汎用 click は使わない）
}

# GTM タグ① のスクロール深度パラメータ名（gtag('event','scroll_depth',{scroll_pct:m})）
GTM_SCROLL_PARAM = "scroll_pct"

SQL_DIRS = [
    os.path.join(ROOT, "sql", "staging"),
    os.path.join(ROOT, "sql", "marts"),
    os.path.join(ROOT, "sql", "reports"),
]


def _read_sql_files() -> dict[str, str]:
    out: dict[str, str] = {}
    for d in SQL_DIRS:
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".sql"):
                continue
            path = os.path.join(d, fn)
            with open(path, "r", encoding="utf-8") as f:
                out[os.path.relpath(path, ROOT)] = f.read()
    return out


def _find_event_name_literals(sql: str) -> set[str]:
    """SQL 中の `event_name = '...'` または `event_name IN ('...')` を抽出する。"""
    found: set[str] = set()
    for m in re.finditer(r"event_name\s*=\s*'([^']+)'", sql):
        found.add(m.group(1))
    for m in re.finditer(r"event_name\s+IN\s*\(([^)]+)\)", sql, re.IGNORECASE):
        for lit in re.findall(r"'([^']+)'", m.group(1)):
            found.add(lit)
    return found


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_EVENT_NAMES))
def test_no_forbidden_event_name(forbidden: str):
    """旧バグ由来の event_name (`scroll` / `click`) が SQL に残っていない。"""
    offenders: list[tuple[str, str]] = []
    for rel, sql in _read_sql_files().items():
        events = _find_event_name_literals(sql)
        if forbidden in events:
            offenders.append((rel, forbidden))
    assert not offenders, (
        f"禁止 event_name '{forbidden}' が SQL に残っています: {offenders}. "
        f"GTM 側の正規名（scroll_depth / cta_click）に置換してください。"
    )


def test_scroll_param_name_matches_gtm():
    """staging が GTM タグ① のパラメータ名 `scroll_pct` を読んでいる。

    旧バグ: staging が `percent_scrolled` を読み、GTM が `scroll_pct` を送っており
    永続的に NULL になっていた。
    """
    path = os.path.join(ROOT, "sql", "staging", "stg_ga4_events.sql")
    with open(path, "r", encoding="utf-8") as f:
        sql = f.read()
    # event_params の key 参照箇所を抽出
    keys = set(re.findall(r"key\s*=\s*'([^']+)'", sql))
    assert GTM_SCROLL_PARAM in keys, (
        f"stg_ga4_events.sql が GTM スクロール深度パラメータ '{GTM_SCROLL_PARAM}' を "
        f"読み取っていません。検出した key: {sorted(keys)}"
    )
    assert "percent_scrolled" not in keys, (
        "stg_ga4_events.sql に旧 key 'percent_scrolled' が残っています。"
        " GTM 送信パラメータは 'scroll_pct' です。"
    )


def test_rpt_looker_main_has_pct_columns():
    """Looker 単位統一のため `_pct` 接尾辞列が rpt_looker_main に存在する。"""
    path = os.path.join(ROOT, "sql", "reports", "rpt_looker_main.sql")
    with open(path, "r", encoding="utf-8") as f:
        sql = f.read()
    required = [
        "engagement_rate_pct",
        "overall_cvr_pct",
        "contact_form_cr_pct",
        "inquiry_only_cvr_pct",       # B1 直観合致の厳密CVR
        "funnel_overall_cvr_pct",
    ]
    missing = [c for c in required if c not in sql]
    assert not missing, (
        f"rpt_looker_main に必須 _pct 列が不足しています: {missing}. "
        f"Looker scorecard の単位統一のため追加してください。"
    )


def test_gtm_event_names_appear_in_sql():
    """GTM が送出するイベント名のうち、SQL で集計対象になるものが実在する。"""
    all_event_literals: set[str] = set()
    for _rel, sql in _read_sql_files().items():
        all_event_literals.update(_find_event_name_literals(sql))
    # 必ず集計されるべきイベント
    must_have = {"scroll_depth", "cta_click", "form_start", "contact_finish"}
    missing = must_have - all_event_literals
    assert not missing, (
        f"SQL 集計対象に GTM イベント名が不足: {missing}. "
        f"検出した event_name: {sorted(all_event_literals)}"
    )
