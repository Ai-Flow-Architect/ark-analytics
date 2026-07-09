"""
回帰防止テスト: 検収R10-B/R10-C「定義書2026-07-09 答え合わせ」の定義統一を構造的に守る。

背景(2026-07-09〜10):
  定義書受領により5差分を修正（新規/リピーターのセッション単位化・ファネルSTEP2厳密化・
  ページ別CTAクリック率のセッション単位化・ページ経由CV数・CV分子のお問い合わせ限定）。
  この案件の最頻クレームは「同名指標が画面（Looker/メール/AIチャット）によって数値が違う」
  ＝落とし穴#30（定義移行漏れ）。本テストは全画面の供給クエリが同一定義であることを
  コードレベルで強制する。
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel: str) -> str:
    path = os.path.join(ROOT, rel)
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def test_funnel_step2_uses_starts_with_not_bare_like():
    """STEP2サービス閲覧: 部分一致 LIKE '%/service%' の再混入を防ぐ（定義書=/service/配下）。"""
    sql = _read("sql/marts/conversion_funnel_daily.sql")
    assert "STARTS_WITH(page_path, '/service/')" in sql, (
        "conversion_funnel_daily の STEP2 が STARTS_WITH('/service/') でない"
    )
    # コメント行を除いた実コードに旧部分一致が残っていないこと
    code = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
    assert "LIKE '%/service%'" not in code, (
        "STEP2 に旧部分一致 LIKE '%/service%' が残存（別サブドメイン痕跡パス混入バグの再発）"
    )


def test_user_type_is_session_scoped():
    """新規/リピーター: GA4ネイティブ ga_session_number=1 のセッション単位判定であること。"""
    stg_e = _read("sql/staging/stg_ga4_events.sql")
    stg_s = _read("sql/staging/stg_sessions.sql")
    tb = _read("sql/marts/traffic_breakdown_daily.sql")
    assert "ga_session_number" in stg_e, "stg_ga4_events に ga_session_number 抽出が無い"
    assert "is_first_session" in stg_s, "stg_sessions に is_first_session が無い"
    assert re.search(r"COALESCE\(\s*s\.is_first_session", tb), (
        "traffic_breakdown_daily の user_type がセッション単位判定(is_first_session)でない"
    )
    assert re.search(r"IF\(is_first_session,\s*'新規'", tb), (
        "user_type の 新規/リピーター 判定が is_first_session ベースでない"
    )


def test_inquiry_only_cv_columns_exist():
    """CV分子のお問い合わせ限定列が3マート全てに存在すること（広義CVとの分離）。"""
    assert "AS inquiry_conversions" in _read("sql/marts/traffic_breakdown_daily.sql")
    assert "AS inquiry_conversions" in _read("sql/marts/channel_kpi_monthly.sql")
    assert "AS inquiry_cv_click_sessions" in _read("sql/marts/cta_breakdown_daily.sql")
    assert "AS inquiry_cv_sessions" in _read("sql/marts/page_performance_daily.sql")


def test_backward_compat_columns_not_removed():
    """Looker既存チャートが参照する旧列が削除されていないこと（GUI差し替え前のチャート破損防止）。"""
    checks = {
        "sql/marts/traffic_breakdown_daily.sql": ["AS conversions", "AS sessions", "AS new_users"],
        "sql/marts/channel_kpi_monthly.sql": ["AS conversions", "AS conversion_rate"],
        "sql/marts/page_performance_daily.sql": [
            "AS conversions_from_page", "AS cta_click_rate", "AS cta_clicks",
            "AS cta_click_sessions", "AS unique_pageviews",
        ],
        "sql/marts/conversion_funnel_daily.sql": ["AS step2b_service_view", "AS step5_submission"],
        "sql/reports/rpt_looker_main.sql": [
            "AS returning_users", "AS inquiry_only_cvr_pct", "AS download_only_cvr_pct",
        ],
        "sql/marts/daily_kpi_summary.sql": [
            "AS document_downloads", "AS document_download_sessions",
        ],
    }
    for rel, cols in checks.items():
        sql = _read(rel)
        for col in cols:
            assert col in sql, f"{rel} から {col} が消えている（後方互換違反）"


def test_ai_chat_and_mail_use_definition_book_metrics():
    """AIチャット/メールの供給クエリが定義書準拠列（Lookerと同定義）を使っていること。"""
    # ページ別: 日次テーブル×セッション単位CTA率×ページ経由CV数
    for rel in ("app.py", "src/natural_language_qa.py"):
        src = _read(rel)
        assert "page_performance_daily" in src, f"{rel} のページ別が日次テーブルでない"
        assert "inquiry_cv_sessions" in src, f"{rel} のページ別CVが inquiry_cv_sessions でない"
        assert "cta_click_sessions" in src and "unique_pageviews" in src, (
            f"{rel} のCTAクリック率がセッション単位（cta_click_sessions/unique_pageviews）でない"
        )
        # 旧定義（週次テーブル・完了ページ集中CV）の再混入防止（コメント言及は許容し実使用のみ検出）
        assert "SUM(conversions_from_page)" not in src, f"{rel} に旧 SUM(conversions_from_page) が残存"
    # チャネル別: お問い合わせ限定CV
    for rel in ("app.py", "src/natural_language_qa.py", "src/data_collector.py"):
        src = _read(rel)
        assert "inquiry_conversion" in src, f"{rel} のチャネルCVが inquiry 基準でない"
    # メールのページ別（get_top_pages）
    dc = _read("src/data_collector.py")
    assert "SUM(inquiry_cv_sessions)" in dc, "data_collector.get_top_pages のCVが定義書準拠でない"
    assert "SUM(cta_click_sessions), SUM(unique_pageviews)" in dc, (
        "data_collector.get_top_pages のCTA率がセッション単位でない"
    )


def test_ai_chat_has_page_cv_interpretation_guard():
    """ページ経由CV数の解釈ガード（ページ間合算禁止）がAI供給プロンプトにあること。"""
    for rel in ("app.py", "src/natural_language_qa.py", "src/prompt_builder.py"):
        src = _read(rel)
        assert "ページ経由CV数" in src, f"{rel} にページ経由CV数の解釈ガードが無い"
