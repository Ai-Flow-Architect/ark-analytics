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
