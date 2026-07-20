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


from src._config_loader import (
    get_kpi_targets,
    get_project_id,
    load_config as _load_config,
    make_bq_client,
)


# 質問の意図からどのBQテーブルを引くかを決定する関数群
def _get_context_data(question: str, bq_client: bigquery.Client, project_id: str) -> str:
    """質問内容に応じてBQからコンテキストデータを取得"""
    q = question.lower()

    # キーワードマッピング
    fetch_page = any(k in q for k in ["ページ", "page", "url", "コンテンツ", "記事", "スクロール", "離脱", "閲覧"])
    fetch_channel = any(k in q for k in ["チャネル", "流入", "経路", "organic", "direct", "検索", "参照"])
    fetch_funnel = any(k in q for k in ["ファネル", "フォーム", "問い合わせ", "cv", "コンバージョン", "送信"])
    fetch_kpi = any(k in q for k in ["セッション", "訪問", "ユーザー", "kpi", "目標", "今月", "先月", "傾向",
                                     "kgi", "達成", "進捗", "ペース"])

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
        # 2026-07-13 検収前検証: app.py と同一の月次KPI集計を供給（今月vs先月の比較用・ratio of sums）
        df = bq_client.query(f"""
            SELECT FORMAT_DATE('%Y-%m', report_date) AS report_month,
                   MIN(report_date) AS period_start, MAX(report_date) AS period_end,
                   SUM(sessions) AS sessions,
                   SUM(contact_form_submissions) AS inquiries,
                   ROUND(SAFE_DIVIDE(SUM(contact_form_submissions)+SUM(document_downloads), SUM(sessions))*100,2) AS overall_cvr_pct
            FROM `{project_id}.marts.daily_kpi_summary`
            WHERE report_date >= DATE_TRUNC(DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 2 MONTH), MONTH)
            GROUP BY report_month ORDER BY report_month DESC
        """).to_dataframe()
        if not df.empty:
            contexts.append("【月次KPI集計（直近3ヶ月・確定値／最新月は月途中まで）】\n" + df.to_string(index=False))
        # 2026-07-20: 客様確定KPI目標（settings.yaml kpi_targets＝SSOT）に対する当月達成率。
        # app.py と同一定義（片経路だけ実装すると「画面で答えられる質問がCLIで答えられない」
        # 定義ドリフトになる＝tests/test_kpi_targets.py が両経路を強制）。
        t = get_kpi_targets()
        df = bq_client.query(f"""
            SELECT
              FORMAT_DATE('%Y-%m', MAX(report_date)) AS report_month,
              MIN(report_date) AS period_start, MAX(report_date) AS period_end,
              SUM(sessions) AS sessions,
              {t['monthly_sessions']} AS sessions_target,
              ROUND(SAFE_DIVIDE(SUM(sessions), {t['monthly_sessions']})*100,1) AS sessions_achieved_pct,
              SUM(contact_form_submissions) AS inquiries,
              {t['monthly_inquiries']} AS inquiries_target,
              ROUND(SAFE_DIVIDE(SUM(contact_form_submissions), {t['monthly_inquiries']})*100,1) AS inquiries_achieved_pct,
              SUM(document_downloads) AS downloads,
              {t['monthly_downloads']} AS downloads_target,
              ROUND(SAFE_DIVIDE(SUM(document_downloads), {t['monthly_downloads']})*100,1) AS downloads_achieved_pct
            FROM `{project_id}.marts.daily_kpi_summary`
            WHERE report_date >= DATE_TRUNC(CURRENT_DATE('Asia/Tokyo'), MONTH)
        """).to_dataframe()
        if not df.empty:
            contexts.append("【KPI目標と当月達成率（確定値・月途中）】\n" + df.to_string(index=False))

    if fetch_page:
        # 2026-07-10 R10-C 横断整合: app.py と同一（Lookerページ別と同定義）。
        # 日次grain × ratio of sums × 定義書準拠列（cta_click_sessions/unique_pageviews/
        # inquiry_cv_sessions）に統一し「同名指標で画面ごとに数値が違う」を防ぐ。
        df = bq_client.query(f"""
            SELECT page_path, SUM(pageviews) AS pageviews,
                   ROUND(SAFE_DIVIDE(SUM(avg_time_on_page_sec * pageviews), SUM(pageviews)),1) AS avg_time_sec,
                   ROUND(SAFE_DIVIDE(SUM(scroll_90pct_count), SUM(pageviews))*100,1) AS scroll_90pct_pct,
                   ROUND(SAFE_DIVIDE(SUM(cta_click_sessions), SUM(unique_pageviews))*100,2) AS cta_click_rate_pct,
                   SUM(inquiry_cv_sessions) AS conversions
            FROM `{project_id}.marts.page_performance_daily`
            GROUP BY page_path
            ORDER BY pageviews DESC LIMIT 15
        """).to_dataframe()
        if not df.empty:
            contexts.append("【ページ別パフォーマンス（全期間合計）】\n" + df.to_string(index=False))

    if fetch_channel:
        # R10-C 横断整合: CV率は定義書準拠「お問い合わせ完了のみ」（inquiry_conversion_rate）。
        df = bq_client.query(f"""
            SELECT report_month, channel_grouping, sessions,
                   inquiry_conversions AS conversions,
                   ROUND(inquiry_conversion_rate*100,2) AS cvr_pct,
                   ROUND(engagement_rate*100,1) AS eng_rate_pct
            FROM `{project_id}.marts.channel_kpi_monthly`
            ORDER BY report_month DESC, sessions DESC
        """).to_dataframe()
        if not df.empty:
            contexts.append("【チャネル別月次KPI】\n" + df.to_string(index=False))

    if fetch_funnel:
        df = bq_client.query(f"""
            -- 2026-06-23 検収R7-③: app.py と同一の包含定義(incl)へ統一。
            -- 旧 step3_contact_page/step4_form_start（独立カウント）は非単調(送信完了>入力開始)で
            -- Looker/総合ビュー(incl)と食い違うため、incl版へ揃える。
            SELECT report_date, step1_sessions,
                   step2b_service_view AS step2_service_view,
                   step3_contact_reach_incl AS step3_contact_page,
                   step4_form_start_incl AS step4_form_start,
                   step5_submission,
                   ROUND(overall_inquiry_cvr*100,2) AS inquiry_cvr_pct
            FROM `{project_id}.marts.conversion_funnel_daily`
            ORDER BY report_date DESC LIMIT 14
        """).to_dataframe()
        if not df.empty:
            contexts.append("【ファネル進行状況（直近14日）】\n" + df.to_string(index=False))
        # 2026-07-13 検収前検証: app.py と同一のファネル期間集計（確定値）を供給。
        # AIが日次14行を自力合算して件数を誤る事故を防ぐ（率はratio of sums）。
        df = bq_client.query(f"""
            SELECT
              MIN(report_date) AS period_start, MAX(report_date) AS period_end,
              SUM(step1_sessions) AS step1_sessions,
              SUM(step2b_service_view) AS step2_service_view,
              SUM(step3_contact_reach_incl) AS step3_contact_page,
              SUM(step4_form_start_incl) AS step4_form_start,
              SUM(step5_submission) AS step5_submission,
              ROUND(SAFE_DIVIDE(SUM(step5_submission), SUM(step1_sessions))*100,2)          AS inquiry_cvr_pct,
              ROUND(SAFE_DIVIDE(SUM(step4_form_start_incl), SUM(step3_contact_reach_incl))*100,2) AS step3_to4_rate_pct,
              ROUND(SAFE_DIVIDE(SUM(step5_submission), SUM(step4_form_start_incl))*100,2)   AS step4_to5_rate_pct
            FROM (
              SELECT * FROM `{project_id}.marts.conversion_funnel_daily`
              ORDER BY report_date DESC LIMIT 14
            )
        """).to_dataframe()
        if not df.empty:
            contexts.append("【ファネル直近14日 期間集計（確定値）】\n" + df.to_string(index=False))

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
        "- 回答は400文字以内\n"
        "- 期間の件数・率（ファネル各ステップ・離脱数・完了率・CVR）は"
        "『期間集計（確定値）』の行があればその値をそのまま引用し、日次行を自分で合算しない\n"
        "- 今月と先月の比較は『月次KPI集計』の行を使う（最新月は月途中までの集計と添える）\n"
        "- 数値を引用するときは必ず対象期間を明記する（例: 全期間累計／直近14日／2026年6月）\n"
        "\n【KPI/KGI目標と達成率（2026-07-16 客様確定値）】\n"
        "- 目標値と当月達成率は『KPI目標と当月達成率（確定値・月途中）』の行の値をそのまま引用し、"
        "目標値を自分で記憶・推定・再計算しない\n"
        "- この行は当月1日〜直近確定日の累計（月途中）＝達成率には必ず集計期間を添え、"
        "月末着地の予測と混同しない（ペースに触れる場合は単純換算と明示する）\n"
        "- KGI『パートナー契約数（月3件）』はGA4に含まれない社内成果指標のため実績を算出できない。"
        "問われたら目標値の存在のみ伝え、御社実績との突合が必要と案内する（推定値を出さない）\n"
        "\n【客様の正式指標定義（アーク事業部 定義書準拠・必ずこの定義で回答する）】\n"
        "- セッション数 ＝ 全ページ訪問回数（GA4セッション数）\n"
        "- お問い合わせ送信数 ＝ 完了ページ(/contact/?mode=finish)に到達したセッション数\n"
        "- 全体CVR ＝ (お問い合わせ送信数＋資料DL数) ÷ セッション数 ×100\n"
        "- お問い合わせCVR ＝ お問い合わせ送信数 ÷ セッション数 ×100\n"
        "- 資料ダウンロードCVR ＝ 資料DL数 ÷ セッション数 ×100（資料DLは現状0件）\n"
        "- 直帰率 ＝ エンゲージドでないセッション ÷ 全セッション ×100\n"
        "- 新規ユーザー率 ＝ 新規ユーザー数 ÷ 全ユーザー数\n"
        "- エンゲージメント率 ＝ エンゲージドセッション ÷ セッション数\n"
        "- 新規/リピーター ＝ セッション単位の初回/再訪の割合\n"
        "- ファネル(お問い合わせのみ): STEP1 全訪問(全セッション=100%)／"
        "STEP2 サービス閲覧(/service/閲覧セッション÷全セッション)／"
        "STEP3 お問い合わせページ(/contact/到達セッション)／"
        "STEP4 フォーム入力開始(form_startイベント)／"
        "STEP5 送信完了(完了ページ到達セッション)\n"
        "- 単に『CVR』と言われたら『全体CVR』を指す。用途で『お問い合わせCVR』か迷う場合は両方の定義を添える。\n"
        "- 『完了率』など定義書に固有名のない語を問われたら、勝手に独自定義せず、"
        "最も近い定義済み指標（例: 入力開始→送信完了率、または問い合わせCVR）に対応づけ、"
        "どの定義で答えたかを必ず明記する。\n"
        "\n【ファネルの構造（重要・解釈を誤らないこと）】\n"
        "- ファネルの各ステップの数値は『そのステップに到達したセッション数』であり、"
        "前のステップを必ず通過した人数ではない。\n"
        "- 特に『サービスページ閲覧(step2)』と『お問い合わせページ(step3)』は、"
        "それぞれ独立に数えた到達セッション数（並列の到達指標）であって、直列の通過順ではない。\n"
        "- ユーザーはサービスページを見ずに、広告・検索・直接アクセスから"
        "直接お問い合わせページへ到達することもある。全員がサービス閲覧を経由する前提は誤り。\n"
        "- よって『step1とstep2の数の差』を根拠に『最初の段階で離脱が多い』と結論づけてはいけない。\n"
        "- 数の大小（前段≧後段の単調減少）が定義上保証されるのは"
        "『お問い合わせページ到達(step3)≧フォーム入力開始(step4)≧送信完了(step5)』の区間のみ。"
        "離脱・改善余地はこの区間で評価する。\n"
        "- 『どのステップで最も離脱が多いか』を問われたら、"
        "『お問い合わせ到達→入力開始』と『入力開始→送信完了』の各区間について、"
        "離脱セッション数（前段−後段）と離脱率（1−後段÷前段）を両方求めて答える。"
        "離脱数が最多の区間と離脱率が最悪の区間が食い違う場合は、"
        "どちらの物差しで最多かを明記し両方を提示する"
        "（例: 到達→入力開始は離脱20件・50%、入力開始→送信完了は離脱12件・60%）。"
        "片方の物差しだけを根拠に『最も離脱が多い』と断定しない。\n"
        "- 離脱率と完了率を混同しないこと。『入力開始→送信完了率』(step4_to5_rate_pct)等は"
        "“完了率（通過率）”であって離脱率ではない。区間の離脱率＝100−完了率"
        "（例: 完了率40%なら離脱率は60%）。完了率をそのまま離脱率として引用しない。\n"
        "- 全体の問い合わせ転換率は『問い合わせCVR(%)』を用いる。\n"
        "- ページ別の『conversions（ページ経由CV数）』は“そのページを閲覧して最終的に"
        "お問い合わせ完了に至ったセッション数”。1セッションが複数ページに計上されるため"
        "ページ間で合算して総CV数として扱わない。\n"
        "- 回答では step1_sessions のような内部の英語カラム名をそのまま出さず、"
        "日本語のステップ名（お問い合わせページ到達、フォーム入力開始 等）で説明する。"
    )

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or _load_config()
        self.project_id = get_project_id(self.config)

        key_path = self.config["gcp"].get("service_account_key", "")
        if key_path and os.path.exists(key_path):
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(key_path)
            self.bq = make_bq_client(self.project_id, credentials=creds)
        else:
            # quota project を project_id に固定（ローカルADC汚染による403を防止）
            self.bq = make_bq_client(self.project_id)

        api_key = os.environ.get("ARK_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise EnvironmentError("ARK_OPENAI_API_KEY または OPENAI_API_KEY が環境変数に設定されていません")
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
