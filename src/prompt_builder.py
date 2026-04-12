"""
prompt_builder.py
KPIデータからOpenAI APIへのプロンプトを組み立てるモジュール
"""
from __future__ import annotations

import os
import textwrap

import pandas as pd


class PromptBuilder:
    """KPIデータ → 分析プロンプト変換"""

    EXECUTIVE_TEMPLATE = textwrap.dedent("""\
        あなたはWebマーケティングの専門データアナリストです。
        以下の{month}のGA4データを分析し、経営層向けに簡潔なインサイトレポートを作成してください。

        ## 今月のKPIデータ
        - セッション数: {sessions:,}（目標: 5,000、前月比: {sessions_mom:+.1f}%）
        - 目標達成率: {sessions_target_rate:.1f}%
        - エンゲージメント率: {engagement_rate:.1f}%
        - お問い合わせ数: {inquiries}件（目標: 9件、前月比: {inquiries_mom:+.1f}%）
        - 資料DL数: {downloads}件（前月比: {downloads_mom:+.1f}%）
        - お問い合わせCVR: {contact_cr:.2f}%（前月比: {contact_cr_mom:+.2f}pt）

        ## チャネル別データ
        {channel_table}

        ## ファネル状況
        - サイト訪問 → 問合せページ到達率: {step2_to_3_pct}%
        - 問合せページ → フォーム入力開始率: {step3_to_4_pct}%
        - フォーム入力 → 送信完了率: {step4_to_5_pct}%

        ## 目標
        - KGI: 月3件成約
        - KPI: 月間セッション5,000 / お問い合わせ9件

        ## 出力形式（Markdown）
        ### 今月の総評（3行以内）
        ### 良かった点TOP3
        ### 改善が必要な点TOP3
        ### 来月の推奨アクション（具体的施策3つ）
        ### 経営層へのひとこと（50字以内・ポジティブに締める）

        **注意**: 数字は必ず根拠として引用すること。専門用語は避け、経営層が理解できる言葉で書くこと。
    """)

    OPS_TEMPLATE = textwrap.dedent("""\
        あなたはWebマーケティングの専門データアナリストです。
        以下の{month}のGA4データをもとに、実務担当者向けの詳細な改善提案を作成してください。

        ## KPIサマリー
        - セッション数: {sessions:,}（前月比: {sessions_mom:+.1f}%）
        - エンゲージメント率: {engagement_rate:.1f}%
        - お問い合わせ数: {inquiries}件（CVR: {contact_cr:.2f}%）
        - 資料DL数: {downloads}件

        ## ファネル詳細
        - Step1 サイト訪問: {sessions:,}
        - Step2 サービスページ閲覧率: {step1_to_2_pct}%
        - Step3 問合せページ到達率: {step2_to_3_pct}%
        - Step4 フォーム入力開始率: {step3_to_4_pct}%
        - Step5 フォーム送信完了率: {step4_to_5_pct}%
        - 全体お問い合わせCVR: {overall_inquiry_cvr_pct}%

        ## 主要ページパフォーマンス（上位5ページ）
        {top_pages_table}

        ## チャネル別効率
        {channel_table}

        ## 出力形式（Markdown）
        ### 月次サマリー（3行）
        ### ファネル最大ボトルネックと改善仮説
        ### 改善優先度の高いページ TOP3（理由付き）
        ### 来月の実行アクションリスト（優先度: 高/中/低）
        ### A/Bテスト提案2案（テスト箇所・仮説・成功指標を明記）

        **注意**: 「なぜそうなっているか」の仮説を必ず含めること。データの数字のみを根拠とすること。
    """)

    def build_executive(
        self,
        month: str,
        kpi: dict,
        mom: dict,
        channel_df: "pd.DataFrame",
        funnel: dict,
    ) -> str:
        channel_table = self._df_to_markdown(
            channel_df[["channel_grouping", "sessions", "conversions", "conversion_rate_pct"]]
        )
        sessions_target_rate = (kpi.get("sessions", 0) / 5000 * 100) if kpi.get("sessions") else 0

        return self.EXECUTIVE_TEMPLATE.format(
            month=month,
            sessions=int(kpi.get("sessions", 0)),
            sessions_mom=mom.get("sessions_mom", 0),
            sessions_target_rate=sessions_target_rate,
            engagement_rate=round(float(kpi.get("engagement_rate", 0)) * 100, 1),
            inquiries=int(kpi.get("inquiries", 0)),
            inquiries_mom=mom.get("inquiries_mom", 0),
            downloads=int(kpi.get("downloads", 0)),
            downloads_mom=mom.get("downloads_mom", 0),
            contact_cr=round(float(kpi.get("contact_cr", 0)) * 100, 2),
            contact_cr_mom=mom.get("contact_cr_mom", 0),
            channel_table=channel_table,
            step2_to_3_pct=funnel.get("step2_to_3_pct", "N/A"),
            step3_to_4_pct=funnel.get("step3_to_4_pct", "N/A"),
            step4_to_5_pct=funnel.get("step4_to_5_pct", "N/A"),
        )

    def build_ops(
        self,
        month: str,
        kpi: dict,
        mom: dict,
        channel_df: "pd.DataFrame",
        funnel: dict,
        top_pages_df: "pd.DataFrame",
    ) -> str:
        channel_table = self._df_to_markdown(
            channel_df[["channel_grouping", "sessions", "conversions", "conversion_rate_pct"]]
        )
        top_pages_table = self._df_to_markdown(
            top_pages_df[["page_path", "pageviews", "avg_time_sec", "cta_click_rate_pct", "conversions"]].head(5)
        )

        return self.OPS_TEMPLATE.format(
            month=month,
            sessions=int(kpi.get("sessions", 0)),
            sessions_mom=mom.get("sessions_mom", 0),
            engagement_rate=round(float(kpi.get("engagement_rate", 0)) * 100, 1),
            inquiries=int(kpi.get("inquiries", 0)),
            downloads=int(kpi.get("downloads", 0)),
            contact_cr=round(float(kpi.get("contact_cr", 0)) * 100, 2),
            step1_to_2_pct=funnel.get("step1_to_2_pct", "N/A"),
            step2_to_3_pct=funnel.get("step2_to_3_pct", "N/A"),
            step3_to_4_pct=funnel.get("step3_to_4_pct", "N/A"),
            step4_to_5_pct=funnel.get("step4_to_5_pct", "N/A"),
            overall_inquiry_cvr_pct=funnel.get("overall_inquiry_cvr_pct", "N/A"),
            top_pages_table=top_pages_table,
            channel_table=channel_table,
        )

    @staticmethod
    def _df_to_markdown(df: "pd.DataFrame") -> str:
        """DataFrameをMarkdown表に変換"""
        if df.empty:
            return "（データなし）"
        lines = ["| " + " | ".join(str(c) for c in df.columns) + " |"]
        lines.append("| " + " | ".join(["---"] * len(df.columns)) + " |")
        for _, row in df.iterrows():
            lines.append("| " + " | ".join(str(v) for v in row.values) + " |")
        return "\n".join(lines)
