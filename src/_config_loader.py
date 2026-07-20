"""
共通設定ローダー — settings.yaml を読み込み、環境変数で上書きする
"""
from __future__ import annotations

import os
import yaml


_PLACEHOLDER_TOKENS = ("REDACTED", "<", ">", "{{", "}}", "TODO", "FIXME")


def _is_placeholder(value: str) -> bool:
    if not value:
        return True
    upper = value.upper()
    return any(token in upper for token in _PLACEHOLDER_TOKENS)


def load_config() -> dict:
    """settings.yaml を読み込み、環境変数で上書きする。

    上書き対象（環境変数 → config パス）:
      ARK_GCP_PROJECT_ID    → gcp.project_id
      ARK_GA4_PROPERTY_ID   → ga4.property_id
      ARK_GA4_RAW_DATASET   → ga4.raw_dataset
    """
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml")
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # 環境変数オーバーライド（クライアント機密情報を settings.yaml に書かないため）
    cfg.setdefault("gcp", {})
    cfg.setdefault("ga4", {})
    if v := os.environ.get("ARK_GCP_PROJECT_ID"):
        cfg["gcp"]["project_id"] = v.strip()
    if v := os.environ.get("ARK_GA4_PROPERTY_ID"):
        cfg["ga4"]["property_id"] = v.strip()
    if v := os.environ.get("ARK_GA4_RAW_DATASET"):
        cfg["ga4"]["raw_dataset"] = v.strip()

    return cfg


def get_kpi_targets(config: dict | None = None) -> dict:
    """KPI目標値の単一の真実 (SSOT)。settings.yaml の kpi_targets を返す。

    レポート/プロンプト/通知の各所でハードコードせず必ずここを経由する
    （2026-07-08 クライアント指摘: お問い合わせ目標がコード各所に「9」で
    ハードコードされ、目標変更(9→6)が反映されない事故の再発防止）。
    """
    cfg = config if config is not None else load_config()
    targets = cfg.get("kpi_targets") or {}
    return {
        "monthly_sessions": int(targets.get("monthly_sessions", 5000)),
        "monthly_inquiries": int(targets.get("monthly_inquiries", 6)),
        "monthly_downloads": int(targets.get("monthly_downloads", 50)),
        "monthly_appointments": int(targets.get("monthly_appointments", 6)),
        "monthly_contracts": int(targets.get("monthly_contracts", 3)),
    }


def get_project_id(config: dict | None = None) -> str:
    """GCPプロジェクトIDの単一の真実 (SSOT)。

    解決順位:
      1. 環境変数 ARK_GCP_PROJECT_ID（GitHub Actions / 本番）
      2. 環境変数 GOOGLE_CLOUD_PROJECT（ADC互換・ローカル開発）
      3. settings.yaml の gcp.project_id

    プレースホルダ・空文字・未設定の場合は RuntimeError を送出する
    （フォールバックでBigQueryに無効値を渡さないための物理ブロック）。
    """
    candidates = [
        ("ARK_GCP_PROJECT_ID", os.environ.get("ARK_GCP_PROJECT_ID", "").strip()),
        ("GOOGLE_CLOUD_PROJECT", os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()),
    ]
    for name, value in candidates:
        if value and _is_placeholder(value):
            raise RuntimeError(
                f"環境変数 {name} がプレースホルダ値です: '{value}'. "
                f"GitHub Secrets を正しい GCP プロジェクトID に更新してください。"
            )
        if value:
            return value

    cfg = config if config is not None else load_config()
    yaml_value = (cfg.get("gcp", {}).get("project_id") or "").strip()
    if yaml_value and _is_placeholder(yaml_value):
        raise RuntimeError(
            f"settings.yaml の gcp.project_id がプレースホルダ値です: '{yaml_value}'."
        )
    if yaml_value:
        return yaml_value

    raise RuntimeError(
        "GCPプロジェクトIDが解決できません。"
        "環境変数 ARK_GCP_PROJECT_ID を設定してください "
        "(GitHub Actions の場合は Secrets > ARK_GCP_PROJECT_ID)."
    )


def make_bq_client(project_id: str, credentials=None):
    """BigQuery クライアントを生成する単一窓口。

    quota/billing プロジェクト（x-goog-user-project ヘッダ）を必ず project_id に
    固定する。これにより、ローカルの ADC
    （~/.config/gcloud/application_default_credentials.json）に別プロジェクトの
    quota_project_id が残っていても、その値で BigQuery を叩いて
    USER_PROJECT_DENIED(403) になる事故を防ぐ。

    背景: ローカル開発機の gcloud/ADC は複数プロジェクト間で共有されるため、
    他作業で set-quota-project された値を Python クライアントが意図せず継承し、
    daily_refresh.sh のローカル実行時に鮮度チェックが 403 で誤警報を出すこと
    があった。GitHub Actions(SA鍵) は quota 未設定で無害だが、ローカル実行に
    対する恒久的な防御として全クライアント生成をこの窓口に統一する。
    """
    from google.cloud import bigquery

    if credentials is None:
        import google.auth

        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    if hasattr(credentials, "with_quota_project"):
        credentials = credentials.with_quota_project(project_id)
    return bigquery.Client(project=project_id, credentials=credentials)
