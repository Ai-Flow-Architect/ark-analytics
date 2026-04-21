"""
GA4 AI アナリスト — ARK Analytics
自然言語でGA4データに質問するStreamlit Webアプリ
"""
from __future__ import annotations

import os
import sys
import yaml
import pandas as pd
import streamlit as st

# src/ をパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# ─── ページ設定 ────────────────────────────────────────────────
st.set_page_config(
    page_title="GA4 AI アナリスト | ARK Analytics",
    page_icon="📊",
    layout="wide",
)

# ─── 定数 ──────────────────────────────────────────────────────
PRIMARY   = "#1a56db"
BG_CARD   = "#f8faff"
PROJECT_ID = "ark-hd-analytics"

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

# ─── CSS ───────────────────────────────────────────────────────
st.markdown(f"""
<style>
  .header-block {{
    background: linear-gradient(135deg, #0f4c81 0%, {PRIMARY} 60%, #2563eb 100%);
    color: white;
    padding: 28px 36px 22px;
    border-radius: 12px;
    margin-bottom: 24px;
  }}
  .header-block h1 {{ font-size: 24px; font-weight: 700; margin: 0 0 4px 0; }}
  .header-block p  {{ font-size: 13px; opacity: 0.8; margin: 0; }}
  .answer-box {{
    background: {BG_CARD};
    border: 1px solid #c7d7f9;
    border-left: 4px solid {PRIMARY};
    border-radius: 8px;
    padding: 20px 24px;
    font-size: 15px;
    line-height: 1.8;
    white-space: pre-wrap;
  }}
  .data-label {{
    font-size: 12px;
    font-weight: 700;
    color: #64748b;
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-top: 20px;
    margin-bottom: 6px;
  }}
  .stButton > button {{
    background: {PRIMARY};
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 28px;
    font-size: 15px;
    font-weight: 600;
    width: 100%;
  }}
  .stButton > button:hover {{ background: #1648c0; }}
</style>
""", unsafe_allow_html=True)

# ─── ヘッダー ───────────────────────────────────────────────────
st.markdown("""
<div class="header-block">
  <h1>📊 GA4 AI アナリスト</h1>
  <p>ARK Analytics — BigQueryデータをもとにAIが即座に分析・回答します</p>
</div>
""", unsafe_allow_html=True)

# ─── サイドバー ─────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 💡 質問例")
    for category, questions in EXAMPLE_QUESTIONS.items():
        st.markdown(f"**{category}**")
        for q in questions:
            if st.button(q, key=q, use_container_width=True):
                st.session_state["question_input"] = q
        st.markdown("---")

    st.markdown("### ℹ️ このツールについて")
    st.markdown("""
BigQueryに蓄積されたGA4データをもとに、
日本語の質問にAI（GPT-4o）が回答します。

**対応データ**
- 日次KPI（セッション・CVR等）
- ページ別パフォーマンス
- チャネル別月次KPI
- コンバージョンファネル
""")

# ─── BQ + OpenAI 初期化（キャッシュ）──────────────────────────
@st.cache_resource(show_spinner=False)
def _init_clients():
    """BigQuery / OpenAI クライアントを初期化（起動時1回だけ）"""
    from google.cloud import bigquery
    from openai import OpenAI

    config_path = os.path.join(os.path.dirname(__file__), "config", "settings.yaml")
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    project_id = cfg["gcp"]["project_id"]
    key_path = cfg["gcp"].get("service_account_key", "")

    if key_path and os.path.exists(key_path):
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(key_path)
        bq = bigquery.Client(project=project_id, credentials=creds)
    else:
        bq = bigquery.Client(project=project_id)

    api_key = (
        st.secrets.get("OPENAI_API_KEY", "")
        or os.environ.get("ARK_OPENAI_API_KEY", "")
        or os.environ.get("OPENAI_API_KEY", "")
    )
    if not api_key:
        st.error("❌ OpenAI APIキーが設定されていません。環境変数 OPENAI_API_KEY を設定してください。")
        st.stop()

    openai_client = OpenAI(api_key=api_key)
    return bq, openai_client, project_id, cfg


def _fetch_data(question: str, bq, project_id: str) -> dict[str, pd.DataFrame]:
    """質問に応じて関連BQテーブルを取得し、DataFrame辞書を返す"""
    q = question.lower()
    fetch_page    = any(k in q for k in ["ページ", "page", "url", "コンテンツ", "スクロール", "離脱", "閲覧"])
    fetch_channel = any(k in q for k in ["チャネル", "流入", "経路", "organic", "direct", "検索"])
    fetch_funnel  = any(k in q for k in ["ファネル", "フォーム", "問い合わせ", "cv", "コンバージョン", "送信"])
    fetch_kpi     = any(k in q for k in ["セッション", "訪問", "ユーザー", "kpi", "今月", "先月", "傾向", "エンゲージ"])

    # いずれにも該当しない場合はKPIを取得
    if not any([fetch_page, fetch_channel, fetch_funnel, fetch_kpi]):
        fetch_kpi = True

    results: dict[str, pd.DataFrame] = {}

    def _safe_query(sql: str, label: str) -> pd.DataFrame | None:
        try:
            df = bq.query(sql).to_dataframe()
            return df if not df.empty else None
        except Exception as e:
            st.warning(f"⚠️ {label} の取得に失敗しました: {e}")
            return None

    if fetch_kpi:
        df = _safe_query(f"""
            SELECT report_date, sessions, users, pageviews,
                   ROUND(engagement_rate*100,1) AS engagement_rate_pct,
                   contact_form_submissions,
                   ROUND(overall_cvr*100,2) AS overall_cvr_pct
            FROM `{project_id}.marts.daily_kpi_summary`
            ORDER BY report_date DESC LIMIT 14
        """, "日次KPI")
        if df is not None:
            results["日次KPI（直近14日）"] = df

    if fetch_page:
        df = _safe_query(f"""
            SELECT page_path, SUM(pageviews) AS pageviews,
                   ROUND(AVG(avg_time_on_page_sec),1) AS avg_time_sec,
                   ROUND(AVG(scroll_90pct_rate)*100,1) AS scroll_90pct_pct,
                   SUM(conversions_from_page) AS conversions
            FROM `{project_id}.marts.page_performance`
            GROUP BY page_path
            ORDER BY pageviews DESC LIMIT 15
        """, "ページ別パフォーマンス")
        if df is not None:
            results["ページ別パフォーマンス"] = df

    if fetch_channel:
        df = _safe_query(f"""
            SELECT report_month, channel_grouping, sessions,
                   ROUND(conversion_rate*100,2) AS cvr_pct,
                   ROUND(engagement_rate*100,1) AS eng_rate_pct
            FROM `{project_id}.marts.channel_kpi_monthly`
            ORDER BY report_month DESC, sessions DESC
        """, "チャネル別月次KPI")
        if df is not None:
            results["チャネル別月次KPI"] = df

    if fetch_funnel:
        df = _safe_query(f"""
            SELECT report_date, step1_sessions, step2_service_view,
                   step3_contact_page, step4_form_start, step5_submission,
                   ROUND(overall_inquiry_cvr*100,2) AS inquiry_cvr_pct
            FROM `{project_id}.marts.conversion_funnel_daily`
            ORDER BY report_date DESC LIMIT 14
        """, "ファネル")
        if df is not None:
            results["ファネル（直近14日）"] = df

    return results


def _ask_ai(question: str, data_frames: dict[str, pd.DataFrame], openai_client, model: str) -> str:
    """BQデータをコンテキストにGPT-4oへ質問する"""
    context_parts = []
    for label, df in data_frames.items():
        context_parts.append(f"【{label}】\n{df.to_string(index=False)}")
    context = "\n\n".join(context_parts) if context_parts else "（データ取得できませんでした）"

    system_prompt = (
        "あなたはGA4データを専門とするWebマーケティングアナリストです。\n"
        "以下の実際のGA4 BQデータを根拠に、日本語で具体的・簡潔に回答してください。\n"
        "- 数字を必ず引用する\n"
        "- 改善提案がある場合は必ず1つ以上追加する\n"
        "- データにない推測・誇張はしない\n"
        "- 回答は500文字以内"
    )
    user_prompt = f"【データ】\n{context}\n\n【質問】\n{question}"

    response = openai_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        max_tokens=700,
        temperature=0.3,
    )
    return response.choices[0].message.content or ""


# ─── メイン UI ─────────────────────────────────────────────────
question = st.text_area(
    "質問を入力してください",
    value=st.session_state.get("question_input", ""),
    placeholder="例: どのページが一番離脱が多いですか？",
    height=90,
    key="question_text",
)

col_btn, col_clear = st.columns([4, 1])
with col_btn:
    ask_clicked = st.button("📊 質問する", use_container_width=True)
with col_clear:
    if st.button("クリア", use_container_width=True):
        st.session_state["question_input"] = ""
        st.rerun()

if ask_clicked and question.strip():
    with st.spinner("BigQueryからデータを取得中..."):
        try:
            bq, openai_client, project_id, cfg = _init_clients()
            model = cfg["report"].get("openai_model", "gpt-4o")

            data_frames = _fetch_data(question.strip(), bq, project_id)

        except Exception as e:
            st.error(f"❌ データ取得エラー: {e}")
            st.stop()

    with st.spinner("AIが分析中..."):
        try:
            answer = _ask_ai(question.strip(), data_frames, openai_client, model)
        except Exception as e:
            st.error(f"❌ AI分析エラー: {e}")
            st.stop()

    # ── 回答表示 ──
    st.markdown("### 🤖 AI回答")
    st.markdown(f'<div class="answer-box">{answer}</div>', unsafe_allow_html=True)

    # ── 参照データ表示 ──
    if data_frames:
        st.markdown("---")
        st.markdown("### 📋 参照したBQデータ")
        for label, df in data_frames.items():
            st.markdown(f'<div class="data-label">{label}</div>', unsafe_allow_html=True)
            st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.warning("⚠️ 関連するBQデータが取得できませんでした。BQにデータが存在するか確認してください。")

elif ask_clicked:
    st.warning("質問を入力してください。")

# ─── フッター ───────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<p style='text-align:center;font-size:12px;color:#94a3b8;'>"
    "ARK Analytics | GA4 × BigQuery × AI 分析基盤 | Powered by GPT-4o"
    "</p>",
    unsafe_allow_html=True,
)
