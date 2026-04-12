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
        print(f"❌ {month} のデータが取得できませんでした")
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


def run_weekly_report() -> None:
    """週次ミニレポート（Lark通知のみ）"""
    from src.data_collector import GA4DataCollector
    from src.delivery import ReportDelivery

    today = date.today()
    month = f"{today.year:04d}-{today.month:02d}"

    print(f"\n=== ark-analytics 週次ミニレポート ({today}) ===\n")
    collector = GA4DataCollector()
    kpi = collector.get_monthly_kpi(month)

    if not kpi:
        print("❌ データが取得できませんでした")
        return

    delivery = ReportDelivery()
    delivery.notify_lark(month, kpi)
    print("✅ 週次Lark通知完了")


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
    args = parser.parse_args()

    if args.report_type == "monthly":
        month = get_target_month(args.month)
        run_monthly_report(month, dry_run=args.dry_run)
    elif args.report_type == "weekly":
        run_weekly_report()
    elif args.report_type == "qa":
        run_qa(args.question)
    elif args.report_type == "scorer":
        run_scorer()


if __name__ == "__main__":
    main()
