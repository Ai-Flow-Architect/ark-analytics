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
    "pageviews":                "ページビュー数",
    "engagement_rate_pct":      "エンゲージメント率(%)",
    "contact_form_submissions": "問い合わせ件数",
    "overall_cvr_pct":          "コンバージョン率(%)",
    "page_path":                "ページパス",
    "avg_time_sec":             "平均滞在時間(秒)",
    "scroll_90pct_pct":         "スクロール90%到達率(%)",
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
}


def _ja(df: pd.DataFrame) -> pd.DataFrame:
    """DataFrameの列名を日本語に変換"""
    return df.rename(columns={k: v for k, v in COLUMN_JA.items() if k in df.columns})


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

    project_id = cfg["gcp"]["project_id"]

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
    if not any([fetch_page, fetch_channel, fetch_funnel, fetch_kpi]):
        fetch_kpi = True

    results: dict[str, pd.DataFrame] = {}

    def _q(sql: str, label: str) -> None:
        try:
            job = bq.query(sql)
            df = job.result(timeout=30).to_dataframe()
            if not df.empty:
                results[label] = df
        except Exception as e:
            st.warning(f"⚠️ {label} の取得に失敗しました: {e}")

    if fetch_kpi:
        _q(f"""
            SELECT report_date, sessions, users, pageviews,
                   ROUND(engagement_rate*100,1) AS engagement_rate_pct,
                   contact_form_submissions,
                   ROUND(overall_cvr*100,2) AS overall_cvr_pct
            FROM `{project_id}.marts.daily_kpi_summary`
            ORDER BY report_date DESC LIMIT 14
        """, "日次KPI（直近14日）")

    if fetch_page:
        _q(f"""
            SELECT page_path, SUM(pageviews) AS pageviews,
                   ROUND(AVG(avg_time_on_page_sec),1) AS avg_time_sec,
                   ROUND(AVG(scroll_90pct_rate)*100,1) AS scroll_90pct_pct,
                   SUM(conversions_from_page) AS conversions
            FROM `{project_id}.marts.page_performance`
            GROUP BY page_path ORDER BY pageviews DESC LIMIT 15
        """, "ページ別パフォーマンス")

    if fetch_channel:
        _q(f"""
            SELECT report_month, channel_grouping, sessions,
                   ROUND(conversion_rate*100,2) AS cvr_pct,
                   ROUND(engagement_rate*100,1) AS eng_rate_pct
            FROM `{project_id}.marts.channel_kpi_monthly`
            ORDER BY report_month DESC, sessions DESC
        """, "チャネル別月次KPI")

    if fetch_funnel:
        _q(f"""
            SELECT report_date, step1_sessions, step2_service_view,
                   step3_contact_page, step4_form_start, step5_submission,
                   ROUND(overall_inquiry_cvr*100,2) AS inquiry_cvr_pct
            FROM `{project_id}.marts.conversion_funnel_daily`
            ORDER BY report_date DESC LIMIT 14
        """, "ファネル（直近14日）")

    return results


def _render_data(label: str, df: pd.DataFrame) -> None:
    """データをグラフ＋テーブルで表示"""
    df_ja = _ja(df.copy())

    st.markdown(f'<div class="section-label">{label}</div>', unsafe_allow_html=True)

    if label == "日次KPI（直近14日）":
        df_sorted = df_ja.sort_values("日付") if "日付" in df_ja.columns else df_ja
        col1, col2 = st.columns(2)
        with col1:
            if "セッション数" in df_sorted.columns and "日付" in df_sorted.columns:
                st.markdown('<p class="chart-title">セッション数推移</p>', unsafe_allow_html=True)
                chart_df = df_sorted.set_index("日付")[["セッション数"]]
                st.line_chart(chart_df, height=200, use_container_width=True)
        with col2:
            if "コンバージョン率(%)" in df_sorted.columns and "日付" in df_sorted.columns:
                st.markdown('<p class="chart-title">コンバージョン率(%)推移</p>', unsafe_allow_html=True)
                chart_df = df_sorted.set_index("日付")[["コンバージョン率(%)"]]
                st.line_chart(chart_df, height=200, use_container_width=True)
        st.dataframe(df_sorted, use_container_width=True, hide_index=True)

    elif label == "ページ別パフォーマンス":
        if "ページビュー数" in df_ja.columns and "ページパス" in df_ja.columns:
            st.markdown('<p class="chart-title">ページビュー数 TOP15</p>', unsafe_allow_html=True)
            chart_df = df_ja.set_index("ページパス")[["ページビュー数"]].head(10)
            st.bar_chart(chart_df, height=220, use_container_width=True)
        st.dataframe(df_ja, use_container_width=True, hide_index=True)

    elif label == "チャネル別月次KPI":
        if "チャネル" in df_ja.columns and "セッション数" in df_ja.columns:
            latest_month = df_ja["月"].max() if "月" in df_ja.columns else None
            df_latest = df_ja[df_ja["月"] == latest_month] if latest_month else df_ja
            st.markdown('<p class="chart-title">チャネル別セッション数（最新月）</p>', unsafe_allow_html=True)
            chart_df = df_latest.set_index("チャネル")[["セッション数"]]
            st.bar_chart(chart_df, height=200, use_container_width=True)
        st.dataframe(df_ja, use_container_width=True, hide_index=True)

    elif label == "ファネル（直近14日）":
        funnel_cols = ["Step1: セッション開始", "Step2: サービスページ閲覧",
                       "Step3: お問い合わせページ", "Step4: フォーム入力開始", "Step5: フォーム送信完了"]
        avail = [c for c in funnel_cols if c in df_ja.columns]
        if avail:
            st.markdown('<p class="chart-title">ファネル平均（直近14日）</p>', unsafe_allow_html=True)
            funnel_avg = df_ja[avail].mean().round(1)
            funnel_avg_df = funnel_avg.reset_index()
            funnel_avg_df.columns = ["ステップ", "平均件数"]
            st.bar_chart(funnel_avg_df.set_index("ステップ"), height=200, use_container_width=True)
        st.dataframe(df_ja, use_container_width=True, hide_index=True)

    else:
        st.dataframe(df_ja, use_container_width=True, hide_index=True)


# ── AI 回答（会話履歴対応） ─────────────────────────────────────
def _ask_ai(
    question: str,
    data_frames: dict[str, pd.DataFrame],
    history: list[dict],
    openai_client,
    model: str,
) -> str:
    context_parts = [f"【{label}】\n{df.to_string(index=False)}" for label, df in data_frames.items()]
    context = "\n\n".join(context_parts) if context_parts else "（関連データなし）"

    system_prompt = (
        "あなたはGA4データを専門とするWebマーケティングアナリストです。\n"
        "以下のBigQueryデータを根拠に、日本語で具体的・簡潔に回答してください。\n"
        "- 数字を必ず引用する\n"
        "- 改善提案がある場合は必ず1つ以上含める\n"
        "- データにない推測・誇張はしない\n"
        "- 回答は500文字以内\n"
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
    "ARK Analytics | GA4 × BigQuery × AI 分析基盤 | Powered by GPT-4o | v2.0"
    "</p>",
    unsafe_allow_html=True,
)
