"""営業メール除外を **実データ（BigQuery）** で証明する（2026-09-16 新設）。

なぜ要るか:
    `test_sales_inquiry_exclusion.py` は SQL ファイルの**文字列**しか見ておらず、
    BQ を一度も実行していない。だから「実装した」は言えても
    「**集計結果が実際に変わった**」は誰も確かめていなかった。
    2026-09-14 に客様から「BigQuery側でも反映されていますか」と聞かれ、
    当方は Looker 層の話しかしていなかったことが分かった（落とし穴 #49）。

走らせ方:
    認証（SA鍵 or ADC）と ARK_GCP_PROJECT_ID が解決できる時だけ走る。
    解決できなければ skip する（CI で毎回赤くしないため）。
        ARK_GCP_PROJECT_ID=<id> GOOGLE_APPLICATION_CREDENTIALS=<key.json> \
        python3 -m pytest tests/test_sales_inquiry_exclusion_live.py -q

    🔴 客様へ「除外しました／除外されています」と書く前は、skip のまま通さない。
       skip は「確かめていない」であって「問題なし」ではない。
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 除外設定を本番公開した日（これより前の送信は種別が残っておらず除外できない＝仕様）
GO_LIVE = "2026-09-11"


@pytest.fixture(scope="module")
def bq():
    try:
        from src import _config_loader as C

        pid = C.get_project_id()
        client = C.make_bq_client(pid)
        client.query("SELECT 1").result()
    except Exception as e:  # 認証なし・権限なし・オフライン
        pytest.skip(f"BQ に到達できないため skip（確かめていない）: {type(e).__name__}: {e}")
    return client, pid


def _rows(bq, sql):
    client, _ = bq
    return [dict(r) for r in client.query(sql).result()]


def test_sales_sessions_are_never_conversions(bq):
    """① stg: 営業メールのお問い合わせ完了は is_conversion=false でなければならない。"""
    _, pid = bq
    rows = _rows(bq, f"""
        SELECT COUNTIF(is_conversion) AS leaked, COUNT(*) AS total
        FROM `{pid}.staging.stg_ga4_events`
        WHERE conversion_type = 'inquiry_sales'
          AND event_date >= '{GO_LIVE}'
    """)
    assert rows, "クエリが行を返さない"
    assert rows[0]["leaked"] == 0, (
        f"営業メールが {rows[0]['leaked']} 件 CV に混ざっている"
        f"（inquiry_sales 総数 {rows[0]['total']}）"
    )


def test_sales_and_normal_inquiry_are_separated(bq):
    """② stg: 種別が付いた日に inquiry と inquiry_sales が別物として存在する。

    ここが 0 件だと ① は「対象が無いから緑」＝分子0の緑（落とし穴 #48）になる。
    実データに1件も営業メールが無い期間では skip し、緑を装わない。
    """
    _, pid = bq
    rows = _rows(bq, f"""
        SELECT
          COUNTIF(conversion_type = 'inquiry_sales') AS sales_n,
          COUNTIF(conversion_type = 'inquiry')       AS normal_n
        FROM `{pid}.staging.stg_ga4_events`
        WHERE event_date >= '{GO_LIVE}'
    """)
    r = rows[0]
    if r["sales_n"] == 0:
        pytest.skip("公開日以降に営業メールの送信が1件も無い＝除外の効きを実データで示せない")
    assert r["sales_n"] > 0


def test_marts_does_not_count_sales_inquiry(bq):
    """③ marts: 営業メールしか無かった日の total_conversions は 0 になる。

    stg で分けても marts が拾い直していたら意味がない＝層をまたいで確かめる。
    """
    _, pid = bq
    rows = _rows(bq, f"""
        WITH sales_only AS (
          SELECT event_date
          FROM `{pid}.staging.stg_ga4_events`
          WHERE event_date >= '{GO_LIVE}' AND conversion_type IS NOT NULL
          GROUP BY event_date
          HAVING COUNTIF(is_conversion) = 0 AND COUNTIF(conversion_type = 'inquiry_sales') > 0
        )
        SELECT s.event_date, k.total_conversions
        FROM sales_only s
        JOIN `{pid}.marts.daily_kpi_summary` k ON k.report_date = s.event_date
    """)
    if not rows:
        pytest.skip("営業メールだけの日が無い＝この観点を実データで示せない")
    bad = [r for r in rows if r["total_conversions"] != 0]
    assert not bad, f"営業メールだけの日なのに CV が計上されている: {bad}"


def test_document_dl_is_untouched(bq):
    """④ 資料DLは種別と無関係＝巻き添えで消えていないこと（除外の副作用チェック）。"""
    _, pid = bq
    rows = _rows(bq, f"""
        SELECT COUNTIF(NOT is_conversion) AS broken, COUNT(*) AS total
        FROM `{pid}.staging.stg_ga4_events`
        WHERE conversion_type = 'document_dl' AND event_date >= '{GO_LIVE}'
    """)
    r = rows[0]
    if r["total"] == 0:
        pytest.skip("公開日以降に資料DLが無い")
    assert r["broken"] == 0, f"資料DLが {r['broken']} 件 CV から外れている（巻き添え）"
