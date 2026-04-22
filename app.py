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

st.markdown(f"""
<style>
  .header-block {{
    background: linear-gradient(135deg, #0f4c81 0%, {PRIMARY} 60%, #2563eb 100%);
    color: white; padding: 22px 28px 18px; border-radius: 12px; margin-bottom: 20px;
  }}
  .header-block h1 {{ font-size: 22px; font-weight: 700; margin: 0 0 4px 0; }}
  .header-block p  {{ font-size: 12px; opacity: 0.8; margin: 0; }}
  .data-label {{
    font-size: 11px; font-weight: 700; color: #64748b;
    letter-spacing: 1px; text-transform: uppercase;
    margin-top: 14px; margin-bottom: 4px;
  }}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="header-block">
  <h1>📊 GA4 AI チャットアナリスト</h1>
  <p>ARK Analytics — データについて日本語で自由にチャットしてください</p>
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
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    project_id = cfg["gcp"]["project_id"]

    from google.cloud import bigquery

    # Streamlit Cloud: gcp_service_account secret があればサービスアカウント認証
    if "gcp_service_account" in st.secrets:
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]),
            scopes=["https://www.googleapis.com/auth/bigquery"],
        )
        bq = bigquery.Client(project=project_id, credentials=creds)
    else:
        # ローカル: ADC（Application Default Credentials）
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
            df = bq.query(sql).to_dataframe()
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

    # 直近6ターンの会話履歴でコンテキストを保持
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for msg in history[-6:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": question})

    resp = openai_client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=700,
        temperature=0.3,
    )
    return resp.choices[0].message.content or ""


# ── サイドバー ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 💡 質問例")
    for category, questions in EXAMPLE_QUESTIONS.items():
        st.markdown(f"**{category}**")
        for q in questions:
            if st.button(q, key=f"ex_{q}", use_container_width=True):
                st.session_state.pending_question = q
                st.rerun()
        st.markdown("---")

    if st.button("🗑 会話をクリア", use_container_width=True, type="secondary"):
        st.session_state.messages = []
        st.rerun()

    st.markdown("### ℹ️ このツールについて")
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
                st.markdown(f'<div class="data-label">{label}</div>', unsafe_allow_html=True)
                st.dataframe(pd.DataFrame(df_dict), use_container_width=True, hide_index=True)


# ── 入力受付 ───────────────────────────────────────────────────
question = st.chat_input("データについて質問してください（例: どのページが一番離脱が多いですか？）")

# サイドバーの質問例ボタンから注入
if not question and st.session_state.pending_question:
    question = st.session_state.pending_question
    st.session_state.pending_question = ""

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

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
                st.markdown(f'<div class="data-label">{label}</div>', unsafe_allow_html=True)
                st.dataframe(df, use_container_width=True, hide_index=True)

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "data_frames": {k: v.to_dict() for k, v in data_frames.items()},
    })

# ── フッター ────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<p style='text-align:center;font-size:12px;color:#94a3b8;'>"
    "ARK Analytics | GA4 × BigQuery × AI 分析基盤 | Powered by GPT-4o"
    "</p>",
    unsafe_allow_html=True,
)
