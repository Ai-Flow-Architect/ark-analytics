"""
次フェーズ 🟢 ディメンション別 流入/CV・CTA別・ページ別日次・総合ファネル の
構造退行防止テスト。

2026-05-23 追加（クライアント様 次フェーズ要望 (3)(5)(6)(7)(8)(9)(10)(11)(12)(15)）:
新規 marts/reports を Looker が安全に参照できる構造（必須列・_pct の *100 経由・
日次grain・GTM正規イベント名）であることを CI で物理保証する。

実行:
    pytest tests/test_breakdown_dimensions.py -v
"""
from __future__ import annotations

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_MARTS = os.path.join(ROOT, "sql", "marts")
SQL_REPORTS = os.path.join(ROOT, "sql", "reports")
SQL_STAGING = os.path.join(ROOT, "sql", "staging")

TRAFFIC = os.path.join(SQL_MARTS, "traffic_breakdown_daily.sql")
CTA = os.path.join(SQL_MARTS, "cta_breakdown_daily.sql")
PAGE_DAILY = os.path.join(SQL_MARTS, "page_performance_daily.sql")
FUNNEL = os.path.join(SQL_REPORTS, "rpt_funnel_overview.sql")
STG_EVENTS = os.path.join(SQL_STAGING, "stg_ga4_events.sql")
REFRESH = os.path.join(ROOT, "scripts", "daily_refresh.sh")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _strip_comments(sql: str) -> str:
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


def _pct_columns(sql: str) -> list[tuple[str, str]]:
    """`AS xxx_pct` の (列名, 行) を抽出（コメント除去後）。"""
    out: list[tuple[str, str]] = []
    for line in _strip_comments(sql).splitlines():
        m = re.search(r"AS\s+([a-zA-Z0-9_]+_pct)\b", line)
        if m:
            out.append((m.group(1), line))
    return out


# ── (3) 全ディメンションが日次 grain（report_date）であること ──────────────
def test_breakdown_marts_are_daily_grain():
    """期間コントロール統一(3)のため、新規 marts は report_date 日次grainで
    PARTITION されている（週次 week_start / 月次 report_month ではない）。"""
    for path in (TRAFFIC, CTA, PAGE_DAILY):
        sql = _read(path)
        assert "PARTITION BY report_date" in sql, (
            f"{os.path.basename(path)} は report_date 日次grainで PARTITION されていません。"
            f" 期間コントロール統一(3)のため必須。"
        )


# ── (5)(6)(7)(9)(10)(15) traffic_breakdown_daily ─────────────────────────
def test_traffic_breakdown_has_all_dimension_types():
    """7ディメンション（device/channel/search_engine/landing_page/referral/user_type/
    exit_page）がすべて実装されている。exit_page は2026-06-11 検収⑦対応で追加。"""
    sql = _read(TRAFFIC)
    required = [
        "'device'", "'channel'", "'search_engine'",
        "'landing_page'", "'referral'", "'user_type'", "'exit_page'",
    ]
    missing = [d for d in required if d not in sql]
    assert not missing, f"traffic_breakdown_daily に不足ディメンション: {missing}"


def test_traffic_breakdown_has_required_metric_columns():
    sql = _read(TRAFFIC)
    required = [
        "dimension_type", "dimension_value",
        "sessions", "users", "new_users", "engaged_sessions",
        "pageviews", "conversions",
        "engagement_rate_pct", "conversion_rate_pct",
    ]
    missing = [c for c in required if c not in sql]
    assert not missing, f"traffic_breakdown_daily に必須列が不足: {missing}"


# ── (8) cta_breakdown_daily ───────────────────────────────────────────────
def test_cta_breakdown_uses_cta_click_and_params():
    sql = _read(CTA)
    assert "event_name = 'cta_click'" in sql, "cta_breakdown_daily は cta_click を集計する必要があります"
    for col in ("cta_location", "cta_type", "cta_purpose", "cta_clicks", "click_sessions"):
        assert col in sql, f"cta_breakdown_daily に列 {col} が不足"


def test_staging_extracts_cta_params():
    """staging が GTM タグ②のCTAパラメータ（GA4イベントタグ送出名）を読み取っている。"""
    sql = _read(STG_EVENTS)
    keys = set(re.findall(r"key\s*=\s*'([^']+)'", sql))
    for k in ("cta_location", "cta_type", "cta_purpose", "cta_id", "cta_text"):
        assert k in keys, f"stg_ga4_events.sql が CTAパラメータ '{k}' を読み取っていません"


# ── (11) page_performance_daily ───────────────────────────────────────────
def test_page_performance_daily_has_raw_counts():
    """ページ別パフォーマンスの『実数併記』(11): 率だけでなく実数列が存在する。"""
    sql = _read(PAGE_DAILY)
    raw = [
        "pageviews", "unique_pageviews", "scroll_90pct_count",
        "cta_clicks", "conversions_from_page",
        "desktop_pageviews", "mobile_pageviews", "tablet_pageviews",
    ]
    missing = [c for c in raw if c not in sql]
    assert not missing, f"page_performance_daily に実数列が不足: {missing}"


# ── (12) rpt_funnel_overview ──────────────────────────────────────────────
def test_funnel_overview_has_three_stages():
    """総合ビューのファネル(12): CTAクリック→フォーム到達→完了 の3段階＋率。"""
    sql = _read(FUNNEL)
    required = [
        "stage1_cta_click", "stage2_form_reach", "stage3_completion",
        "cta_to_form_rate_pct", "form_to_complete_rate_pct", "cta_to_complete_rate_pct",
    ]
    missing = [c for c in required if c not in sql]
    assert not missing, f"rpt_funnel_overview に必須列が不足: {missing}"


# ── 退行防止: _pct 列はすべて *100 を経由 ─────────────────────────────────
@pytest.mark.parametrize("path", [TRAFFIC, CTA, PAGE_DAILY, FUNNEL])
def test_pct_columns_multiply_by_100(path: str):
    pct = _pct_columns(_read(path))
    assert pct, f"{os.path.basename(path)} に _pct 列が見つかりません"
    offenders = [c for c, line in pct if "* 100" not in line and "*100" not in line]
    assert not offenders, (
        f"{os.path.basename(path)} の _pct 列が *100 を経由していません: {offenders}"
    )


# ── 退行防止: 率は SAFE_DIVIDE（0除算防止） ───────────────────────────────
@pytest.mark.parametrize("path", [TRAFFIC, CTA, PAGE_DAILY, FUNNEL])
def test_rates_use_safe_divide(path: str):
    sql = _strip_comments(_read(path))
    assert "SAFE_DIVIDE" in sql, (
        f"{os.path.basename(path)} の比率計算に SAFE_DIVIDE が使われていません（0除算リスク）"
    )


# ── daily_refresh.sh 配線保証 ─────────────────────────────────────────────
def test_daily_refresh_wires_new_objects():
    """新規 marts/reports が daily_refresh.sh に配線されている（毎日再生成される）。"""
    sh = _read(REFRESH)
    for needle in (
        "marts/traffic_breakdown_daily.sql",
        "marts/cta_breakdown_daily.sql",
        "marts/page_performance_daily.sql",
        "reports/rpt_funnel_overview.sql",
    ):
        assert needle in sh, f"daily_refresh.sh に {needle} が配線されていません"


# ── チャットアナリスト配線保証（2026-06-11 検収⑥⑦対応） ──────────────────
def test_chat_app_wires_traffic_breakdown():
    """app.py のチャットが traffic_breakdown_daily（検索エンジン/Referral/離脱等）を
    参照している。検収指摘「Looker で見える情報がチャットで取得できない」の再発防止。"""
    app = _read(os.path.join(ROOT, "app.py"))
    for needle in (
        "marts.traffic_breakdown_daily",
        "'search_engine'", "'referral'", "'exit_page'",
        "検索エンジン",
    ):
        assert needle in app, f"app.py のチャットデータ取得に {needle} が配線されていません"


def test_chat_app_funnel_uses_inclusive_columns():
    """app.py のファネル取得が単調保証の包含列（*_incl）を使う。
    2026-06-03 確定の主ファネル正本と Looker 総合ビューに整合させる。"""
    app = _read(os.path.join(ROOT, "app.py"))
    for needle in ("step3_contact_reach_incl", "step4_form_start_incl"):
        assert needle in app, f"app.py のファネルクエリに {needle} が使われていません"


def test_chat_app_resolves_project_id_from_sa_secret():
    """Streamlit Cloud Secrets に ARK_GCP_PROJECT_ID が無くても、
    gcp_service_account 内の project_id から解決できる（2026-06-11 本番起動不能の再発防止）。"""
    app = _read(os.path.join(ROOT, "app.py"))
    assert 'st.secrets["gcp_service_account"]).get("project_id"' in app, (
        "app.py に SAキーからの project_id フォールバックがありません"
        "（Secrets未設定環境で起動不能になります）"
    )


def test_daily_refresh_order_marts_before_funnel_report():
    """rpt_funnel_overview は conversion_funnel_daily の後に実行される（依存順）。"""
    sh = _read(REFRESH)
    assert sh.index("conversion_funnel_daily.sql") < sh.index("rpt_funnel_overview.sql"), (
        "rpt_funnel_overview は conversion_funnel_daily の後に配線する必要があります"
    )
