"""
report_formatter.py
AI生成インサイトをHTML/Markdownレポートに整形するモジュール
"""
from __future__ import annotations

import os
from datetime import datetime


class ReportFormatter:
    """AI分析テキスト → HTMLメール・Markdownレポートに変換"""

    HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }}
    h1 {{ color: #1a73e8; border-bottom: 2px solid #1a73e8; padding-bottom: 8px; }}
    h2 {{ color: #34495e; margin-top: 24px; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 16px 0; }}
    .kpi-card {{ background: #f8f9fa; border-radius: 8px; padding: 16px; text-align: center; }}
    .kpi-label {{ font-size: 12px; color: #666; }}
    .kpi-value {{ font-size: 28px; font-weight: bold; color: #1a73e8; }}
    .kpi-target {{ font-size: 11px; color: #999; }}
    .good {{ color: #27ae60; }}
    .bad {{ color: #e74c3c; }}
    .insight {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 12px 16px; margin: 8px 0; }}
    footer {{ font-size: 12px; color: #999; margin-top: 32px; border-top: 1px solid #eee; padding-top: 12px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 8px 0; }}
    th {{ background: #f0f0f0; padding: 8px; text-align: left; }}
    td {{ padding: 8px; border-bottom: 1px solid #eee; }}
  </style>
</head>
<body>
  <h1>📊 {month} Webサイト分析レポート</h1>
  <p>ark-hd.co.jp | データ取得日時: {generated_date}</p>

  <h2>KPIサマリー</h2>
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-label">月間セッション</div>
      <div class="kpi-value {sessions_class}">{sessions:,}</div>
      <div class="kpi-target">目標: 5,000</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">お問い合わせ数</div>
      <div class="kpi-value {inquiry_class}">{inquiries}</div>
      <div class="kpi-target">目標: 9件</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">お問い合わせCVR</div>
      <div class="kpi-value">{contact_cr:.2f}%</div>
      <div class="kpi-target">資料DL: {downloads}件</div>
    </div>
  </div>

  <h2>AIインサイト（経営層向け）</h2>
  <div class="insight">
{executive_insight}
  </div>

  <h2>詳細分析（実務担当向け）</h2>
{ops_insight}

  <footer>
    このレポートはGA4データを元にAIが自動生成しました。<br>
    生成モデル: GPT-4o | データ基盤: BigQuery | 担当: AIフローアーキテクト 五十嵐
  </footer>
</body>
</html>
"""

    def to_html(
        self,
        month: str,
        kpi: dict,
        executive_insight: str,
        ops_insight: str,
    ) -> str:
        """HTMLメール本文を生成"""
        sessions = int(kpi.get("sessions", 0))
        inquiries = int(kpi.get("inquiries", 0))
        downloads = int(kpi.get("downloads", 0))
        contact_cr = round(float(kpi.get("contact_cr", 0)) * 100, 2)

        # 目標達成でカラー変更
        sessions_class = "good" if sessions >= 5000 else "bad"
        inquiry_class = "good" if inquiries >= 9 else "bad"

        # MarkdownをシンプルなHTML変換
        executive_html = self._md_to_simple_html(executive_insight)
        ops_html = self._md_to_simple_html(ops_insight)

        return self.HTML_TEMPLATE.format(
            month=month,
            generated_date=datetime.now().strftime("%Y年%m月%d日 %H:%M"),
            sessions=sessions,
            sessions_class=sessions_class,
            inquiries=inquiries,
            inquiry_class=inquiry_class,
            contact_cr=contact_cr,
            downloads=downloads,
            executive_insight=executive_html,
            ops_insight=ops_html,
        )

    def to_markdown(
        self,
        month: str,
        kpi: dict,
        executive_insight: str,
        ops_insight: str,
    ) -> str:
        """Markdownレポートを生成（Drive保存用）"""
        sessions = int(kpi.get("sessions", 0))
        inquiries = int(kpi.get("inquiries", 0))
        contact_cr = round(float(kpi.get("contact_cr", 0)) * 100, 2)

        return f"""# {month} Webサイト分析レポート

> ark-hd.co.jp | データ取得日時: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}

## KPIサマリー

| 指標 | 実績 | 目標 | 達成率 |
|------|------|------|--------|
| 月間セッション | {sessions:,} | 5,000 | {sessions/50:.1f}% |
| お問い合わせ数 | {inquiries} | 9件 | {inquiries/9*100:.1f}% |
| お問い合わせCVR | {contact_cr}% | - | - |
| 資料DL数 | {int(kpi.get('downloads', 0))} | 30件 | {int(kpi.get('downloads', 0))/30*100:.1f}% |

---

## AIインサイト（経営層向け）

{executive_insight}

---

## 詳細分析（実務担当向け）

{ops_insight}

---
*このレポートはGA4データを元にAIが自動生成しました。*
*生成モデル: GPT-4o | データ基盤: BigQuery | 担当: AIフローアーキテクト 五十嵐*
"""

    @staticmethod
    def _md_to_simple_html(md: str) -> str:
        """MarkdownをシンプルなHTMLに変換（外部ライブラリ不要）"""
        lines = []
        for line in md.split("\n"):
            if line.startswith("### "):
                lines.append(f"<h3>{line[4:]}</h3>")
            elif line.startswith("## "):
                lines.append(f"<h3>{line[3:]}</h3>")
            elif line.startswith("- ") or line.startswith("* "):
                lines.append(f"<li>{line[2:]}</li>")
            elif line.startswith("**") and line.endswith("**"):
                lines.append(f"<strong>{line[2:-2]}</strong>")
            elif line.strip():
                lines.append(f"<p>{line}</p>")
        return "\n".join(lines)
