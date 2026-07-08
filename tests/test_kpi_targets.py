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
    """settings.yaml のお問い合わせ目標は6件（2026-07-08 クライアント確定値）"""
    targets = get_kpi_targets()
    assert targets["monthly_inquiries"] == 6
    assert targets["monthly_sessions"] == 5000
    assert targets["monthly_downloads"] == 30


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
