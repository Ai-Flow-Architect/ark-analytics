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
# 2026-06-08 更新: 'scroll' を禁止から解除。
#   実データ監査で custom `scroll_depth`(560件) は深度パラメータを一切送出しておらず、
#   GA4標準 `scroll`(percent_scrolled=90・87件) が唯一の正しい90%到達供給源と判明したため、
#   native `scroll` を集計対象に含める設計に変更（5/13 の scroll_depth 単独前提は誤りだった）。
FORBIDDEN_EVENT_NAMES = {
    "click",    # 正: cta_click（汎用 click は使わない）
}

# スクロール深度パラメータ名。custom scroll_depth は `scroll_pct`、
# GA4標準 scroll は `percent_scrolled` を送る。staging は両方を COALESCE で受ける。
GTM_SCROLL_PARAM = "scroll_pct"
GA4_NATIVE_SCROLL_PARAM = "percent_scrolled"

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
    """staging が custom/native 両方のスクロール深度パラメータを読んでいる。

    2026-06-08 改定: 実データ監査で
      - custom `scroll_depth` は深度パラメータ(scroll_pct)を送出できておらず常に NULL
      - GA4標準 `scroll` が `percent_scrolled=90` を正送信
    と判明したため、staging は `scroll_pct`（custom優先）と `percent_scrolled`（native）の
    両方を COALESCE で受ける設計に変更した。両 key を読んでいることを保証する。
    """
    path = os.path.join(ROOT, "sql", "staging", "stg_ga4_events.sql")
    with open(path, "r", encoding="utf-8") as f:
        sql = f.read()
    # event_params の key 参照箇所を抽出
    keys = set(re.findall(r"key\s*=\s*'([^']+)'", sql))
    assert GTM_SCROLL_PARAM in keys, (
        f"stg_ga4_events.sql が custom スクロール深度パラメータ '{GTM_SCROLL_PARAM}' を "
        f"読み取っていません。検出した key: {sorted(keys)}"
    )
    assert GA4_NATIVE_SCROLL_PARAM in keys, (
        f"stg_ga4_events.sql が GA4標準 scroll の '{GA4_NATIVE_SCROLL_PARAM}' を "
        f"読み取っていません（90%到達の唯一の実供給源）。検出した key: {sorted(keys)}"
    )


def test_scroll_pct_column_name_is_unified():
    """下流に渡る列名は `scroll_pct` に統一されている（命名負債解消）。

    旧バグ: stg_ga4_events で `scroll_pct AS percent_scrolled` と AS で偽装し、
    下流SQLが `percent_scrolled` を参照する命名不一致を放置していた。

    2026-06-08 改定: `percent_scrolled` は GA4標準 scroll の event_param key として
    `key = 'percent_scrolled'` の形で読み取るのは正当（native供給源）。
    禁止するのは列エイリアス `AS percent_scrolled`（命名偽装）のみに限定する。
    """
    sql_files = _read_sql_files()
    offenders: list[tuple[str, int]] = []
    for rel, sql in sql_files.items():
        for i, line in enumerate(sql.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("--") or stripped.startswith("/*"):
                continue
            sql_part = line.split("--", 1)[0]
            # 列エイリアスとしての percent_scrolled のみ禁止（param key 読み取りは許可）
            if re.search(r"\bAS\s+percent_scrolled\b", sql_part, re.IGNORECASE):
                offenders.append((rel, i))
    assert not offenders, (
        f"列エイリアス 'AS percent_scrolled' が SQL に残っています: {offenders}. "
        f"下流に渡す列名は `scroll_pct` に統一してください。"
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


def test_pct_columns_have_multiplication_by_100():
    """_pct 接尾辞列は `* 100` を経由してパーセント表記になっていることを保証する。

    退行防止: 将来のリファクタで `ROUND(rate * 100, 2) AS rate_pct` が
    `ROUND(rate, 2) AS rate_pct` に変わると、列名は _pct のままだが値が
    0.0xxx の素値になり、Looker 側で「%書式」を当てている運用者だけ
    1/100 表示になる事故が CI を通り抜けてしまう。
    """
    path = os.path.join(ROOT, "sql", "reports", "rpt_looker_main.sql")
    with open(path, "r", encoding="utf-8") as f:
        sql = f.read()
    # _pct AS 行を抽出（行末コメントは除く）
    pct_lines = []
    for line in sql.splitlines():
        sql_part = line.split("--", 1)[0]
        m = re.search(r"AS\s+([a-zA-Z_]+_pct)\b", sql_part)
        if m:
            pct_lines.append((m.group(1), sql_part))
    assert pct_lines, "rpt_looker_main.sql に _pct 列が1つも見つかりません"
    offenders: list[str] = []
    for col, line in pct_lines:
        if "* 100" not in line and "*100" not in line:
            offenders.append(f"{col}: {line.strip()}")
    assert not offenders, (
        f"_pct 列のうち '* 100' を含まない列が検出されました（退行リスク）: {offenders}. "
        f"パーセント表記 (0〜100) を返すには必ず `* 100` を経由してください。"
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
