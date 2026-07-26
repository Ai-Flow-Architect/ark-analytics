"""
回帰防止テスト: 検収R12 ②（2026-07-26）「クリック0件のCTA番号も常に全行表示」。

client 指摘: Looker「CTA番号別内訳」でクリックのあった番号しか行が出ず、
期間によっては「データなし」になる（設定した全番号が出る想定）。

対応: marts.cta_number_breakdown_daily を
  「番号付与開始日〜最新データ日の日付スパイン × 対応表21番号」のグリッド駆動にし、
  実績が無い組み合わせを 0 で埋める。

守る不変条件:
  1. グリッド（date_spine × cta_number_master）で行を作ること＝0件番号が消えない。
  2. 実績カラムは COALESCE で 0 埋めすること（NULL のままだと Looker で空欄表示）。
  3. 対応表に無い番号（(対応表外)）の実績行を落とさないこと。
  4. 率は 0/0 を 0% と断定せず SAFE_DIVIDE のまま（分母0=NULL）。
  5. 付与開始日より前の日付を捏造しないこと（スパイン開始＝2026-07-14）。
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_REL = "sql/marts/cta_number_breakdown_daily.sql"


def _read(rel: str) -> str:
    path = os.path.join(ROOT, rel)
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def _code_lines(sql: str) -> str:
    """コメント行を除いた実コード。"""
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


def test_date_spine_exists():
    """1: 日付スパインを GENERATE_DATE_ARRAY で作っていること。"""
    code = _code_lines(_read(SQL_REL))
    assert "date_spine AS (" in code, "date_spine CTE が無い（0件番号が再び消える）"
    assert "GENERATE_DATE_ARRAY" in code, "日付スパインが GENERATE_DATE_ARRAY で作られていない"


def test_grid_drives_rows_not_agg():
    """1: 最終SELECTの駆動表が実績(agg)でなくグリッド(row_keys)であること。"""
    code = _code_lines(_read(SQL_REL))
    assert "row_keys AS (" in code, "row_keys CTE が無い"
    assert "CROSS JOIN cta_number_master" in code, (
        "スパイン×対応表の CROSS JOIN が無い＝全番号が出ない"
    )
    assert "FROM row_keys k" in code, (
        "最終SELECTが row_keys 駆動でない（FROM agg のままだと0件番号が消える）"
    )
    assert "LEFT JOIN agg a" in code, "実績は LEFT JOIN で載せること"


def test_zero_fill_on_metrics():
    """2: 実績カラムが 0 埋めされていること。"""
    code = _code_lines(_read(SQL_REL))
    for col in ("cta_clicks", "click_sessions", "click_users",
                "inquiry_cv_click_sessions", "cv_click_sessions"):
        assert f"COALESCE(a.{col}," in code, f"{col} が 0 埋めされていない"


def test_unknown_cta_id_rows_are_kept():
    """3: 対応表外の実績番号を UNION DISTINCT で残していること。"""
    code = _code_lines(_read(SQL_REL))
    assert "UNION DISTINCT" in code, "対応表外の実績行が落ちる（グリッドのみの構成）"
    assert "'(対応表外)'" in code, "対応表外ラベルが消えている"


def test_rate_is_not_faked_zero():
    """4: 分母0の行の率を 0 と断定していないこと。"""
    code = _code_lines(_read(SQL_REL))
    assert "SAFE_DIVIDE(a.inquiry_cv_click_sessions, a.click_sessions)" in code, (
        "到達率が SAFE_DIVIDE でない"
    )
    assert "COALESCE(a.cta_to_cv_rate" not in code, (
        "分母0の率を 0 埋めしている（0件番号に 0% と表示され誤読を招く）"
    )


def test_spine_starts_at_numbering_go_live():
    """5: 番号付与開始日より前の行を作らないこと。"""
    code = _code_lines(_read(SQL_REL))
    assert "DATE '2026-07-14'" in code, (
        "スパイン開始日（data-cta-id 本番付与日）が固定されていない"
    )
