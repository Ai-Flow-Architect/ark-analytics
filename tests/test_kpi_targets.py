"""
test_kpi_targets.py
KPI目標値のSSOT検証 — settings.yaml (kpi_targets) がレポート出力に反映されること。

背景: 2026-07-08 クライアント指摘。お問い合わせ目標がコード各所に「9」で
ハードコードされ、目標変更(9→6)がレポートに反映されなかった。
再発防止として「目標値はconfig経由・9が出力に残らない」ことを固定する。
"""
from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src._config_loader import get_kpi_targets  # noqa: E402
from src.report_formatter import ReportFormatter  # noqa: E402
from src.prompt_builder import PromptBuilder  # noqa: E402


KPI = {
    "sessions": 1234,
    "inquiries": 5,
    "downloads": 10,
    "inquiry_cvr": 0.004,
    "period_start": "2026-06-01",
    "period_end": "2026-06-30",
}


def test_settings_yaml_inquiry_target_is_6():
    """settings.yaml のKPI目標はクライアント確定値
    （お問い合わせ6件=2026-07-08／セッション5,000・資料DL50件・パートナー契約3件=2026-07-16）
    """
    targets = get_kpi_targets()
    assert targets["monthly_inquiries"] == 6
    assert targets["monthly_sessions"] == 5000
    assert targets["monthly_downloads"] == 50
    assert targets["monthly_contracts"] == 3


def test_html_report_uses_config_target():
    """HTMLレポートの目標表記がconfig値（6件）に追従し、旧値9件が残らない"""
    html = ReportFormatter().to_html("2026-06", KPI, "exec", "ops")
    assert "目標: 6件" in html
    assert "目標: 9件" not in html
    assert "目標: 5,000" in html


def test_markdown_report_uses_config_target():
    """Markdownレポートの目標・達成率がconfig値（6件）で計算される"""
    md = ReportFormatter().to_markdown("2026-06", KPI, "exec", "ops")
    assert "| 6件 |" in md
    assert f"{5 / 6 * 100:.1f}%" in md
    assert "9件" not in md


def test_executive_prompt_uses_config_target():
    """AIプロンプトの目標表記がconfig値（6件）に追従し、旧値9件が残らない"""
    builder = PromptBuilder()
    channel_df = pd.DataFrame(
        columns=["channel_grouping", "sessions", "conversions", "conversion_rate_pct"]
    )
    prompt = builder.build_executive("2026-06", KPI, {}, channel_df, {})
    assert "目標: 6件" in prompt
    assert "お問い合わせ6件" in prompt
    assert "9件" not in prompt


# ── AIチャット2経路のKPI目標配線（2026-07-20 客様②「KPI・達成率を教えて」対応） ──
# app.py（Streamlit=客様が触る本番）と src/natural_language_qa.py（CLI経路）は
# コンテキスト供給が別実装。片方だけ実装すると「画面では答えるがCLIでは答えない」
# 定義ドリフトになるため、両経路を同時に強制する（[[feedback_same_guard_two_implementations]]）。
# ラベルは全文で照合する（前方一致だと "…_MUT" のような書き換えを素通りさせ、
# 2経路で別ラベルになっても気付けない＝2026-07-20のミューテーション実測で確認）
_KPI_TARGET_LABEL = "KPI目標と当月達成率（確定値・月途中）"


def _src(rel: str) -> str:
    path = os.path.join(os.path.dirname(__file__), "..", rel)
    return open(path, encoding="utf-8").read()


def test_both_chat_paths_supply_kpi_target_context():
    """2経路とも当月達成率の確定値ブロックをBQから供給していること"""
    for rel in ("app.py", "src/natural_language_qa.py"):
        code = _src(rel)
        assert _KPI_TARGET_LABEL in code, f"{rel} にKPI目標コンテキストが無い"
        assert "get_kpi_targets" in code, f"{rel} が目標値をSSOT(get_kpi_targets)から取っていない"
        assert "downloads_achieved_pct" in code, f"{rel} の達成率がSQL側で確定計算されていない"


def test_chat_paths_do_not_hardcode_target_values():
    """目標値をプロンプト/クエリに直書きしないこと（変更時に旧値が残る事故の再発防止）"""
    for rel in ("app.py", "src/natural_language_qa.py"):
        code = _src(rel)
        for literal in ("monthly_sessions', 5000", "資料ダウンロード50件", "目標50件", "目標30件"):
            assert literal not in code, f"{rel} に目標値の直書き（{literal}）がある"


def test_chat_paths_state_kgi_contracts_not_in_ga4():
    """KGIパートナー契約はGA4外＝推定値を出さない指示が両経路にあること"""
    for rel in ("app.py", "src/natural_language_qa.py"):
        code = _src(rel)
        assert "パートナー契約" in code, f"{rel} にKGIの取扱い指示が無い"
        assert "推定値を出さない" in code, f"{rel} にKGI推定禁止の指示が無い"
