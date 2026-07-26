"""
回帰防止テスト: 検収R12 無償対応⑥⑪（2026-07-26）。

⑥ チャネル分析への「資料DL数」追加:
   traffic_breakdown_daily / channel_kpi_monthly に document_dl_conversions 列
   （conversion_type='document_dl' 到達セッション数・inquiry_conversions と同一設計）。
⑪ CTA番号別内訳への「CV達成セッション数」追加:
   cta_number_breakdown_daily に cv_click_sessions 列
   （conversion_type IN ('inquiry','document_dl') のいずれか到達セッション数）。

守る不変条件:
  1. 新列が消えないこと（Looker接続後の削除=チャート破損）。
  2. 既存列 inquiry_conversions / inquiry_cv_click_sessions / conversions が
     変更・削除されないこと（後方互換・⑧で使用中）。
  3. 種別判定は conversion_type 列を参照すること
     （event_name 直接判定=二重定義の再発防止・stg_ga4_events コメント準拠）。
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel: str) -> str:
    path = os.path.join(ROOT, rel)
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def _code_lines(sql: str) -> str:
    """コメント行を除いた実コード。"""
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


def test_document_dl_conversions_column_exists():
    """⑥: 資料DL数列が両マートに存在すること。"""
    for rel in ("sql/marts/traffic_breakdown_daily.sql",
                "sql/marts/channel_kpi_monthly.sql"):
        src = _read(rel)
        assert "AS document_dl_conversions" in src, f"{rel} に document_dl_conversions が無い"
        assert "conversion_type = 'document_dl'" in _code_lines(src), (
            f"{rel} の資料DL判定が conversion_type='document_dl' でない"
        )


def test_cta_number_cv_click_sessions_column_exists():
    """⑪: CV達成セッション数列（inquiry+document_dl）が存在すること。"""
    src = _read("sql/marts/cta_number_breakdown_daily.sql")
    assert "AS cv_click_sessions" in src, (
        "cta_number_breakdown_daily に cv_click_sessions が無い"
    )
    assert "conversion_type IN ('inquiry', 'document_dl')" in _code_lines(src), (
        "cv_click_sessions の判定が conversion_type IN ('inquiry','document_dl') でない"
    )


def test_cv_click_sessions_wired_to_looker_view():
    """⑪: Looker接続VIEW rpt_cta_number（明示列挙式）に新列が配線されていること。
    落とし穴#30（定義移行漏れ）: martに足しても接続VIEWに無ければLookerには永遠に届かない。"""
    src = _read("sql/reports/rpt_cta_number.sql")
    assert "cv_click_sessions" in _code_lines(src), (
        "rpt_cta_number に cv_click_sessions が配線されていない（Lookerから見えない）"
    )


def test_r12_does_not_break_existing_columns():
    """既存列（後方互換・⑧使用中）が残っていること。"""
    tb = _read("sql/marts/traffic_breakdown_daily.sql")
    ck = _read("sql/marts/channel_kpi_monthly.sql")
    cn = _read("sql/marts/cta_number_breakdown_daily.sql")
    assert "AS inquiry_conversions" in tb and "AS conversions" in tb
    assert "AS inquiry_conversions" in ck and "AS conversions" in ck
    assert "AS inquiry_cv_click_sessions" in cn, (
        "inquiry_cv_click_sessions（⑧で使用中）が削除された"
    )
    # inquiry 単独判定も残っていること（cv_click_sessions への置換で消さない）
    assert "conversion_type = 'inquiry'" in _code_lines(cn), (
        "cta_number_breakdown_daily の inquiry 単独判定が消えた"
    )
