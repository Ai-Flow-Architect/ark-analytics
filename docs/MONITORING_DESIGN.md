# 監視冗長化システム設計書 (MONITORING_DESIGN.md)

> 本書は ark-analytics（GA4 × BigQuery × AIレポート基盤）における
> GitHub Actions 監視冗長化の設計確定版である。
> Vibe coding禁止ゾーン該当（クライアント納品済み本番／障害発生時の損失大）のため、
> WebSearch×3 + 通常レビュー + Red Team + 総括 の 3AI並列設計フロー を経て確定。
>
> 作成日: 2026-05-12 / バージョン: v1.0 / 屋号: AIフローアーキテクト

---

## ① 設計ゴール・要件定義

### 1.1 背景・課題（事故の事実）

- 2026-05-08 〜 2026-05-11 の 4日間、`daily_refresh.yml` が連続failureしたが誰も気づかなかった。
- 失敗時の唯一の証跡が `actions/upload-artifact` によるログ保存のみで、能動的な通知（Lark / Mail / Issue）はゼロ。
- 結果として 5/11 配信予定の Weekly Report が古いデータで（あるいは失敗で）配信され、クライアント信頼を毀損するリスクがあった。

### 1.2 設計ゴール（一行）

> **「1経路の通知が壊れても別経路で気づけて、データ鮮度劣化が起きても自動検知できる」冗長化監視。**

### 1.3 必須要件（4チェーン冗長化）

| # | チェーン | 役割 | 単一障害時のカバー |
|---|----------|------|------------------|
| ① | workflow失敗 → Lark Bot通知 | 即時通知（IM）。1分以内に開発者へ届く一次経路 | Lark死 → ②③で気づける |
| ② | workflow失敗 → GitHub Issue自動作成 | 永続化アラート。閉じない限り残る | Issue未読 → ①③で気づける |
| ③ | workflow失敗 → メール通知 | アウトオブバンド経路（GitHub/Lark独立） | Mail死 → ①②④で気づける |
| ④ | データ鮮度デイリーチェック | "結果"ベース監視。workflow自体が動かなくても気づく | 全部死 → 外部Healthchecks.io ping |

### 1.4 NFR（非機能要件）

| 項目 | 目標 |
|------|------|
| 通知遅延 | failure発生から **5分以内** に最低1経路へ到達 |
| 誤検知率 | 月 **2件以下**（false positive） |
| 通知ループ | composite action 自体の失敗で再帰通知させない |
| 機密保護 | Webhook/SMTP は **全てGitHub Secrets経由**・コード直書きゼロ |
| 匿名性 | 通知文/コード/コミット履歴に **本名・個人メール禁止**。屋号「AIフローアーキテクト」で統一 |
| 月コスト | GitHub Actions無料枠内（追加分数 +30min/月以下） |

### 1.5 NOT-TO-DO（やらないことを先に固定）

- 既存workflowの構造変更（job分割など）はしない。**最終stepの`uses:`追加のみ**。
- Issue を「成功で自動close」する仕組みは初期は入れない（誤close事故防止）。
- `pull_request` トリガーの通知拡張はしない（secret漏洩リスク）。

---

## ② 4チェーン冗長化アーキテクチャ図

```mermaid
flowchart TB
    subgraph EXISTING["既存 workflows (構造は変更しない)"]
        D[daily_refresh.yml]
        W[weekly_report.yml]
        M[monthly_report.yml]
        K[keepalive.yml]
    end

    subgraph COMPOSITE["composite action: .github/actions/notify-failure"]
        N[notify-failure/action.yml]
        N --> L1[curl POST Lark Webhook]
        N --> L2[gh issue create / update]
        N --> L3[smtp send via Python script]
    end

    D -- if: failure() --> N
    W -- if: failure() --> N
    M -- if: failure() --> N
    K -- if: failure() --> N

    subgraph META["メタ監視 (workflow自体の死活)"]
        H[health_check.yml<br/>cron: 毎日 21:00 UTC]
        H --> H1{4 workflow の<br/>last successful run<br/>≦ 48h?}
        H --> H2{BigQuery<br/>marts.daily_kpi_summary<br/>MAX(report_date) ≦ 2日前?}
        H1 -- NG --> N
        H2 -- NG --> N
    end

    subgraph EXTERNAL["外部 Dead Man Switch (Healthchecks.io)"]
        E[health_check.yml が<br/>毎日 ping]
        E -- 30h ping無し --> ECC[外部メール/Lark へ自動アラート]
    end

    H --> E

    N --> LARK[(Lark Bot<br/>ClaudeCode-Bot)]
    N --> ISSUE[(GitHub Issue<br/>label: monitoring-alert)]
    N --> MAIL[(SMTP → ALERT_RECIPIENTS)]

    classDef chain fill:#e1f5ff,stroke:#0288d1
    classDef meta fill:#fff3e0,stroke:#f57c00
    classDef ext fill:#f3e5f5,stroke:#7b1fa2
    class N,L1,L2,L3 chain
    class H,H1,H2 meta
    class E,ECC ext
```

### 2.1 冗長化の論理表（どこが壊れても気づく）

| 壊れた経路 | 残りで気づくルート |
|------------|-------------------|
| Lark Bot 障害 | Issue自動作成 / Mail / health_check |
| GitHub Issue（権限障害） | Lark / Mail / health_check |
| SMTP障害（Gmailアプリパス失効） | Lark / Issue / health_check |
| GitHub Actions全体停止 | 外部Healthchecks.io が30h ping無しで検知 |
| BigQuery書き込み停止（workflowは成功扱い） | health_check.yml の MAX(report_date) チェックで検知 |
| health_check.yml 自体が無効化 | 外部Healthchecks.io が ping欠落で検知 |

---

## ③ 各チェーンの実装ファイル一覧・サンプルYAML

### 3.1 ファイル構成

```
ark-analytics/
├── .github/
│   ├── actions/
│   │   └── notify-failure/
│   │       └── action.yml          # NEW: composite action（3通知を順次叩く）
│   ├── workflows/
│   │   ├── daily_refresh.yml       # MODIFY: 末尾に uses: ./.github/actions/notify-failure
│   │   ├── weekly_report.yml       # MODIFY: 同上
│   │   ├── monthly_report.yml      # MODIFY: 同上
│   │   ├── keepalive.yml           # MODIFY: 同上
│   │   └── health_check.yml        # NEW: メタ監視 + 鮮度チェック + Healthchecks.io ping
│   └── ISSUE_TEMPLATE/
│       └── monitoring_alert.md     # NEW: 自動Issue雛形
└── scripts/
    └── notify_mail.py              # NEW: SMTP送信（dawidd6を使わず自前で・依存削減）
```

### 3.2 composite action: `.github/actions/notify-failure/action.yml`

```yaml
name: "Notify Failure (Lark + Issue + Mail)"
description: "ワークフロー失敗時に Lark Bot / GitHub Issue / SMTP メール の3経路を順次叩く（個別失敗は許容）"

inputs:
  lark_webhook:
    description: "Lark Bot Incoming Webhook URL（GitHub Secret経由で渡すこと）"
    required: true
  smtp_user:
    description: "SMTP送信元アドレス"
    required: true
  smtp_pass:
    description: "SMTP送信元パスワード（Gmailアプリパスワード等）"
    required: true
  alert_recipients:
    description: "通知先メール（カンマ区切り）"
    required: true
  github_token:
    description: "Issue作成用GITHUB_TOKEN"
    required: true
  failed_step:
    description: "失敗したstep名（任意・分かれば渡す）"
    required: false
    default: "unknown"
  severity:
    description: "通知重要度（info/warn/critical）"
    required: false
    default: "critical"

runs:
  using: "composite"
  steps:
    # ---------- ① Lark Bot 通知 ----------
    - name: "[1/3] Notify Lark Bot"
      if: always()
      continue-on-error: true
      shell: bash
      env:
        LARK_WEBHOOK: ${{ inputs.lark_webhook }}
      run: |
        set +x  # secret漏洩防止: コマンドエコー禁止
        PAYLOAD=$(cat <<EOF
        {
          "msg_type": "post",
          "content": {
            "post": {
              "ja_jp": {
                "title": "[AIフローアーキテクト] ${{ github.workflow }} 失敗",
                "content": [
                  [{"tag": "text", "text": "Workflow: ${{ github.workflow }}"}],
                  [{"tag": "text", "text": "Failed step: ${{ inputs.failed_step }}"}],
                  [{"tag": "text", "text": "Severity: ${{ inputs.severity }}"}],
                  [{"tag": "text", "text": "Commit: ${{ github.sha }}"}],
                  [{"tag": "text", "text": "Actor: ${{ github.actor }}"}],
                  [{"tag": "a", "text": "View run logs", "href": "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"}]
                ]
              }
            }
          }
        }
        EOF
        )
        # 通知ループ防止: 1回のみPOST、リトライしない
        curl --max-time 15 --silent --show-error \
          -X POST -H "Content-Type: application/json" \
          --data "$PAYLOAD" "$LARK_WEBHOOK" || echo "[notify-failure] Lark POST failed (continuing)"

    # ---------- ② GitHub Issue 自動作成 ----------
    - name: "[2/3] Open or Update GitHub Issue"
      if: always()
      continue-on-error: true
      uses: actions/github-script@v7
      with:
        github-token: ${{ inputs.github_token }}
        script: |
          const workflow = "${{ github.workflow }}";
          const runUrl = `${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}`;
          const label = "monitoring-alert";
          const title = `[ALERT] ${workflow} failed (auto-opened)`;

          // 通知ループ防止: 既存open Issue（同workflow / 24h以内）があれば更新のみ
          const existing = await github.rest.issues.listForRepo({
            owner: context.repo.owner,
            repo:  context.repo.repo,
            state: "open",
            labels: label,
            per_page: 30,
          });
          const since = new Date(Date.now() - 24 * 60 * 60 * 1000);
          const dup = existing.data.find(i =>
            i.title.includes(workflow) && new Date(i.updated_at) > since
          );

          const body = [
            `## Workflow失敗を自動検知しました`,
            ``,
            `- Workflow: \`${workflow}\``,
            `- Failed step: \`${{ inputs.failed_step }}\``,
            `- Severity: \`${{ inputs.severity }}\``,
            `- Commit SHA: \`${{ github.sha }}\``,
            `- Actor: \`${{ github.actor }}\``,
            `- Run URL: ${runUrl}`,
            ``,
            `> このIssueは notify-failure composite action が自動生成しました。`,
            `> 24h以内の同一workflow失敗はこのIssueに追記されます。`,
            `> 復旧したら手動でcloseしてください（誤close事故防止のため自動closeは無効）。`,
          ].join("\n");

          if (dup) {
            await github.rest.issues.createComment({
              owner: context.repo.owner, repo: context.repo.repo,
              issue_number: dup.number,
              body: `### 再発検知 (${new Date().toISOString()})\n\n${body}`,
            });
            core.notice(`Updated existing issue #${dup.number}`);
          } else {
            const created = await github.rest.issues.create({
              owner: context.repo.owner, repo: context.repo.repo,
              title, body, labels: [label, "automated"],
            });
            core.notice(`Created new issue #${created.data.number}`);
          }

    # ---------- ③ SMTP メール通知 ----------
    - name: "[3/3] Send SMTP Mail (out-of-band)"
      if: always()
      continue-on-error: true
      shell: bash
      env:
        SMTP_USER: ${{ inputs.smtp_user }}
        SMTP_PASS: ${{ inputs.smtp_pass }}
        ALERT_RECIPIENTS: ${{ inputs.alert_recipients }}
        WORKFLOW_NAME: ${{ github.workflow }}
        RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
        FAILED_STEP: ${{ inputs.failed_step }}
        SEVERITY: ${{ inputs.severity }}
        COMMIT_SHA: ${{ github.sha }}
        ACTOR: ${{ github.actor }}
      run: |
        set +x
        python3 "${{ github.action_path }}/../../../scripts/notify_mail.py"
```

### 3.3 SMTP 送信スクリプト: `scripts/notify_mail.py`

> `dawidd6/action-send-mail@v3` 等の外部actionに依存せず、Pythonの標準ライブラリのみで実装。
> サプライチェーン攻撃面を減らす（Red Team 指摘②）。

```python
"""
notify_mail.py
GitHub Actions composite action `notify-failure` から呼ばれる SMTP 送信スクリプト。
依存ゼロ（標準ライブラリのみ）でサプライチェーン攻撃面を最小化する。

環境変数:
  SMTP_USER, SMTP_PASS         : Gmail App Password など
  ALERT_RECIPIENTS              : カンマ区切り宛先
  WORKFLOW_NAME, RUN_URL, FAILED_STEP, SEVERITY, COMMIT_SHA, ACTOR : 通知ペイロード
"""
from __future__ import annotations
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage


def main() -> int:
    user = os.environ.get("SMTP_USER", "").strip()
    pw   = os.environ.get("SMTP_PASS", "").strip()
    to   = [a.strip() for a in os.environ.get("ALERT_RECIPIENTS", "").split(",") if a.strip()]

    if not (user and pw and to):
        print("[notify_mail] SMTP_USER / SMTP_PASS / ALERT_RECIPIENTS のいずれか未設定。スキップ。")
        return 0  # continue-on-error と整合（失敗扱いにしない）

    wf  = os.environ.get("WORKFLOW_NAME", "unknown")
    url = os.environ.get("RUN_URL", "")
    step = os.environ.get("FAILED_STEP", "unknown")
    sev = os.environ.get("SEVERITY", "critical")
    sha = os.environ.get("COMMIT_SHA", "")
    actor = os.environ.get("ACTOR", "")

    msg = EmailMessage()
    msg["Subject"] = f"[AIフローアーキテクト][ALERT] {wf} 失敗 (sev={sev})"
    msg["From"] = f"AIフローアーキテクト 監視Bot <{user}>"
    msg["To"] = ", ".join(to)
    msg.set_content(
        "ark-analytics 監視冗長化システムからの通知です。\n\n"
        f"Workflow   : {wf}\n"
        f"Failed step: {step}\n"
        f"Severity   : {sev}\n"
        f"Commit SHA : {sha}\n"
        f"Actor      : {actor}\n"
        f"Run URL    : {url}\n\n"
        "復旧手順:\n"
        "  1) Run URL のログを確認\n"
        "  2) 24h以内なら GitHub Issue (label: monitoring-alert) にも記録あり\n"
        "  3) 修正後、該当Issueを手動closeしてください\n\n"
        "-- AIフローアーキテクト 監視冗長化システム"
    )

    ctx = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=20) as s:
            s.login(user, pw)
            s.send_message(msg)
        print(f"[notify_mail] sent to {len(to)} recipient(s)")
        return 0
    except Exception as e:
        # 機密(pw)をstderrに混ぜないため repr せずクラス名のみ
        print(f"[notify_mail] SMTP送信失敗: {type(e).__name__}", file=sys.stderr)
        return 0  # composite action 全体は止めない（他チェーン優先）


if __name__ == "__main__":
    sys.exit(main())
```

### 3.4 health_check.yml（メタ監視 + データ鮮度 + 外部ping）

```yaml
name: Health Check (Meta Monitoring)

# メタ監視: 「workflow自体が動いていない」「BQデータが古い」を毎日検知
# 既存4 workflowが全滅しても、これだけは外部Healthchecks.io 経由で検知される

on:
  schedule:
    # 毎日 21:00 UTC = 翌日 JST AM 6:00（daily_refresh の2時間後）
    - cron: '0 21 * * *'
  workflow_dispatch:

permissions:
  contents: read
  actions: read     # GitHub API /actions/runs 読み取り
  issues: write     # notify-failure 用

jobs:
  health-check:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      # ---------- (A) 既存workflowの「last successful run」を48h閾値でチェック ----------
      - name: Check workflow run freshness (meta)
        id: meta_check
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
        run: |
          set -euo pipefail
          THRESHOLD_HOURS=48
          NOW_EPOCH=$(date -u +%s)
          FAILED=""
          for WF in daily_refresh.yml weekly_report.yml monthly_report.yml; do
            LATEST_SUCCESS_AT=$(gh api \
              "repos/${GITHUB_REPOSITORY}/actions/workflows/${WF}/runs?status=success&per_page=1" \
              --jq '.workflow_runs[0].updated_at // empty')
            if [ -z "$LATEST_SUCCESS_AT" ]; then
              echo "::warning ::${WF} に成功実行履歴がありません"
              FAILED="${FAILED} ${WF}(no-success)"
              continue
            fi
            LAST_EPOCH=$(date -u -d "$LATEST_SUCCESS_AT" +%s)
            DIFF_HOURS=$(( (NOW_EPOCH - LAST_EPOCH) / 3600 ))
            echo "${WF}: last success ${DIFF_HOURS}h ago"
            # weekly_report は168h(7日)、monthly_reportは744h(31日)許容
            case "$WF" in
              daily_refresh.yml)   LIMIT=48 ;;
              weekly_report.yml)   LIMIT=168 ;;
              monthly_report.yml)  LIMIT=744 ;;
            esac
            if [ "$DIFF_HOURS" -gt "$LIMIT" ]; then
              FAILED="${FAILED} ${WF}(${DIFF_HOURS}h>${LIMIT}h)"
            fi
          done
          if [ -n "$FAILED" ]; then
            echo "META_FAILED=$FAILED" >> "$GITHUB_OUTPUT"
            echo "::error ::Stale workflows detected:$FAILED"
            exit 1
          fi

      # ---------- (B) BQ データ鮮度チェック（既存スクリプト流用） ----------
      - name: Authenticate to Google Cloud
        if: success() || failure()
        uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SERVICE_ACCOUNT_KEY }}

      - name: Check BigQuery freshness
        if: success() || failure()
        id: bq_check
        env:
          ARK_GCP_PROJECT_ID: ${{ secrets.ARK_GCP_PROJECT_ID }}
          GOOGLE_CLOUD_PROJECT: ${{ secrets.ARK_GCP_PROJECT_ID }}
          LARK_APP_ID: ${{ secrets.LARK_APP_ID }}
          LARK_APP_SECRET: ${{ secrets.LARK_APP_SECRET }}
          LARK_CHAT_ID: ${{ secrets.LARK_CHAT_ID }}
        run: |
          python3 scripts/check_data_freshness.py --threshold-days 2 --source health_check

      # ---------- (C) 外部 Healthchecks.io へ生存ping（success時のみ） ----------
      - name: Ping external dead man switch (Healthchecks.io)
        if: success()
        env:
          HC_URL: ${{ secrets.HEALTHCHECKS_PING_URL }}
        run: |
          set +x
          if [ -z "${HC_URL:-}" ]; then
            echo "[health_check] HEALTHCHECKS_PING_URL 未設定、pingスキップ"
            exit 0
          fi
          curl --max-time 10 --retry 2 --silent --show-error "$HC_URL" || true

      # ---------- (D) 失敗時は 3経路通知 ----------
      - name: Notify failure (3 channels)
        if: failure()
        uses: ./.github/actions/notify-failure
        with:
          lark_webhook:     ${{ secrets.LARK_BOT_WEBHOOK }}
          smtp_user:        ${{ secrets.SMTP_USER }}
          smtp_pass:        ${{ secrets.SMTP_PASS }}
          alert_recipients: ${{ secrets.ALERT_RECIPIENTS }}
          github_token:     ${{ secrets.GITHUB_TOKEN }}
          failed_step:      "meta_or_bq_check"
          severity:         "critical"
```

### 3.5 既存3 workflow への追記（最小差分）

`daily_refresh.yml` / `weekly_report.yml` / `monthly_report.yml` の末尾に以下stepを追加。
`keepalive.yml` も同様（severity: warn）。

```yaml
      # ---------- 失敗時の冗長化通知 ----------
      - name: Notify failure (3 channels)
        if: failure()
        uses: ./.github/actions/notify-failure
        with:
          lark_webhook:     ${{ secrets.LARK_BOT_WEBHOOK }}
          smtp_user:        ${{ secrets.SMTP_USER }}
          smtp_pass:        ${{ secrets.SMTP_PASS }}
          alert_recipients: ${{ secrets.ALERT_RECIPIENTS }}
          github_token:     ${{ secrets.GITHUB_TOKEN }}
          failed_step:      ${{ steps.<該当step_id>.outcome == 'failure' && '<step_id>' || 'unknown' }}
          severity:         "critical"
```

> 既存`upload-artifact` step は **削除せず残す**（ログ証跡保全）。追加するのは通知stepのみ。

### 3.6 Issue Template: `.github/ISSUE_TEMPLATE/monitoring_alert.md`

```markdown
---
name: Monitoring Alert (auto)
about: notify-failure composite action が自動作成するテンプレ
title: '[ALERT] <workflow> failed (auto-opened)'
labels: monitoring-alert, automated
---

このIssueは自動作成されました。手動編集する場合は以下に対応状況を追記してください。

## 状況
- [ ] 1次調査完了
- [ ] 根本原因特定
- [ ] 修正PR作成
- [ ] 復旧確認

## 関連リンク
- Run URL:
- 関連commit:
```

---

## ④ 3AI差分マトリクス

| # | 指摘者 | 指摘内容 | 採否 | 理由・実装場所 |
|---|--------|----------|------|---------------|
| 1 | WebSearch | composite actionは shell明示必須 | ✅採用 | 全shell stepに `shell: bash` 明記（3.2） |
| 2 | WebSearch | scheduled workflowは遅延・スキップ頻発 | ✅採用 | だからこそ ④health_check + 外部Healthchecks.io で二重化 |
| 3 | WebSearch | Lark webhook payloadは `msg_type:post` でリンク埋込可 | ✅採用 | Larkの richtext post形式採用（3.2） |
| 4 | WebSearch | dead man switch は外部サービス推奨 | ✅採用 | Healthchecks.io ping 経路を追加（3.4 step C） |
| 5 | 通常レビュー(GPT) | Lark/Mail/GitHub 同時ダウン非考慮 | ✅採用 | 外部Healthchecks.io が第5経路として独立（GitHub障害も検知） |
| 6 | 通常レビュー(GPT) | composite input にエラー詳細を追加 | ✅採用 | `failed_step` / `severity` を input に追加 |
| 7 | 通常レビュー(GPT) | Issue大量作成でnoise化 | ✅採用 | 24h以内の同workflow Issueはコメント追記のみ（3.2 ②） |
| 8 | 通常レビュー(GPT) | health_checkは GitHub API + 閾値判定 | ✅採用 | `gh api workflows/.../runs?status=success` 方式（3.4 step A） |
| 9 | 通常レビュー(GPT) | 通知ループ防止のバックオフ | ⚠️部分採用 | リトライしない単発POST + continue-on-error。指数バックオフは過剰のため不採用 |
| 10 | Red Team | Secrets漏洩（ログ出力） | ✅採用 | 全shell stepに `set +x` 明記。`type(e).__name__` のみ出力 |
| 11 | Red Team | 通知ループ / 洪水（DoS） | ✅採用 | (a)curlリトライ0回 (b)24h Issue集約 (c)composite自身は再帰呼出しなし |
| 12 | Red Team | pull_request から secret 抜き取り | ✅採用 | health_check.yml の `on:` は `schedule` + `workflow_dispatch` のみ。`pull_request*` トリガー禁止を本書で明文化 |
| 13 | Red Team | サプライチェーン攻撃面 | ✅採用 | `dawidd6/action-send-mail` 等の外部actionを廃し、自前 `notify_mail.py`（標準ライブラリのみ）に置換 |
| 14 | Red Team | SAキー期限切れ・権限失効 | ✅採用 | freshness check が「BQ参照失敗」を即検知（exit 1 → 通知） |
| 15 | Red Team | health_check.yml 自身の無効化 | ✅採用 | 外部Healthchecks.io が30h ping欠落で独立アラート |
| 16 | Red Team | SMTP失敗時の機密漏洩 | ✅採用 | `repr(e)` 禁止・`type(e).__name__` のみ |
| 17 | Plan(総括) | 既存`src/alert.py`との責務分離 | ✅採用 | composite action = GHA層の通知 / `src/alert.py` = Python層の通知（既存維持・触らない） |
| 18 | Plan(総括) | Issue自動closeは不採用 | ✅採用 | 誤close事故回避のため手動close運用（テンプレに明記） |

---

## ⑤ 障害シナリオ別 動作確認表（6シナリオ）

| # | 障害 | 検知経路 | 想定通知遅延 | フェイルセーフ動作 |
|---|------|----------|-------------|------------------|
| S1 | Lark Webhook死亡（Larkサービス停止） | ② Issue + ③ Mail + ④ health_check | < 5分 | curl `--max-time 15` で諦め、`continue-on-error` で②③実行 |
| S2 | GitHub Actions全体停止 | 外部Healthchecks.io（30h ping欠落） | 〜30h | 開発者個人メール（屋号アドレス）に外部から直接アラート |
| S3 | SMTP死亡（Gmailアプリパス失効） | ① Lark + ② Issue + ④ health_check | < 5分 | `notify_mail.py` が type名のみログに出して return 0 |
| S4 | BQ書き込み停止（refreshは成功扱い） | ④ health_check のMAX(report_date)検査 | < 24h（翌朝6時JST） | `check_data_freshness.py` exit 1 → notify-failure 起動 |
| S5 | health_check.yml 無効化（60日活動なしルール等） | 外部Healthchecks.io（30h ping欠落） | 〜30h | 既存`keepalive.yml`も毎月走るので二重防御 |
| S6 | SA鍵期限切れ（GCP_SERVICE_ACCOUNT_KEY） | ④ health_check step B 即失敗 → 通知 | < 24h | google-github-actions/auth@v2 が401で落ちる→`if: failure()` で通知 |

---

## ⑥ 必要な GitHub Secrets 一覧

| Secret 名 | 用途 | 形式 | 既存 / 新規 |
|-----------|------|------|------------|
| `GCP_SERVICE_ACCOUNT_KEY` | BQ認証 | JSON文字列 | 既存 |
| `ARK_GCP_PROJECT_ID` | BQプロジェクトID | string | 既存 |
| `ARK_GA4_PROPERTY_ID` | GA4 PID | string | 既存 |
| `ARK_GA4_RAW_DATASET` | GA4 raw dataset | string | 既存 |
| `LARK_APP_ID` / `LARK_APP_SECRET` / `LARK_CHAT_ID` | 既存`src/alert.py` 用（Bot API） | string | 既存 |
| `OPENAI_API_KEY` / `ARK_OPENAI_API_KEY` | レポート生成 | string | 既存 |
| `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` | Weekly/Monthly レポート送信 | string | 既存 |
| `ARK_CLIENT_EMAIL` / `ARK_CC_EMAILS` | クライアント宛 | string | 既存 |
| **`LARK_BOT_WEBHOOK`** | **NEW: notify-failure Lark経路** | URL | **新規** |
| **`SMTP_USER`** | **NEW: 監視通知用送信元（既存GMAIL_ADDRESSと別アカ推奨）** | email | **新規** |
| **`SMTP_PASS`** | **NEW: SMTP_USER のアプリパスワード** | string | **新規** |
| **`ALERT_RECIPIENTS`** | **NEW: 通知先（カンマ区切り）** | string | **新規** |
| **`HEALTHCHECKS_PING_URL`** | **NEW: 外部dead man switch** | URL | **新規** |

> ⚠️ 機密値は **絶対にコードに直書きしない**。`*.example` ファイルにダミー値を置く程度に留める。
> ⚠️ Secret 名・値の追加時は `~/.config/credentials/` にも保存し `memory/reference_credentials.md` を更新する（認証情報セキュア保存ルール準拠）。
> ⚠️ `ALERT_RECIPIENTS` に本名アドレスを入れる場合も、コミット履歴・通知文には **絶対に出さない**（Secret経由のみ・参照は `${{ secrets.* }}`）。

---

## ⑦ 実装ToDoリスト（後続Claude実装エージェント向け）

> 上から順に実行すれば完了する粒度に分解。各タスクに「成功判定」を付ける。

### Phase 1: composite action と SMTP スクリプト

- [ ] **T1.** `.github/actions/notify-failure/action.yml` を本書 3.2 のYAMLで新規作成
  - 成功判定: ファイルが存在し yamllint で構文OK
- [ ] **T2.** `scripts/notify_mail.py` を本書 3.3 のコードで新規作成
  - 成功判定: `python3 -m py_compile scripts/notify_mail.py` がexit 0
- [ ] **T3.** `.github/ISSUE_TEMPLATE/monitoring_alert.md` を本書 3.6 で新規作成
  - 成功判定: GitHub UIで Issue作成時にテンプレが選択肢に出る

### Phase 2: GitHub Secrets 登録

- [ ] **T4.** Lark Bot Incoming Webhook を新規発行し `LARK_BOT_WEBHOOK` をSecretsに登録
  - 成功判定: `gh secret list` に表示される
- [ ] **T5.** Gmail で監視通知専用アプリパスワードを発行し `SMTP_USER` / `SMTP_PASS` を登録（既存 `GMAIL_*` とは別アカ推奨）
- [ ] **T6.** `ALERT_RECIPIENTS` をカンマ区切りで登録（本名アドレスはここのみ・コード非出現）
- [ ] **T7.** Healthchecks.io で新規checkを作成（schedule: daily, grace 6h）し `HEALTHCHECKS_PING_URL` を登録

### Phase 3: health_check.yml 新規作成

- [ ] **T8.** `.github/workflows/health_check.yml` を本書 3.4 で新規作成
  - 成功判定: `gh workflow run health_check.yml` で手動実行 → 全step success
- [ ] **T9.** Healthchecks.io ダッシュボードで初回ping受信を確認

### Phase 4: 既存4 workflow に通知step追加

- [ ] **T10.** `.github/workflows/daily_refresh.yml` の末尾に notify-failure step を追加（severity: critical）
- [ ] **T11.** `.github/workflows/weekly_report.yml` に追加（severity: critical）
- [ ] **T12.** `.github/workflows/monthly_report.yml` に追加（severity: critical）
- [ ] **T13.** `.github/workflows/keepalive.yml` に追加（severity: warn）
  - 成功判定: 各workflowの `workflow_dispatch` 実行→**意図的に1step失敗させて** Lark / Issue / Mail が全部届くこと

### Phase 5: 動作確認（5シナリオ）

- [ ] **T14.** Lark Webhook を空文字に置き換えた状態で意図失敗 → Issue + Mail が届くこと（S1模擬）
- [ ] **T15.** `SMTP_PASS` を不正値にして意図失敗 → Lark + Issue が届くこと（S3模擬）
- [ ] **T16.** `check_data_freshness.py --threshold-days 0` で意図失敗 → 全経路通知（S4模擬）
- [ ] **T17.** 連続2回失敗させて Issueが**新規ではなく既存にコメント追記**されること（noise抑制確認）
- [ ] **T18.** Healthchecks.io ダッシュボードで日次pingが正常受信されることを24h観測（S2/S5の備え）

### Phase 6: ドキュメント・引き継ぎ

- [ ] **T19.** `README.md` の運用セクションに「監視冗長化（4チェーン）」の概要を追記（本書へのリンクのみ）
- [ ] **T20.** `KNOWLEDGE.md` に「2026-05-12: 監視冗長化システム導入（事故再発防止）」を追記
- [ ] **T21.** クライアント向けトークルームには **送らない**（運用改善のため、社内のみ）。代わりに Lark 開発メモDocに進捗を1行記録

### Phase 7: コミット・push

- [ ] **T22.** `git status` で本名・個人メールが含まれていないことを確認
  - 成功判定: `git diff --cached | grep -E "kosuke|@gmail\.com"` がヒット0件
- [ ] **T23.** pre-commit hook が pass することを確認してcommit
  - メッセージ例: `feat(monitoring): 4チェーン冗長化監視システム導入（事故再発防止）`
- [ ] **T24.** push → GitHub上で全workflow が緑になることを確認

---

## 付録 A: 既存資産との責務分離

| 層 | コンポーネント | 責務 |
|----|---------------|------|
| GHA層 | `notify-failure/action.yml` | workflow失敗の即時通知（Lark Webhook / Issue / Mail） |
| Python層 | `src/alert.py` | Pythonスクリプト内の例外をLark Bot APIで通知（Webhookと別経路・Bot API使用） |
| Pythonバッチ層 | `scripts/check_data_freshness.py` | BQ MAX(report_date) 監視。失敗時 `src/alert.py` 呼出 + exit 1 |
| メタ監視層 | `health_check.yml` | 上記Pythonバッチを毎日起動 + GitHub APIで全workflow最終成功時刻監査 |
| 外部監視層 | Healthchecks.io | 上記`health_check.yml`自体の生存監視（30h ping欠落で発報） |

「既存資産を生かしつつ、足りない経路（Webhook / Issue / Mail / 外部DMS）だけを追加」する設計。
Python層 (`src/alert.py`) は触らない。

## 付録 B: 運用ルール（事故再発防止）

1. **新規workflow追加時のチェックリスト**: 末尾に `uses: ./.github/actions/notify-failure` を必ず入れる（PRレビュー必須項目）
2. **Secret ローテーション時**: ローテ翌日に `gh workflow run health_check.yml` を手動実行して通知到達確認
3. **月次レビュー**: `monitoring-alert` ラベルの Issue を月初に棚卸し（誤検知率・対応工数を測定）
4. **本書の更新タイミング**: 通知経路を追加・撤去するたびに本書 ②④⑤⑥ を更新

---

(End of MONITORING_DESIGN.md)
