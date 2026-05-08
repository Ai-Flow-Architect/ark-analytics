"""
共通設定ローダー — settings.yaml を読み込み、環境変数で上書きする
"""
from __future__ import annotations

import os
import yaml


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
        cfg["gcp"]["project_id"] = v
    if v := os.environ.get("ARK_GA4_PROPERTY_ID"):
        cfg["ga4"]["property_id"] = v
    if v := os.environ.get("ARK_GA4_RAW_DATASET"):
        cfg["ga4"]["raw_dataset"] = v

    return cfg
