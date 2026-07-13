"""
GA4 AI チャットアナリスト — ARK Analytics
会話形式でGA4データについてAIに質問できるStreamlit Webアプリ
"""
from __future__ import annotations

import os
import sys
import yaml
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

st.set_page_config(
    page_title="GA4 AI チャット | ARK Analytics",
    page_icon="📊",
    layout="wide",
)

PRIMARY = "#1a56db"

EXAMPLE_QUESTIONS = {
    "📄 ページ分析": [
        "どのページが一番離脱が多いですか？",
        "スクロール到達率が低いページはどこですか？",
        "コンバージョンに貢献しているページを教えてください",
    ],
    "📣 チャネル分析": [
        "どの流入チャネルのCVRが最も高いですか？",
        "オーガニック検索のトレンドを教えてください",
        "チャネル別にエンゲージメント率を比較してください",
    ],
    "🔄 ファネル分析": [
        "フォームのどのステップで最も離脱しますか？",
        "問い合わせフォームの完了率はどのくらいですか？",
        "今月のCVRは先月と比べてどうですか？",
    ],
    "📈 KPI確認": [
        "今月のセッション数の傾向はどうですか？",
        "先週のエンゲージメント率を教えてください",
        "今週の改善ポイントをまとめてください",
    ],
}

# 列名の日本語変換マッピング
COLUMN_JA = {
    "report_date":              "日付",
    "report_month":             "月",
    "sessions":                 "セッション数",
    "users":                    "ユーザー数",
    "new_users":                "新規ユーザー数",
    "engaged_sessions":         "エンゲージドセッション数",
    "pageviews":                "ページビュー数",
    "engagement_rate_pct":      "エンゲージメント率(%)",
    "new_user_rate_pct":        "新規ユーザー率(%)",
    "bounce_rate_pct":          "直帰率(%)",
    "contact_form_submissions": "問い合わせ件数",
    "overall_cvr_pct":          "コンバージョン率(%)",
    "period_start":             "期間開始",
    "period_end":               "期間終了",
    "inquiries":                "問い合わせ件数",
    "page_path":                "ページパス",
    "avg_time_sec":             "平均滞在時間(秒)",
    "scroll_90pct_pct":         "スクロール90%到達率(%)",
    "cta_click_rate_pct":       "CTAクリック率(%)",
    "conversions":              "コンバージョン数",
    "channel_grouping":         "チャネル",
    "cvr_pct":                  "CVR(%)",
    "eng_rate_pct":             "エンゲージメント率(%)",
    "step1_sessions":           "Step1: セッション開始",
    "step2_service_view":       "Step2: サービスページ閲覧",
    "step3_contact_page":       "Step3: お問い合わせページ",
    "step4_form_start":         "Step4: フォーム入力開始",
    "step5_submission":         "Step5: フォーム送信完了",
    "inquiry_cvr_pct":          "問い合わせCVR(%)",
    "step3_to4_rate_pct":       "お問い合わせ到達→入力開始率(%)",
    "step4_to5_rate_pct":       "入力開始→送信完了率(%)",
    "dimension_type":           "分類軸",
    "dimension_value":          "内訳",
}

# 流入・ページ内訳の分類軸 日本語ラベル
DIMENSION_TYPE_JA = {
    "channel":       "チャネル",
    "search_engine": "検索エンジン",
    "referral":      "参照元サイト",
    "landing_page":  "ランディングページ",
    "exit_page":     "離脱ページ",
    "device":        "デバイス",
    "user_type":     "新規/リピーター",
}


def _ja(df: pd.DataFrame) -> pd.DataFrame:
    """DataFrameの列名を日本語に変換"""
    return df.rename(columns=COLUMN_JA)


def _col_config(df: pd.DataFrame) -> dict:
    """st.dataframe用 column_config（表示名を日本語化）"""
    return {
        k: st.column_config.Column(label=v)
        for k, v in COLUMN_JA.items()
        if k in df.columns
    }


st.markdown(f"""
<style>
  .header-block {{
    background: linear-gradient(135deg, #0f4c81 0%, {PRIMARY} 60%, #2563eb 100%);
    color: white; padding: 28px 32px 22px; border-radius: 14px; margin-bottom: 24px;
    box-shadow: 0 4px 16px rgba(26,86,219,0.18);
  }}
  .header-block h1 {{ font-size: 26px; font-weight: 700; margin: 0 0 6px 0; letter-spacing: -0.3px; }}
  .header-block p  {{ font-size: 13px; opacity: 0.85; margin: 0; }}
  .section-label {{
    font-size: 11px; font-weight: 700; color: #64748b;
    letter-spacing: 1.5px; text-transform: uppercase;
    margin-top: 18px; margin-bottom: 6px;
    padding-left: 4px; border-left: 3px solid {PRIMARY};
  }}
  .chart-title {{
    font-size: 13px; font-weight: 600; color: #374151;
    margin: 12px 0 4px 0;
  }}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="header-block">
  <h1>📊 GA4 AI チャットアナリスト</h1>
  <p>ARK Analytics — データについて日本語で自由にチャットしてください。BigQuery × GPT-4o で即回答します。</p>
</div>
""", unsafe_allow_html=True)

# ── セッション初期化 ────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_question" not in st.session_state:
    st.session_state.pending_question = ""


# ── BQ + OpenAI 初期化（起動時1回） ────────────────────────────
@st.cache_resource(show_spinner=False)
def _init_clients():
    config_path = os.path.join(os.path.dirname(__file__), "config", "settings.yaml")
    try:
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except FileNotFoundError:
        st.error(f"❌ 設定ファイルが見つかりません: {config_path}")
        st.stop()

    from src._config_loader import get_project_id
    # Streamlit Cloud secrets を環境変数に流し込む（get_project_id が読めるように）
    if "ARK_GCP_PROJECT_ID" in st.secrets and not os.environ.get("ARK_GCP_PROJECT_ID"):
        os.environ["ARK_GCP_PROJECT_ID"] = str(st.secrets["ARK_GCP_PROJECT_ID"])
    # フォールバック: SAキー(gcp_service_account)内の project_id から解決
    # （Streamlit Cloud Secrets に ARK_GCP_PROJECT_ID が無い環境でも起動可能にする）
    if not os.environ.get("ARK_GCP_PROJECT_ID") and "gcp_service_account" in st.secrets:
        sa_project = str(dict(st.secrets["gcp_service_account"]).get("project_id", "") or "")
        if sa_project:
            os.environ["ARK_GCP_PROJECT_ID"] = sa_project
    try:
        project_id = get_project_id(cfg)
    except RuntimeError as e:
        st.error(f"❌ GCPプロジェクトIDが解決できません: {e}")
        st.stop()

    from google.cloud import bigquery

    if "gcp_service_account" in st.secrets:
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]),
            scopes=["https://www.googleapis.com/auth/bigquery"],
        )
        bq = bigquery.Client(project=project_id, credentials=creds)
    else:
        bq = bigquery.Client(project=project_id)

    api_key = (
        st.secrets.get("OPENAI_API_KEY", "")
        or os.environ.get("OPENAI_API_KEY", "")
    )
    if not api_key:
        st.error("❌ OPENAI_API_KEY が設定されていません。Streamlit Secrets を確認してください。")
        st.stop()

    from openai import OpenAI
    return bq, OpenAI(api_key=api_key), project_id, cfg


# ── BQ データ取得 ───────────────────────────────────────────────
def _fetch_data(question: str, bq, project_id: str) -> dict[str, pd.DataFrame]:
    q = question.lower()
    fetch_page    = any(k in q for k in ["ページ", "page", "url", "スクロール", "離脱", "閲覧", "コンテンツ"])
    fetch_channel = any(k in q for k in ["チャネル", "流入", "経路", "organic", "direct", "検索"])
    fetch_funnel  = any(k in q for k in ["ファネル", "フォーム", "問い合わせ", "cv", "コンバージョン", "送信"])
    fetch_kpi     = any(k in q for k in ["セッション", "訪問", "ユーザー", "kpi", "今月", "先月", "傾向", "エンゲージ"])
    fetch_traffic = any(k in q for k in [
        "検索エンジン", "google", "yahoo", "bing", "リファラ", "referral", "参照",
        "流入元", "ランディング", "離脱", "デバイス", "スマホ", "モバイル", "新規", "リピー",
    ])
    if not any([fetch_page, fetch_channel, fetch_funnel, fetch_kpi, fetch_traffic]):
        fetch_kpi = True

    results: dict[str, pd.DataFrame] = {}

    def _q(sql: str, label: str) -> None:
        # BQコールドスタート等の一過性エラーに備えて1回だけ自動リトライ
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                job = bq.query(sql)
                df = job.result(timeout=30).to_dataframe()
                if not df.empty:
                    results[label] = df
                return
            except Exception as e:
                last_err = e
        st.warning(f"⚠️ {label} の取得に失敗しました（再試行済み）: {last_err}")

    if fetch_kpi:
        # engaged_sessions/new_users の生値も渡し、期間集計時は率を単純平均せず
        # SUM(分子)/SUM(分母)(=ratio of sums) で計算させる（Looker側の真値定義に一致）。
        _q(f"""
            SELECT report_date, sessions, users, new_users, engaged_sessions, pageviews,
                   ROUND(engagement_rate*100,1) AS engagement_rate_pct,
                   ROUND(new_user_rate*100,1) AS new_user_rate_pct,
                   ROUND(bounce_rate*100,1) AS bounce_rate_pct,
                   contact_form_submissions,
                   ROUND(overall_cvr*100,2) AS overall_cvr_pct
            FROM `{project_id}.marts.daily_kpi_summary`
            ORDER BY report_date DESC LIMIT 14
        """, "日次KPI（直近14日）")
        # 直近14日の期間集計をSQL側で確定値として渡す（AIが14行を自力合算して
        # 読み違える事故を防止。率は必ずratio of sumsでLooker値と一致させる）。
        _q(f"""
            SELECT
              MIN(report_date) AS period_start, MAX(report_date) AS period_end,
              SUM(sessions) AS sessions, SUM(users) AS users,
              ROUND(SAFE_DIVIDE(SUM(engaged_sessions), SUM(sessions))*100,2)        AS engagement_rate_pct,
              ROUND((1 - SAFE_DIVIDE(SUM(engaged_sessions), SUM(sessions)))*100,2)  AS bounce_rate_pct,
              ROUND(SAFE_DIVIDE(SUM(new_users), SUM(users))*100,2)                  AS new_user_rate_pct,
              SUM(contact_form_submissions) AS inquiries,
              ROUND(SAFE_DIVIDE(SUM(contact_form_submissions)+SUM(document_downloads), SUM(sessions))*100,2) AS overall_cvr_pct
            FROM (
              SELECT * FROM `{project_id}.marts.daily_kpi_summary`
              ORDER BY report_date DESC LIMIT 14
            )
        """, "直近14日 期間集計（確定値）")
        # 2026-07-13 検収前検証: 「今月のCVRは先月と比べて？」（サイドバー質問例）に
        # 回答できるよう、月単位のKPI集計（直近3ヶ月・ratio of sums）を供給する。
        # 6月行は Looker/月次レポートの確定値（788・49・6.22%）と同値になる。
        _q(f"""
            SELECT FORMAT_DATE('%Y-%m', report_date) AS report_month,
                   MIN(report_date) AS period_start, MAX(report_date) AS period_end,
                   SUM(sessions) AS sessions, SUM(users) AS users,
                   ROUND(SAFE_DIVIDE(SUM(engaged_sessions), SUM(sessions))*100,2)       AS engagement_rate_pct,
                   ROUND((1 - SAFE_DIVIDE(SUM(engaged_sessions), SUM(sessions)))*100,2) AS bounce_rate_pct,
                   SUM(contact_form_submissions) AS inquiries,
                   ROUND(SAFE_DIVIDE(SUM(contact_form_submissions)+SUM(document_downloads), SUM(sessions))*100,2) AS overall_cvr_pct
            FROM `{project_id}.marts.daily_kpi_summary`
            WHERE report_date >= DATE_TRUNC(DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 2 MONTH), MONTH)
            GROUP BY report_month ORDER BY report_month DESC
        """, "月次KPI集計（直近3ヶ月・確定値／最新月は月途中まで）")

    if fetch_page:
        # 2026-07-10 R10-C 横断整合: 週次grainの page_performance ＋ AVG(率) ＋
        # conversions_from_page（完了ページにだけCVが立つ旧定義）は、Lookerページ別
        # （日次grain・ratio of sums・inquiry_cv_sessions）と同名指標で数値が食い違うため、
        # Lookerと同一の page_performance_daily × ratio of sums × 定義書準拠列に統一。
        _q(f"""
            SELECT page_path, SUM(pageviews) AS pageviews,
                   ROUND(SAFE_DIVIDE(SUM(avg_time_on_page_sec * pageviews), SUM(pageviews)),1) AS avg_time_sec,
                   ROUND(SAFE_DIVIDE(SUM(scroll_90pct_count), SUM(pageviews))*100,1) AS scroll_90pct_pct,
                   ROUND(SAFE_DIVIDE(SUM(cta_click_sessions), SUM(unique_pageviews))*100,2) AS cta_click_rate_pct,
                   SUM(inquiry_cv_sessions) AS conversions
            FROM `{project_id}.marts.page_performance_daily`
            GROUP BY page_path ORDER BY pageviews DESC LIMIT 15
        """, "ページ別パフォーマンス")

    if fetch_channel:
        # 2026-07-10 R10-C 横断整合: CV率は定義書2026-07-09「お問い合わせ完了のみ」
        # （inquiry_conversion_rate）に統一（Lookerチャネル別と同定義・同値）。
        _q(f"""
            SELECT report_month, channel_grouping, sessions,
                   inquiry_conversions AS conversions,
                   ROUND(inquiry_conversion_rate*100,2) AS cvr_pct,
                   ROUND(engagement_rate*100,1) AS eng_rate_pct
            FROM `{project_id}.marts.channel_kpi_monthly`
            ORDER BY report_month DESC, sessions DESC
        """, "チャネル別月次KPI")

    if fetch_funnel:
        _q(f"""
            SELECT report_date, step1_sessions,
                   step2b_service_view AS step2_service_view,
                   step3_contact_reach_incl AS step3_contact_page,
                   step4_form_start_incl AS step4_form_start,
                   step5_submission,
                   ROUND(overall_inquiry_cvr*100,2) AS inquiry_cvr_pct
            FROM `{project_id}.marts.conversion_funnel_daily`
            ORDER BY report_date DESC LIMIT 14
        """, "ファネル（直近14日）")
        # 2026-07-13 検収前検証: AIが日次14行を自力合算して件数を誤る事故
        # （実測: 送信完了8件を7件と誤算・CVR1.54%を0.98%と誤答）を防ぐため、
        # 日次KPIと同様に期間集計の確定値行をSQL側で渡す（率はratio of sums）。
        _q(f"""
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
        """, "ファネル直近14日 期間集計（確定値）")

    if fetch_traffic:
        _q(f"""
            SELECT dimension_type, dimension_value,
                   SUM(sessions) AS sessions,
                   -- R10-C 横断整合: CV数は定義書準拠のお問い合わせ完了のみ（inquiry_conversions）。
                   -- Lookerのチャネル別/LP別「コンバージョン数」と同定義・同値。
                   SUM(inquiry_conversions) AS conversions,
                   ROUND(SAFE_DIVIDE(SUM(engaged_sessions), SUM(sessions))*100,1) AS eng_rate_pct
            FROM `{project_id}.marts.traffic_breakdown_daily`
            WHERE report_date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 30 DAY)
              AND dimension_type IN ('channel','search_engine','referral',
                                     'landing_page','exit_page','device','user_type')
            GROUP BY dimension_type, dimension_value
            HAVING sessions > 0
            ORDER BY dimension_type, sessions DESC
        """, "流入・ページ内訳（直近30日: チャネル/検索エンジン/Referral/LP/離脱/デバイス/新規リピーター）")
        label_tr = "流入・ページ内訳（直近30日: チャネル/検索エンジン/Referral/LP/離脱/デバイス/新規リピーター）"
        if label_tr in results:
            results[label_tr]["dimension_type"] = (
                results[label_tr]["dimension_type"].map(DIMENSION_TYPE_JA)
                .fillna(results[label_tr]["dimension_type"])
            )

    return results


def _render_data(label: str, df: pd.DataFrame) -> None:
    """データをグラフ＋テーブルで表示"""
    st.markdown(f'<div class="section-label">{label}</div>', unsafe_allow_html=True)
    col_cfg = _col_config(df)

    if label == "日次KPI（直近14日）":
        df_sorted = df.sort_values("report_date") if "report_date" in df.columns else df
        col1, col2 = st.columns(2)
        with col1:
            if "sessions" in df_sorted.columns and "report_date" in df_sorted.columns:
                st.markdown('<p class="chart-title">セッション数推移</p>', unsafe_allow_html=True)
                _c = df_sorted.set_index("report_date")[["sessions"]].rename(columns={"sessions": "セッション数"})
                st.line_chart(_c, height=200, use_container_width=True)
        with col2:
            if "overall_cvr_pct" in df_sorted.columns and "report_date" in df_sorted.columns:
                st.markdown('<p class="chart-title">コンバージョン率(%)推移</p>', unsafe_allow_html=True)
                _c = df_sorted.set_index("report_date")[["overall_cvr_pct"]].rename(columns={"overall_cvr_pct": "CVR(%)"})
                st.line_chart(_c, height=200, use_container_width=True)
        st.dataframe(df_sorted, column_config=col_cfg, use_container_width=True, hide_index=True)

    elif label == "ページ別パフォーマンス":
        if "pageviews" in df.columns and "page_path" in df.columns:
            st.markdown('<p class="chart-title">ページビュー数 TOP15</p>', unsafe_allow_html=True)
            chart_df = df.set_index("page_path")[["pageviews"]].head(10)
            chart_df.index.name = "ページパス"
            chart_df.columns = ["ページビュー数"]
            st.bar_chart(chart_df, height=220, use_container_width=True)
        st.dataframe(df, column_config=col_cfg, use_container_width=True, hide_index=True)

    elif label == "チャネル別月次KPI":
        if "channel_grouping" in df.columns and "sessions" in df.columns and "report_month" in df.columns:
            latest_month = df["report_month"].max()
            df_latest = df[df["report_month"] == latest_month]
            st.markdown('<p class="chart-title">チャネル別セッション数（最新月）</p>', unsafe_allow_html=True)
            chart_df = df_latest.set_index("channel_grouping")[["sessions"]]
            chart_df.index.name = "チャネル"
            chart_df.columns = ["セッション数"]
            st.bar_chart(chart_df, height=200, use_container_width=True)
        st.dataframe(df, column_config=col_cfg, use_container_width=True, hide_index=True)

    elif label == "ファネル（直近14日）":
        funnel_raw = ["step1_sessions", "step2_service_view", "step3_contact_page",
                      "step4_form_start", "step5_submission"]
        funnel_ja  = ["Step1: セッション開始", "Step2: サービスページ閲覧",
                      "Step3: お問い合わせページ", "Step4: フォーム入力開始", "Step5: フォーム送信完了"]
        avail_raw = [c for c in funnel_raw if c in df.columns]
        if avail_raw:
            st.markdown('<p class="chart-title">ファネル平均（直近14日）</p>', unsafe_allow_html=True)
            funnel_avg = df[avail_raw].mean().round(1)
            label_map = dict(zip(funnel_raw, funnel_ja))
            funnel_avg.index = [label_map.get(c, c) for c in funnel_avg.index]
            funnel_avg_df = funnel_avg.reset_index()
            funnel_avg_df.columns = ["ステップ", "平均件数"]
            st.bar_chart(funnel_avg_df.set_index("ステップ"), height=200, use_container_width=True)
        st.dataframe(df, column_config=col_cfg, use_container_width=True, hide_index=True)

    else:
        st.dataframe(df, column_config=col_cfg, use_container_width=True, hide_index=True)


# ── AI 回答（会話履歴対応） ─────────────────────────────────────
def _ask_ai(
    question: str,
    data_frames: dict[str, pd.DataFrame],
    history: list[dict],
    openai_client,
    model: str,
) -> str:
    # AIへ渡すデータも列名を日本語化する（回答に step1_sessions 等の内部英語列名が
    # そのまま露出する事故を防ぐ・2026-06-23 検収R7-③対応）。
    context_parts = [f"【{label}】\n{_ja(df).to_string(index=False)}" for label, df in data_frames.items()]
    context = "\n\n".join(context_parts) if context_parts else "（関連データなし）"

    system_prompt = (
        "あなたはGA4データを専門とするWebマーケティングアナリストです。\n"
        "以下のBigQueryデータを根拠に、日本語で具体的・簡潔に回答してください。\n"
        "- 数字を必ず引用する\n"
        "- 改善提案がある場合は必ず1つ以上含める\n"
        "- データにない推測・誇張はしない\n"
        "- 回答は500文字以内\n"
        "\n【率の期間集計ルール（重要）】\n"
        "- 直近14日の期間の数値を聞かれたら、まず『直近14日 期間集計（確定値）』の行の値をそのまま引用する。\n"
        "  日次行を自分で足し算して率を出し直さない（合算ミスの原因になる）。\n"
        "- ファネルの期間の件数・率（各ステップ到達数、離脱数、完了率、問い合わせCVR）も同様に、\n"
        "  必ず『ファネル直近14日 期間集計（確定値）』の行の値をそのまま引用する。\n"
        "  日次14行を自分で合算しない。離脱数を出すときは確定値行の隣接ステップの差で計算する。\n"
        "- 今月と先月の比較は『月次KPI集計』の行を使う（最新月は月途中までの集計であることを必ず添える）。\n"
        "- 数値を引用するときは必ず対象期間を明記する（例: 全期間累計／直近14日／直近30日／2026年6月）。\n"
        "- 上記の確定値が無い範囲を集計するときのみ、率は日次％の単純平均ではなく\n"
        "  必ず分子と分母を合計してから割る(ratio of sums)。例: SUM(engaged_sessions)÷SUM(sessions)。\n"
        "  これがLooker Studioの数値と一致する正しい集計。\n"
        "\n【利用可能なデータ範囲】\n"
        "- 日次KPI・ファネル: 直近14日 ／ ページ別: 全期間 ／ チャネル別: 月次\n"
        "- 日次KPIには 直帰率(bounce_rate_pct)・新規ユーザー率(new_user_rate_pct)・エンゲージメント率も含む\n"
        "- ページ別の『コンバージョン数』は“そのページを閲覧して最終的にお問い合わせ完了に至った"
        "セッション数（ページ経由CV数）”。1セッションが複数ページを閲覧して完了すると閲覧した"
        "各ページに1ずつ計上されるため、ページ間で合算して総CV数として扱ってはいけない"
        "（サイト全体の総数は日次KPIの問い合わせ件数を使う）\n"
        "- 『/contact/?mode=finish』は送信完了の着地ページそのものなので、"
        "コンバージョンに貢献したページとしては挙げない\n"
        "- 流入・ページ内訳（チャネル/検索エンジン/参照元/LP/離脱ページ/デバイス/新規リピーター）: 直近30日\n"
        "- GA4→BigQueryの日次連携のため、直近1〜2日のデータは未反映\n"
        "- 渡されたデータは固定範囲(14日/30日/月次)の集計。これより前にさかのぼる任意期間の再集計はこのチャットでは不可。\n"
        "  その場合は『この期間の自由指定集計は現在のAIチャットでは未対応で、Looker Studioで任意期間を指定してご確認いただけます』と案内する\n"
        "- 範囲外・データにない質問には「現在のデータでは回答できない」と明示し、"
        "代わりに確認できる内容を案内する\n"
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
        "- 特に『Step2: サービスページ閲覧』と『Step3: お問い合わせページ』は、"
        "それぞれ独立に数えた到達セッション数（並列の到達指標）であって、直列の通過順ではない。\n"
        "- ユーザーはサービスページを見ずに、広告・検索・直接アクセスから"
        "直接お問い合わせページへ到達することもある。"
        "つまり全ユーザーがStep2（サービス閲覧）を経由してStep3へ進む前提は誤り。\n"
        "- したがって『Step1とStep2の数の差』を根拠に『最初の段階で離脱が多い』と結論づけてはいけない。"
        "Step2はサイト内回遊の参考指標として扱う。\n"
        "- 数の大小関係（前段 ≧ 後段 の単調減少）が定義上保証されるのは"
        "『Step3 お問い合わせページ到達 ≧ Step4 フォーム入力開始 ≧ Step5 送信完了』の区間のみ。"
        "離脱や改善余地を論じるときは、この区間（お問い合わせ到達→入力開始→送信完了）で評価する。\n"
        "- 『どのステップで最も離脱が多いか』を問われたら、"
        "『お問い合わせ到達→入力開始』と『入力開始→送信完了』の各区間について、"
        "離脱セッション数（前段−後段）と離脱率（1−後段÷前段）を両方求めて答える。"
        "離脱数が最多の区間と離脱率が最悪の区間が食い違う場合は、"
        "どちらの物差しで最多かを明記し両方を提示する"
        "（例: 到達→入力開始は離脱20件・50%、入力開始→送信完了は離脱12件・60%）。"
        "片方の物差しだけを根拠に『最も離脱が多い』と断定しない。\n"
        "- サイト全体の最終的な問い合わせ転換率は『問い合わせCVR(%)』を用いる"
        "（Step1からStep5への到達率）。\n"
        "- 回答では step1_sessions のような内部の英語カラム名やstep番号の生表記をそのまま出さず、"
        "必ず日本語のステップ名（例: お問い合わせページ到達、フォーム入力開始）で説明する。\n"
        f"\n【最新BQデータ】\n{context}"
    )

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for msg in history[-6:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": question})

    resp = openai_client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=700,
        temperature=0.3,
        timeout=30,
    )
    if not resp.choices:
        return "（AI応答が得られませんでした）"
    return resp.choices[0].message.content or ""


# ── サイドバー ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 質問例")
    for category, questions in EXAMPLE_QUESTIONS.items():
        st.markdown(f"**{category}**")
        for q in questions:
            if st.button(q, key=f"ex_{q}", use_container_width=True):
                st.session_state.pending_question = q
                st.rerun()
        st.markdown("---")

    if st.button("会話をリセット", use_container_width=True, type="secondary"):
        st.session_state.messages = []
        st.rerun()

    st.markdown("### このツールについて")
    st.markdown("""
BigQueryに蓄積されたGA4データをもとに、
日本語の質問にAI（GPT-4o）が回答します。

前の質問の文脈を引き継いで会話できます。

**対応データ**
- 日次KPI（セッション・CVR等）
- ページ別パフォーマンス
- チャネル別月次KPI
- コンバージョンファネル
- 検索エンジン別・参照元別の流入
- ランディング/離脱ページ・デバイス・新規/リピーター
""")


# ── チャット履歴の表示 ──────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("data_frames"):
            for label, df_dict in msg["data_frames"].items():
                _render_data(label, pd.DataFrame(df_dict))


# ── 入力受付 ───────────────────────────────────────────────────
question = st.chat_input("データについて質問してください（例: どのページが一番離脱が多いですか？）")

if not question and st.session_state.pending_question:
    question = st.session_state.pending_question
    st.session_state.pending_question = ""

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    answer: str = ""
    data_frames: dict[str, pd.DataFrame] = {}

    with st.chat_message("assistant"):
        with st.spinner("BigQueryからデータを取得中..."):
            try:
                bq, openai_client, project_id, cfg = _init_clients()
                model = cfg["report"].get("openai_model", "gpt-4o")
                data_frames = _fetch_data(question, bq, project_id)
            except Exception as e:
                st.error(f"❌ データ取得エラー: {e}")
                st.stop()

        with st.spinner("AIが分析中..."):
            try:
                history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages[:-1]
                ]
                answer = _ask_ai(question, data_frames, history, openai_client, model)
            except Exception as e:
                st.error(f"❌ AI分析エラー: {e}")
                st.stop()

        st.markdown(answer)

        if data_frames:
            st.markdown("---")
            for label, df in data_frames.items():
                _render_data(label, df)

        st.session_state.messages.append({
            "role": "assistant",
            "content": answer,
            "data_frames": {k: v.to_dict() for k, v in data_frames.items()},
        })

# ── フッター ────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<p style='text-align:center;font-size:12px;color:#94a3b8;'>"
    "ARK Analytics | GA4 × BigQuery × AI 分析基盤 | Powered by GPT-4o | v2.3"
    "</p>",
    unsafe_allow_html=True,
)
