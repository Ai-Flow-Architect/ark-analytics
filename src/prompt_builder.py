"""
prompt_builder.py
KPIデータからOpenAI APIへのプロンプトを組み立てるモジュール
"""
from __future__ import annotations

import os
import textwrap

import pandas as pd

from src._config_loader import get_kpi_targets


class PromptBuilder:
    """KPIデータ → 分析プロンプト変換

    KPI目標値は settings.yaml (kpi_targets) をSSOTとして参照する。
    ハードコード禁止（2026-07-08 目標9→6変更漏れ事故の再発防止）。
    """

    def __init__(self, config: dict | None = None) -> None:
        targets = get_kpi_targets(config)
        self.sessions_target = targets["monthly_sessions"]
        self.inquiry_target = targets["monthly_inquiries"]
        self.contracts_target = targets["monthly_contracts"]

    EXECUTIVE_TEMPLATE = textwrap.dedent("""\
        あなたはWebマーケティングの専門データアナリストです。
        以下の{month}のGA4データを分析し、経営層向けに簡潔なインサイトレポートを作成してください。

        ## 今月のKPIデータ
        - セッション数: {sessions:,}（目標: {sessions_target:,}、前月比: {sessions_mom:+.1f}%）
        - 目標達成率: {sessions_target_rate:.1f}%
        - エンゲージメント率: {engagement_rate:.1f}%
        - お問い合わせ数: {inquiries}件（目標: {inquiry_target}件、前月比: {inquiries_mom:+.1f}%）
        - 資料DL数: {downloads}件（前月比: {downloads_mom:+.1f}%）
        - お問い合わせCVR（問合せ完了/全セッション）: {inquiry_cvr:.2f}%（前月比: {inquiry_cvr_mom:+.1f}%）

        ## チャネル別データ
        {channel_table}

        ## ファネル状況
        - サービスページ閲覧→お問い合わせ到達率: {step2_to_3_pct}%（{service_view_total}件→{contact_reach_total}件）
        - お問い合わせ到達→フォーム入力開始率: {step3_to_4_pct}%（{contact_reach_total}件→{form_start_total}件）
        - フォーム入力開始→送信完了率: {step4_to_5_pct}%（{form_start_total}件→{submission_total}件）

        ## 目標
        - KGI: 月{contracts_target}件成約
        - KPI: 月間セッション{sessions_target:,} / お問い合わせ{inquiry_target}件

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
        - お問い合わせ数: {inquiries}件（お問い合わせCVR: {inquiry_cvr:.2f}%）
        - 資料DL数: {downloads}件

        ## ファネル詳細
        - Step1 サイト訪問: {sessions_total:,}件
        - Step2 サービスページ閲覧: {service_view_total}件（サイト訪問→サービスページ閲覧率: {step1_to_2_pct}%）
        - Step3 お問い合わせ到達: {contact_reach_total}件（サービスページ閲覧→お問い合わせ到達率: {step2_to_3_pct}%）
        - Step4 フォーム入力開始: {form_start_total}件（お問い合わせ到達→フォーム入力開始率: {step3_to_4_pct}%）
        - Step5 フォーム送信完了: {submission_total}件（フォーム入力開始→送信完了率: {step4_to_5_pct}%）
        - 全体お問い合わせCVR（サイト訪問→送信完了）: {overall_inquiry_cvr_pct}%

        ## 主要ページパフォーマンス（上位5ページ）
        {top_pages_table}
        ※ conversions は「そのページを閲覧して最終的にお問い合わせ完了に至ったセッション数（ページ経由CV数）」。
          1セッションが複数ページを閲覧して完了すると閲覧した各ページに1ずつ計上されるため、
          ページ間で合算して総CV数として扱わないこと（総数はKPIサマリーのお問い合わせ数）。
          cta_click_rate_pct は「CTAクリックセッション÷ページ閲覧セッション」（セッション単位）。

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
        sessions_target_rate = (
            (kpi.get("sessions", 0) / self.sessions_target * 100) if kpi.get("sessions") else 0
        )

        return self.EXECUTIVE_TEMPLATE.format(
            month=month,
            sessions_target=self.sessions_target,
            inquiry_target=self.inquiry_target,
            contracts_target=self.contracts_target,
            sessions=int(kpi.get("sessions", 0)),
            sessions_mom=mom.get("sessions_mom", 0),
            sessions_target_rate=sessions_target_rate,
            engagement_rate=round(float(kpi.get("engagement_rate", 0)) * 100, 1),
            inquiries=int(kpi.get("inquiries", 0)),
            inquiries_mom=mom.get("inquiries_mom", 0),
            downloads=int(kpi.get("downloads", 0)),
            downloads_mom=mom.get("downloads_mom", 0),
            inquiry_cvr=round(float(kpi.get("inquiry_cvr", 0) or 0) * 100, 2),
            inquiry_cvr_mom=mom.get("inquiry_cvr_mom", 0),
            channel_table=channel_table,
            service_view_total=self._funnel_int(funnel, "service_view_total"),
            contact_reach_total=self._funnel_int(funnel, "contact_reach_total"),
            form_start_total=self._funnel_int(funnel, "form_start_total"),
            submission_total=self._funnel_int(funnel, "submission_total"),
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
            inquiry_cvr=round(float(kpi.get("inquiry_cvr", 0) or 0) * 100, 2),
            sessions_total=self._funnel_int(funnel, "sessions_total"),
            service_view_total=self._funnel_int(funnel, "service_view_total"),
            contact_reach_total=self._funnel_int(funnel, "contact_reach_total"),
            form_start_total=self._funnel_int(funnel, "form_start_total"),
            submission_total=self._funnel_int(funnel, "submission_total"),
            step1_to_2_pct=funnel.get("step1_to_2_pct", "N/A"),
            step2_to_3_pct=funnel.get("step2_to_3_pct", "N/A"),
            step3_to_4_pct=funnel.get("step3_to_4_pct", "N/A"),
            step4_to_5_pct=funnel.get("step4_to_5_pct", "N/A"),
            overall_inquiry_cvr_pct=funnel.get("overall_inquiry_cvr_pct", "N/A"),
            top_pages_table=top_pages_table,
            channel_table=channel_table,
        )

    @staticmethod
    def _funnel_int(funnel: dict, key: str) -> int:
        """ファネル実数値を安全にint化（欠損・None・NaNは0）"""
        val = funnel.get(key)
        try:
            return int(val)
        except (TypeError, ValueError):
            return 0

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
