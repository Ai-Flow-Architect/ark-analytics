"""週次KPIメールのCVR・集計期間表示の回帰テスト（BQ/メール送信なし・モック）

検収指摘の再発防止:
- CVRは overall_cvr=(問合せ+資料DL)/全セッション を表示する（contact_cr=到達→完了率ではない）
  クライアント例: セッション358・問合せ30・資料DL0 → 30/358 = 8.38%（旧バグは63.4%表示）
- レポートに実集計期間（MIN/MAX report_date）を明示する（「月初〜送信日」の誤認防止）
"""
import sys
import types
from unittest import mock
from datetime import date


def _install_stub_modules(capture: dict):
    """main.py が関数内 import する src.* をスタブ化し、送信HTMLを捕捉する"""
    dc = types.ModuleType("src.data_collector")

    class FakeCollector:
        def get_monthly_kpi(self, month):
            # 検収で指摘された実数値を再現（overall_cvr=8.38%、contact_cr=63.4%）
            return {
                "month": "2026-06",
                "period_start": date(2026, 6, 1),
                "period_end": date(2026, 6, 13),
                "sessions": 358,
                "inquiries": 30,
                "downloads": 0,
                "overall_cvr": 0.0838,   # ← 正しい表示値（8.38%）
                "contact_cr": 0.634,     # ← 旧バグはこちらを表示していた（63.4%）
            }

    dc.GA4DataCollector = FakeCollector
    sys.modules["src.data_collector"] = dc

    dl = types.ModuleType("src.delivery")

    class FakeDelivery:
        def send_gmail(self, month, html_body, to_email=None, cc_emails=None):
            capture["html"] = html_body
            capture["month"] = month

    dl.ReportDelivery = FakeDelivery
    sys.modules["src.delivery"] = dl

    rf = types.ModuleType("src.report_formatter")
    rf.ReportFormatter = object
    sys.modules["src.report_formatter"] = rf


def test_weekly_cvr_uses_overall_cvr_and_shows_period():
    if "yaml" not in sys.modules:
        sys.modules["yaml"] = types.ModuleType("yaml")
    import main

    capture: dict = {}
    _install_stub_modules(capture)

    fixed_today = date(2026, 6, 15)
    with mock.patch.object(main, "date") as mdate, \
         mock.patch.object(main, "_run_freshness_check", return_value=None):
        mdate.today.return_value = fixed_today
        mdate.side_effect = lambda *a, **k: date(*a, **k)
        main.run_weekly_report(frequency="weekly")

    html = capture.get("html", "")
    assert html, "メールHTMLが生成されていない"
    # 正: 全体CVR 8.38% が表示される
    assert "8.38%" in html, f"overall_cvr(8.38%)が表示されていない: CVR周辺={html[html.find('CVR'):html.find('CVR')+120]}"
    # 誤: 旧バグの contact_cr(63.4%) が表示されてはいけない
    assert "63.4" not in html, "旧バグのCVR(63.4%)が残っている"
    # 集計期間が明示される（実体 6/1〜6/13）
    assert "2026-06-01" in html and "2026-06-13" in html, "実集計期間(2026-06-01〜2026-06-13)が表示されていない"
    print("OK: CVR=8.38%（overall_cvr）表示・集計期間2026-06-01〜2026-06-13明示・旧63.4%は消滅")


if __name__ == "__main__":
    test_weekly_cvr_uses_overall_cvr_and_shows_period()
