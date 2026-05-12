"""
プレースホルダ流入の物理ブロックテスト

2026-05-11 インシデント由来：
過去のセキュリティクリーンアップで実プロジェクトIDを `REDACTED-GCP-PROJECT` に置換した際、
ワークフロー・スクリプト側の Secrets 参照置換を忘れて push してしまい、
GitHub Actions 上の BigQuery クエリが400エラー連発で停止した。

このテストは「プレースホルダ文字列が実行パスに残ったまま master に流入する」事故を
CIで物理的にブロックする最後の砦。

実行:
    pytest tests/test_no_placeholder.py -v
"""
from __future__ import annotations

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


PLACEHOLDER_PATTERNS = [
    r"REDACTED-GCP-PROJECT",
    r"REDACTED-GA4-PROPID",
    r"REDACTED-CLIENT-EMAIL",
    r"REDACTED-CC-EMAIL",
]

# 実行パスに残ってはいけないファイル（コード・YAML・SQL・シェル）
EXECUTION_FILE_EXTS = (".py", ".yml", ".yaml", ".sh", ".sql")

# 検出パターン自体を定義しているファイル（許可リスト）
ALLOWED_FILES = {
    os.path.normpath("tests/test_no_placeholder.py"),
    os.path.normpath("src/_config_loader.py"),
    os.path.normpath("scripts/daily_refresh.sh"),  # 自己防衛のgrepに残す
}

EXCLUDED_DIRS = {".git", "venv", ".venv", "__pycache__", ".pytest_cache", "node_modules"}


def _iter_repo_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for fn in filenames:
            if not fn.endswith(EXECUTION_FILE_EXTS):
                continue
            yield os.path.join(dirpath, fn)


@pytest.mark.parametrize("pattern", PLACEHOLDER_PATTERNS)
def test_no_placeholder_in_execution_files(pattern: str):
    """プレースホルダがコード/YAML/シェル/SQLに残っていないことを保証する。

    src/_config_loader.py / scripts/daily_refresh.sh / このテストファイル自身は
    検出ロジックの一部として明示的に許可する。
    """
    regex = re.compile(pattern)
    offenders: list[str] = []
    for path in _iter_repo_files():
        rel = os.path.normpath(os.path.relpath(path, ROOT))
        if rel in ALLOWED_FILES:
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except OSError:
            continue
        if regex.search(content):
            offenders.append(rel)

    assert not offenders, (
        f"プレースホルダ '{pattern}' が実行パスに残っています: {offenders}. "
        f"GitHub Secrets 経由 or src._config_loader.get_project_id() 経由に置き換えてください。"
    )


def test_get_project_id_rejects_placeholder(monkeypatch):
    """get_project_id() がプレースホルダ値を弾く（=ガードレールが効いている）。"""
    from src._config_loader import get_project_id

    monkeypatch.setenv("ARK_GCP_PROJECT_ID", "REDACTED-GCP-PROJECT")
    with pytest.raises(RuntimeError, match="プレースホルダ"):
        get_project_id()


def test_get_project_id_rejects_empty(monkeypatch):
    """get_project_id() が空文字・未設定を弾く。"""
    from src._config_loader import get_project_id

    monkeypatch.delenv("ARK_GCP_PROJECT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    # settings.yaml 側も project_id を削除済みなので RuntimeError になる
    with pytest.raises(RuntimeError):
        get_project_id()


def test_get_project_id_resolves_valid(monkeypatch):
    """正しい値が与えられたら解決できる。"""
    from src._config_loader import get_project_id

    monkeypatch.setenv("ARK_GCP_PROJECT_ID", "my-test-gcp-project")
    assert get_project_id() == "my-test-gcp-project"
