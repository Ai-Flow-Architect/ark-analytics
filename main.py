"""
main.py
ark-analytics AI月次レポート自動生成 エントリーポイント

使い方:
  # 月次レポート生成（今月）
  python main.py --report-type monthly

  # 指定月のレポート生成
  python main.py --report-type monthly --month 2026-04

  # 週次ミニレポート（Lark通知のみ）
  python main.py --report-type weekly

  # ドライラン（メール送信なし・コンソール出力のみ）
  python main.py --report-type monthly --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date

import yaml


def get_target_month(args_month: str | None) -> str:
    """対象月を決定する（デフォルト: 先月）"""
    if args_month:
        return args_month
    today = date.today()
    # 1日実行なので「今月」= 先月分のレポートを生成
    year, month = today.year, today.month - 1
    if month == 0:
        year, month = year - 1, 12
    return f"{year:04d}-{month:02d}"


def run_monthly_report(month: str, dry_run: bool = False) -> None:
    """月次レポートを生成して配信する"""
    print(f"\n=== ark-analytics 月次レポート: {month} ===\n")

    # 各モジュールをインポート（依存パッケージのインストール後に利用可能）
    from src.data_collector import GA4DataCollector
    from src.prompt_builder import PromptBuilder
    from src.ai_analyzer import AIAnalyzer
    from src.report_formatter import ReportFormatter
    from src.delivery import ReportDelivery

    # 1. データ収集
    print("1/5 BigQueryからデータ取得中...")
    collector = GA4DataCollector()
    kpi = collector.get_monthly_kpi(month)
    mom_data = collector.get_mom_comparison(month)
    channel_df = collector.get_channel_breakdown(month)
    funnel = collector.get_funnel_summary(month)
    top_pages_df = collector.get_top_pages(month)

    if not kpi:
        from src.alert import notify_failure
        reason = f"{month} の marts.daily_kpi_summary に該当データがありません"
        print(f"❌ {reason}")
        notify_failure(
            job="monthly_report",
            reason=reason,
            context={"month": month, "dry_run": dry_run},
        )
        sys.exit(1)

    print(f"   セッション: {int(kpi.get('sessions', 0)):,} | 問合せ: {int(kpi.get('inquiries', 0))}件")

    # 2. プロンプト生成
    print("2/5 プロンプト生成中...")
    builder = PromptBuilder()
    mom = mom_data.get("diff", {})
    exec_prompt = builder.build_executive(month, kpi, mom, channel_df, funnel)
    ops_prompt = builder.build_ops(month, kpi, mom, channel_df, funnel, top_pages_df)

    # 3. AI分析
    print("3/5 AI分析中 (GPT-4o)...")
    analyzer = AIAnalyzer()
    exec_insight = analyzer.analyze(exec_prompt, report_type="executive")
    ops_insight = analyzer.analyze(ops_prompt, report_type="ops")
    print("   AI分析完了")

    # 4. レポート整形
    print("4/5 レポート整形中...")
    formatter = ReportFormatter()
    html_report = formatter.to_html(month, kpi, exec_insight, ops_insight)
    md_report = formatter.to_markdown(month, kpi, exec_insight, ops_insight)

    if dry_run:
        print("\n--- [DRY RUN] レポートプレビュー (Markdown) ---")
        print(md_report[:2000])
        print("\n--- [DRY RUN] 送信はスキップしました ---")
        return

    # 5. 配信
    print("5/5 配信中...")
    delivery = ReportDelivery()

    # Drive保存
    drive_url = delivery.save_to_drive(month, md_report)

    # Gmail送信
    delivery.send_gmail(month, html_report)

    # Lark通知
    delivery.notify_lark(month, kpi, drive_url=drive_url)

    print(f"\n✅ {month} 月次レポート完了")


def run_weekly_report(frequency: str = "weekly") -> None:
    """週次/隔週ミニレポート（Lark通知 + メール配信）

    Args:
        frequency: "weekly"（毎週）または "biweekly"（隔週）
    """
    from src.data_collector import GA4DataCollector
    from src.delivery import ReportDelivery
    from src.report_formatter import ReportFormatter

    today = date.today()

    # 隔週の場合は奇数週のみ実行
    if frequency == "biweekly":
        week_number = today.isocalendar()[1]
        if week_number % 2 != 1:
            print(f"⏭  隔週設定のため今週はスキップ（第{week_number}週 = 偶数週）")
            return

    month = f"{today.year:04d}-{today.month:02d}"
    week_label = f"{today.month}/{today.day}週"

    print(f"\n=== ark-analytics 週次ミニレポート ({today}) ===\n")
    collector = GA4DataCollector()
    kpi = collector.get_monthly_kpi(month)

    if not kpi:
        from src.alert import notify_failure
        reason = f"{month} の marts.daily_kpi_summary に該当データがありません（daily_refresh が走っていない可能性あり）"
        print(f"❌ {reason}")
        notify_failure(
            job="weekly_report",
            reason=reason,
            context={"month": month, "frequency": frequency, "today": str(today)},
        )
        sys.exit(1)

    sessions = int(kpi.get("sessions", 0))
    inquiries = int(kpi.get("inquiries", 0))
    downloads = int(kpi.get("downloads", 0))
    cvr = round(float(kpi.get("contact_cr", 0)) * 100, 2)

    # メール配信（KPIサマリー形式）
    delivery = ReportDelivery()
    html_body = f"""
<html><body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;">
<h2 style="color:#1e293b;border-bottom:2px solid #4a6cf7;padding-bottom:8px;">
  週次KPIレポート｜{week_label}（{month}月累積）
</h2>
<table style="width:100%;border-collapse:collapse;margin:16px 0;">
  <tr style="background:#f8faff;">
    <td style="padding:10px 14px;border:1px solid #e2e8f0;font-weight:700;">セッション数</td>
    <td style="padding:10px 14px;border:1px solid #e2e8f0;">{sessions:,}件
      <span style="color:#64748b;font-size:12px;">（目標 5,000件 / 達成率 {sessions/5000*100:.1f}%）</span></td>
  </tr>
  <tr>
    <td style="padding:10px 14px;border:1px solid #e2e8f0;font-weight:700;">問合せ数</td>
    <td style="padding:10px 14px;border:1px solid #e2e8f0;">{inquiries}件
      <span style="color:#64748b;font-size:12px;">（目標 9件 / 達成率 {inquiries/9*100:.1f}%）</span></td>
  </tr>
  <tr style="background:#f8faff;">
    <td style="padding:10px 14px;border:1px solid #e2e8f0;font-weight:700;">資料DL数</td>
    <td style="padding:10px 14px;border:1px solid #e2e8f0;">{downloads}件</td>
  </tr>
  <tr>
    <td style="padding:10px 14px;border:1px solid #e2e8f0;font-weight:700;">CVR</td>
    <td style="padding:10px 14px;border:1px solid #e2e8f0;">{cvr}%</td>
  </tr>
</table>
<p style="color:#64748b;font-size:13px;">
  ※ 月末時点の月次AIレポートで詳細分析・改善施策をお届けします。<br>
  ※ Looker Studioダッシュボードでリアルタイム確認できます：
  <a href="https://datastudio.google.com/reporting/e26ea2fe-edd9-47d6-8187-dd7c7cd31b8e">ダッシュボードを開く</a>
</p>
<p style="font-size:12px;color:#94a3b8;">このメールは ark-analytics 自動配信システムにより送信されています。</p>
</body></html>
"""
    delivery.send_gmail(
        month,
        html_body,
        to_email=None,  # ARK_CLIENT_EMAIL 環境変数から取得
    )

    print("✅ 週次レポート完了（メール配信）")


def run_qa(question: str) -> None:
    """自然言語Q&Aモード"""
    from src.natural_language_qa import NaturalLanguageQA
    qa = NaturalLanguageQA()
    if question:
        print("\n分析中...\n")
        answer = qa.ask(question)
        print(f"回答:\n{answer}\n")
    else:
        qa.interactive()


def run_scorer() -> None:
    """改善施策優先順位スコアリングモード"""
    from src.priority_scorer import PriorityScorer
    scorer = PriorityScorer()
    scorer.print_table()


def main() -> None:
    parser = argparse.ArgumentParser(description="ark-analytics AI レポート自動生成")
    parser.add_argument(
        "--report-type",
        choices=["monthly", "weekly", "qa", "scorer"],
        default="monthly",
        help="レポート種別 (monthly / weekly / qa / scorer)",
    )
    parser.add_argument(
        "--month",
        type=str,
        default=None,
        help="対象月 (例: 2026-04)。未指定の場合は先月",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="ドライラン（メール・Drive保存なし）",
    )
    parser.add_argument(
        "--question",
        type=str,
        default="",
        help="QAモード用の質問文 (例: 'どのページが一番離脱が多いですか？')",
    )
    parser.add_argument(
        "--frequency",
        choices=["weekly", "biweekly"],
        default="weekly",
        help="週次レポートの配信頻度 (weekly=毎週 / biweekly=隔週)",
    )
    args = parser.parse_args()

    if args.report_type == "monthly":
        month = get_target_month(args.month)
        run_monthly_report(month, dry_run=args.dry_run)
    elif args.report_type == "weekly":
        run_weekly_report(frequency=args.frequency)
    elif args.report_type == "qa":
        run_qa(args.question)
    elif args.report_type == "scorer":
        run_scorer()


if __name__ == "__main__":
    main()
