"""
ai_analyzer.py
OpenAI APIを使ってKPIデータからAIインサイトを生成するモジュール
"""
from __future__ import annotations

import os
import yaml
from openai import OpenAI


def _load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class AIAnalyzer:
    """OpenAI GPTを使ってプロンプトから分析レポートを生成"""

    SYSTEM_PROMPT = (
        "あなたはWebマーケティングの専門データアナリストです。"
        "提供されたデータの数字のみを根拠として分析し、"
        "推測や誇張は避けてください。"
        "不明なデータについては「データ不足」と明記してください。"
    )

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or _load_config()
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY が環境変数に設定されていません")
        self.client = OpenAI(api_key=api_key)
        self.model = self.config["report"].get("openai_model", "gpt-4o")
        self.temperature = float(self.config["report"].get("temperature", 0.3))

    def analyze(
        self,
        prompt: str,
        report_type: str = "executive",
    ) -> str:
        """
        プロンプトを受け取りAIインサイトを返す
        report_type: 'executive' or 'ops'
        """
        max_tokens = (
            self.config["report"].get("max_tokens_executive", 800)
            if report_type == "executive"
            else self.config["report"].get("max_tokens_ops", 1500)
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=self.temperature,
        )
        return response.choices[0].message.content or ""
