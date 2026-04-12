"""
natural_language_qa.py
サービス③: AI自然言語分析環境
「どのページが離脱多い？」などの質問にBQデータを引いてAIが即回答する
"""
from __future__ import annotations

import os
import yaml
from openai import OpenAI
from google.cloud import bigquery


def _load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# 質問の意図からどのBQテーブルを引くかを決定する関数群
def _get_context_data(question: str, bq_client: bigquery.Client, project_id: str) -> str:
    """質問内容に応じてBQからコンテキストデータを取得"""
    q = question.lower()

    # キーワードマッピング
    fetch_page = any(k in q for k in ["ページ", "page", "url", "コンテンツ", "記事", "スクロール", "離脱", "閲覧"])
    fetch_channel = any(k in q for k in ["チャネル", "流入", "経路", "organic", "direct", "検索", "参照"])
    fetch_funnel = any(k in q for k in ["ファネル", "フォーム", "問い合わせ", "cv", "コンバージョン", "送信"])
    fetch_kpi = any(k in q for k in ["セッション", "訪問", "ユーザー", "kpi", "目標", "今月", "先月", "傾向"])

    contexts = []

    if fetch_kpi or (not fetch_page and not fetch_channel and not fetch_funnel):
        df = bq_client.query(f"""
            SELECT report_date, sessions, users, pageviews,
                   ROUND(engagement_rate*100,1) AS engagement_rate_pct,
                   contact_form_submissions,
                   ROUND(overall_cvr*100,2) AS overall_cvr_pct
            FROM `{project_id}.marts.daily_kpi_summary`
            ORDER BY report_date DESC LIMIT 14
        """).to_dataframe()
        if not df.empty:
            contexts.append("【日次KPI（直近14日）】\n" + df.to_string(index=False))

    if fetch_page:
        df = bq_client.query(f"""
            SELECT page_path, SUM(pageviews) AS pageviews,
                   ROUND(AVG(avg_time_on_page_sec),1) AS avg_time_sec,
                   ROUND(AVG(scroll_90pct_rate)*100,1) AS scroll_90pct_pct,
                   SUM(conversions_from_page) AS conversions
            FROM `{project_id}.marts.page_performance`
            GROUP BY page_path
            ORDER BY pageviews DESC LIMIT 15
        """).to_dataframe()
        if not df.empty:
            contexts.append("【ページ別パフォーマンス（全期間合計）】\n" + df.to_string(index=False))

    if fetch_channel:
        df = bq_client.query(f"""
            SELECT report_month, channel_grouping, sessions,
                   ROUND(conversion_rate*100,2) AS cvr_pct,
                   ROUND(engagement_rate*100,1) AS eng_rate_pct
            FROM `{project_id}.marts.channel_kpi_monthly`
            ORDER BY report_month DESC, sessions DESC
        """).to_dataframe()
        if not df.empty:
            contexts.append("【チャネル別月次KPI】\n" + df.to_string(index=False))

    if fetch_funnel:
        df = bq_client.query(f"""
            SELECT report_date, step1_sessions, step2_service_view,
                   step3_contact_page, step4_form_start, step5_submission,
                   ROUND(overall_inquiry_cvr*100,2) AS inquiry_cvr_pct
            FROM `{project_id}.marts.conversion_funnel_daily`
            ORDER BY report_date DESC LIMIT 14
        """).to_dataframe()
        if not df.empty:
            contexts.append("【ファネル進行状況（直近14日）】\n" + df.to_string(index=False))

    return "\n\n".join(contexts) if contexts else "（データ取得できませんでした）"


class NaturalLanguageQA:
    """
    自然言語でGA4データに質問できるAIアナリスト

    使い方:
        qa = NaturalLanguageQA()
        answer = qa.ask("どのページが一番離脱が多いですか？")
        print(answer)
    """

    SYSTEM_PROMPT = (
        "あなたはGA4データを専門とするWebマーケティングアナリストです。\n"
        "以下の実際のGA4 BQデータを根拠に、日本語で具体的・簡潔に回答してください。\n"
        "- 数字を必ず引用する\n"
        "- 改善提案がある場合は必ず1つ以上追加する\n"
        "- データにない推測・誇張はしない\n"
        "- 回答は400文字以内"
    )

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

    def ask(self, question: str) -> str:
        """
        自然言語の質問に対してBQデータを引いてAIが回答する
        question: 日本語の質問文
        """
        # 1. 質問に関連するBQデータを取得
        context = _get_context_data(question, self.bq, self.project_id)

        # 2. プロンプト組み立て
        user_prompt = f"【データ】\n{context}\n\n【質問】\n{question}"

        # 3. OpenAI呼び出し
        response = self.openai.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=600,
            temperature=0.3,
        )
        return response.choices[0].message.content or ""

    def interactive(self) -> None:
        """対話モード（CLIで直接使う場合）"""
        print("=== GA4 AI自然言語アナリスト ===")
        print("質問を入力してください（'exit' で終了）\n")
        while True:
            try:
                q = input("質問> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n終了します")
                break
            if q.lower() in ("exit", "quit", "終了"):
                print("終了します")
                break
            if not q:
                continue
            print("\n分析中...\n")
            try:
                answer = self.ask(q)
                print(f"回答:\n{answer}\n")
                print("-" * 50)
            except Exception as e:
                print(f"エラー: {e}\n")


if __name__ == "__main__":
    qa = NaturalLanguageQA()
    qa.interactive()
