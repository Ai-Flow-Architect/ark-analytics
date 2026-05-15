"""
ファネル遷移率列の退行防止テスト

2026-05-15: B⑤ GTM発火検証で発覚した「scroll_depth / cta_click / form_start 0件」
事態を受けて、conversion_funnel_daily.sql の各 funnel_rate_*_pct 列が
SQL レイヤで正しく `* 100` を経由していることを保証する。

旧バグ: 比率列が `ROUND(SAFE_DIVIDE(...), 4)` で 0.0xxx 素値のまま放置され、
Looker 側で「数値書式: %」を当てると正しく見える一方、scorecard で
直接参照すると 0.05 ≒ 5% を「0.05%」と表示してしまう事故が頻発した。

実行:
    pytest tests/test_funnel_step_rate.py -v
"""
from __future__ import annotations

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RPT_LOOKER_MAIN = os.path.join(ROOT, "sql", "reports", "rpt_looker_main.sql")
CONVERSION_FUNNEL_DAILY = os.path.join(ROOT, "sql", "marts", "conversion_funnel_daily.sql")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _strip_comments(sql: str) -> str:
    """SQL から行コメント `--` 以降を除去（テキスト中の `--` は単純除去で問題なし）。"""
    out = []
    for line in sql.splitlines():
        out.append(line.split("--", 1)[0])
    return "\n".join(out)


def test_funnel_rate_columns_exist_in_rpt_looker_main():
    """rpt_looker_main に必須の funnel_rate_*_pct 列が存在する。"""
    sql = _read(RPT_LOOKER_MAIN)
    required_pct_columns = [
        "funnel_cta_click_rate_pct",
        "funnel_cta_to_contact_rate_pct",
        "funnel_rate_1to2_pct",
        "funnel_rate_2to3_pct",
        "funnel_rate_3to4_pct",
        "funnel_rate_4to5_pct",
        "funnel_overall_cvr_pct",
    ]
    missing = [c for c in required_pct_columns if c not in sql]
    assert not missing, (
        f"rpt_looker_main.sql にファネル比率の _pct 列が不足: {missing}. "
        f"Looker scorecard で直接参照するため必須。"
    )


def test_funnel_rate_columns_have_multiplication_by_100():
    """funnel_*_rate_pct 列は ROUND(... * 100, 2) を経由している。"""
    sql_no_comments = _strip_comments(_read(RPT_LOOKER_MAIN))

    # `AS funnel_*_pct` の行をすべて抽出
    pct_lines: list[tuple[str, str]] = []
    for line in sql_no_comments.splitlines():
        m = re.search(r"AS\s+(funnel_[a-zA-Z0-9_]+_pct)\b", line)
        if m:
            pct_lines.append((m.group(1), line))

    assert pct_lines, "rpt_looker_main.sql に funnel_*_pct 列が1つも見つかりません"

    offenders: list[str] = []
    for col, line in pct_lines:
        if "* 100" not in line and "*100" not in line:
            offenders.append(f"{col}: {line.strip()}")
    assert not offenders, (
        f"funnel_*_pct 列のうち '* 100' を含まない列が検出されました: {offenders}. "
        f"パーセント表記 (0〜100) を返すには必ず `* 100` を経由してください。"
    )


def test_conversion_funnel_daily_has_required_step_columns():
    """conversion_funnel_daily に Step1〜Step5 の必須列がすべて存在する。"""
    sql = _read(CONVERSION_FUNNEL_DAILY)
    required_steps = [
        "step1_sessions",        # Step1: 訪問
        "step2a_cta_click",      # Step2a: CTAクリック（GTMタグ②）
        "step2b_service_view",   # Step2b: サービスページ閲覧
        "step3_contact_page",    # Step3: お問い合わせページ到達
        "step4_form_start",      # Step4: フォーム入力開始（GTMタグ③）
        "step5_submission",      # Step5: フォーム送信完了（contact_finish）
    ]
    missing = [c for c in required_steps if c not in sql]
    assert not missing, (
        f"conversion_funnel_daily.sql に必須ステップ列が不足: {missing}. "
        f"ファネル可視化のため必須。"
    )


def test_conversion_funnel_daily_uses_correct_event_names():
    """conversion_funnel_daily が GTM 正規イベント名で集計している。"""
    sql = _read(CONVERSION_FUNNEL_DAILY)
    # 旧バグ由来の誤名が残っていないこと
    assert "event_name = 'scroll'" not in sql, "誤った event_name 'scroll' が残存"
    assert "event_name = 'click'" not in sql, "誤った event_name 'click' が残存"
    # 必須の正規名で集計していること
    required_events = ["cta_click", "form_start", "contact_finish"]
    for ev in required_events:
        pattern = f"event_name = '{ev}'"
        assert pattern in sql, (
            f"conversion_funnel_daily.sql に '{pattern}' が見つかりません。"
            f"GTM 正規イベント名で集計してください。"
        )


def test_rpt_looker_main_uses_safe_divide_for_rates():
    """比率計算は SAFE_DIVIDE を使用している（0除算防止）。"""
    sql_no_comments = _strip_comments(_read(CONVERSION_FUNNEL_DAILY))
    # SAFE_DIVIDE を経由しているか
    safe_divide_count = sql_no_comments.count("SAFE_DIVIDE")
    assert safe_divide_count >= 6, (
        f"conversion_funnel_daily.sql の SAFE_DIVIDE 使用回数が想定より少ない: "
        f"{safe_divide_count}件 (期待: 6件以上). "
        f"step1_to_cta_rate / cta_to_contact_rate / step1_to_2b_rate / "
        f"step2b_to_3_rate / step3_to_4_rate / step4_to_5_rate / overall_inquiry_cvr "
        f"の各比率で 0除算防止のため SAFE_DIVIDE 必須。"
    )
