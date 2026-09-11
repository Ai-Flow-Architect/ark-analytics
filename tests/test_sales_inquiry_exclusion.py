"""営業メールを CV 集計から除外する定義の退行防止（2026-09-11 客様ご依頼・7/6 お約束分）。

仕組み: GTM が完了画面で inquiry_kind(inquiry_type) を送る → stg_ga4_events が
同じセッションに inquiry_type='sales' がある contact_finish を conversion_type='inquiry_sales' に分け、
is_conversion からも外す。marts は conversion_type='inquiry' / is_conversion を参照するので一律に効く。
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
STG = ROOT / "sql" / "staging" / "stg_ga4_events.sql"


def _code(path):
    return "\n".join(l.split("--", 1)[0] for l in path.read_text(encoding="utf-8").splitlines())


def test_stg_reads_inquiry_type_param():
    assert "key = 'inquiry_type'" in _code(STG), "inquiry_type パラメータを読んでいない"


def test_stg_flags_sales_session_from_inquiry_kind():
    code = _code(STG)
    assert "event_name = 'inquiry_kind'" in code and "inquiry_type = 'sales'" in code
    assert "OVER (PARTITION BY session_id)" in code, "セッション単位で種別を判定していない"
    assert "session_id IS NOT NULL" in code, "session_id NULL の行をまとめて判定してしまう"


def test_stg_final_columns_exclude_sales():
    code = _code(STG)
    assert "THEN 'inquiry_sales'" in code, "営業メールの完了を inquiry と別にしていない"
    assert re.search(r"_is_conversion_base\s+AND NOT \(_conversion_type_base = 'inquiry' AND _is_sales_session\)", code), \
        "is_conversion（広義CV）から営業メールを外していない"
    # 最終列は外側SELECTで1回だけ定義（内側に同名列が残ると二重定義）
    assert code.count("AS conversion_type,") == 1
    assert code.count("AS is_conversion") == 1


def test_document_dl_is_not_affected():
    code = _code(STG)
    m = re.search(r"CASE\s+WHEN _conversion_type_base = 'inquiry' AND _is_sales_session", code)
    assert m, "営業判定は inquiry にだけ当てる（資料DLは種別と無関係）"


def test_no_downstream_reincludes_sales():
    """marts/reports が inquiry_sales を再び CV として数えていないこと。"""
    for sub in ("marts", "reports"):
        for p in (ROOT / "sql" / sub).glob("*.sql"):
            code = _code(p)
            assert "LIKE 'inquiry" not in code, f"{p.name}: LIKE 'inquiry%' は inquiry_sales を含めてしまう"
            assert "inquiry_sales" not in code, f"{p.name}: inquiry_sales を直接参照している"
            assert not re.search(r"event_name\s*=\s*'contact_finish'", code), \
                f"{p.name}: contact_finish を直接数えると営業メールが混ざる（conversion_type を使う）"
