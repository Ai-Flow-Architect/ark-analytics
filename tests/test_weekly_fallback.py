"""月初フォールバックの制御フロー検証（BQ/メール送信なし・モック）

6/1 想定: 当月(2026-06)は空 → 前月(2026-05)にフォールバックし、
month が前月表記に揃い、send_gmail が前月monthで呼ばれることを確認する。
"""
import sys
import types
from unittest import mock
from datetime import date


def _install_stub_modules():
    """main.py が関数内 import する src.* をスタブ化"""
    # src.data_collector.GA4DataCollector
    dc = types.ModuleType("src.data_collector")

    class FakeCollector:
        def __init__(self):
            self.calls = []

        def get_monthly_kpi(self, month):
            self.calls.append(month)
            # 当月は空、前月はデータあり
            if month == "2026-06":
                return {}
            return {"sessions": 1234, "inquiries": 5, "downloads": 3, "contact_cr": 0.004}

    dc.GA4DataCollector = FakeCollector
    sys.modules["src.data_collector"] = dc

    # src.delivery.ReportDelivery
    dl = types.ModuleType("src.delivery")

    class FakeDelivery:
        sent = []

        def send_gmail(self, month, html_body, to_email=None, cc_emails=None):
            FakeDelivery.sent.append(month)

    dl.ReportDelivery = FakeDelivery
    sys.modules["src.delivery"] = dl

    # src.report_formatter.ReportFormatter（import されるだけ）
    rf = types.ModuleType("src.report_formatter")
    rf.ReportFormatter = object
    sys.modules["src.report_formatter"] = rf

    return FakeDelivery


def test_month_start_falls_back_to_prev_month():
    # main.py トップレベルの import yaml を回避（依存未導入環境でも回す）
    if "yaml" not in sys.modules:
        sys.modules["yaml"] = types.ModuleType("yaml")
    import main

    FakeDelivery = _install_stub_modules()
    FakeDelivery.sent = []

    fixed_today = date(2026, 6, 1)

    with mock.patch.object(main, "date") as mdate, \
         mock.patch.object(main, "_run_freshness_check", return_value=None):
        mdate.today.return_value = fixed_today
        # date(...) コンストラクタ呼び出しは本物に委譲
        mdate.side_effect = lambda *a, **k: date(*a, **k)

        main.run_weekly_report(frequency="weekly")

    assert FakeDelivery.sent == ["2026-05"], f"前月にフォールバックされていない: {FakeDelivery.sent}"
    print("OK: 6/1 当月空 → 前月2026-05でメール配信される")


if __name__ == "__main__":
    test_month_start_falls_back_to_prev_month()
