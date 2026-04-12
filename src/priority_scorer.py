"""
priority_scorer.py
サービス④: 改善施策の優先順位スコアリング
インパクト × 工数 × 実行可能性の3軸でLLMが自動判断・出力する
"""
from __future__ import annotations

import json
import os
import yaml
from openai import OpenAI
from google.cloud import bigquery


def _load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


SCORING_SYSTEM_PROMPT = """\
あなたはWebサイト改善の優先順位付けの専門家です。
以下のGA4データとページ一覧を分析し、改善施策をJSON形式で出力してください。

出力フォーマット（必ず以下のJSON形式で返す。キー名は "actions" で配列を持つこと）:
{
  "actions": [
    {
      "rank": 1,
      "page_or_area": "改善対象のページ・エリア",
      "issue": "現在の課題",
      "action": "具体的な改善アクション",
      "impact_score": 1~5,
      "effort_score": 1~5,
      "feasibility_score": 1~5,
      "priority_score": "(impact*2 + feasibility - effort) で計算した数値",
      "expected_outcome": "期待される改善効果"
    },
    ...
  ]
}

スコア定義:
- impact_score: CVや訪問数への影響度（5=最大）
- effort_score: 実装コスト・工数（5=最大。低いほど優先度UP）
- feasibility_score: GA4・CSS・コンテンツ改善で実現可能か（5=最大）
- priority_score: impact×2 + feasibility - effort（自動計算）

上位5施策を出力すること。マーケティング部門の担当者が今週から実行できる粒度で書くこと。
"""


class PriorityScorer:
    """
    GA4データからLLMが改善施策の優先順位を自動スコアリング
    サービス④の核心機能

    使い方:
        scorer = PriorityScorer()
        result = scorer.score()
        print(result)
    """

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or _load_config()
        self.project_id = self.config["gcp"]["project_id"]

        key_path = self.config["gcp"].get("service_account_key", "")
        if key_path and os.path.exists(key_path):
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(key_path)
            self.bq = bigquery.Client(project=self.project_id, credentials=creds)
        else:
            self.bq = bigquery.Client(project=self.project_id)

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY が環境変数に設定されていません")
        self.openai = OpenAI(api_key=api_key)
        self.model = self.config["report"].get("openai_model", "gpt-4o")

    def _fetch_data(self) -> str:
        """BQから分析用データを取得してテキスト化"""
        # KPIサマリー
        kpi_df = self.bq.query(f"""
            SELECT report_date, sessions, pageviews,
                   ROUND(engagement_rate*100,1) AS eng_pct,
                   contact_form_submissions,
                   ROUND(overall_cvr*100,2) AS cvr_pct
            FROM `{self.project_id}.marts.daily_kpi_summary`
            ORDER BY report_date DESC LIMIT 7
        """).to_dataframe()

        # ページ別（離脱・スクロール・CTA）
        page_df = self.bq.query(f"""
            SELECT page_path,
                   SUM(pageviews) AS pv,
                   ROUND(AVG(avg_time_on_page_sec),1) AS avg_sec,
                   ROUND(AVG(scroll_90pct_rate)*100,1) AS scroll_90pct,
                   ROUND(AVG(cta_click_rate)*100,1) AS cta_ctr,
                   SUM(conversions_from_page) AS cvs
            FROM `{self.project_id}.marts.page_performance`
            GROUP BY page_path
            ORDER BY pv DESC LIMIT 10
        """).to_dataframe()

        # ファネル
        funnel_df = self.bq.query(f"""
            SELECT
                ROUND(AVG(step1_sessions),0) AS avg_sessions,
                ROUND(AVG(step2_service_view),0) AS avg_service_view,
                ROUND(AVG(step3_contact_page),0) AS avg_contact,
                ROUND(AVG(step4_form_start),0) AS avg_form_start,
                ROUND(AVG(step5_submission),0) AS avg_submit,
                ROUND(AVG(step1_to_2_rate)*100,1) AS rate_1to2,
                ROUND(AVG(step2_to_3_rate)*100,1) AS rate_2to3,
                ROUND(AVG(step3_to_4_rate)*100,1) AS rate_3to4,
                ROUND(AVG(step4_to_5_rate)*100,1) AS rate_4to5
            FROM `{self.project_id}.marts.conversion_funnel_daily`
        """).to_dataframe()

        return (
            f"【日次KPI（直近7日）】\n{kpi_df.to_string(index=False)}\n\n"
            f"【ページ別パフォーマンス（全期間）】\n{page_df.to_string(index=False)}\n\n"
            f"【ファネル平均】\n{funnel_df.to_string(index=False)}"
        )

    def score(self) -> list[dict]:
        """
        改善施策を優先順位付きでスコアリングして返す
        戻り値: 施策リスト（rank順）
        """
        data_context = self._fetch_data()
        user_prompt = f"以下のGA4データを分析して改善施策の優先順位を出力してください。\n\n{data_context}"

        response = self.openai.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SCORING_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1500,
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(raw)

        # リストが直接返った場合
        if isinstance(parsed, list):
            return parsed
        # 既知キーにリストが入っている場合
        for key in ("items", "actions", "result", "施策", "recommendations", "施策リスト", "data"):
            if key in parsed and isinstance(parsed[key], list):
                return parsed[key]
        # 全値がdictの場合（{"1":{...}, "2":{...}} 形式）→ values をリストに変換
        all_vals = list(parsed.values())
        if all_vals and all(isinstance(v, dict) for v in all_vals):
            return all_vals
        # 最初の値がリストの場合
        first_val = all_vals[0] if all_vals else []
        if isinstance(first_val, list):
            return first_val
        return []

    def print_table(self) -> None:
        """スコアリング結果をテーブル形式で表示"""
        items = self.score()
        if not items:
            print("スコアリング結果が取得できませんでした")
            return

        print("\n=== 改善施策 優先順位スコアリング ===\n")
        header = f"{'順位':>3} | {'対象':20} | {'課題':20} | {'アクション':25} | 優先度 | 期待効果"
        print(header)
        print("-" * len(header))

        for item in items:
            rank = item.get("rank", "?")
            target = str(item.get("page_or_area", ""))[:20]
            issue = str(item.get("issue", ""))[:20]
            action = str(item.get("action", ""))[:25]
            score = item.get("priority_score", "?")
            outcome = str(item.get("expected_outcome", ""))[:30]
            print(f"{rank:>3} | {target:20} | {issue:20} | {action:25} | {score:>6} | {outcome}")

        print()


if __name__ == "__main__":
    scorer = PriorityScorer()
    scorer.print_table()
