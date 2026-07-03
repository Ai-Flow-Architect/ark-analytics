# RUNBOOK: 監視を「エラー時にクライアントへメールするだけ」に簡素化

> 対象: ark-analytics（客様案件）/ 改訂: 2026-05-30（最小構成版）/ 実行予定: 同日 +2h セッション
> 屋号: AIフローアーキテクト
> 本書は「2時間後セッションで上から順に実行すれば完了する」粒度。各STEPに成功判定を付す。

---

## 0. 最終仕様（合意済み・最小構成）

**workflow がエラー → クライアント（客様）へメールを1通送るだけ。**

- ❌ Lark Bot通知 … 使用しない（除去）
- ❌ GitHub Issue自動作成 … 除去
- ❌ データ鮮度チェック / Healthchecks.io … 除去
- ✅ メール通知のみ … 宛先 `ARK_CLIENT_EMAIL`・critical限定・客向け文面
- 運用: 客が数値異常やメールに気づく → AIFLOWへ連絡 → AIFLOWが修正（人間リレー）

> ⚠️ トレードオフ（記録のみ）: 「workflowは成功扱いだがデータが古い」型障害（5/8-11事故の型）は鮮度チェック除去により**自動検知できなくなる**。客の気づきに依存する運用として合意。

---

## STEP 1. composite action をメール専用に簡素化

### 1-A. `.github/actions/notify-failure/action.yml` を下記で全面上書き

Lark step・Issue step を削除し、メール1経路のみ・critical限定に。

```yaml
name: "Notify Failure (Client Mail only)"
description: "ワークフロー失敗時にクライアントへメール通知（critical限定・メール1経路）"

inputs:
  smtp_user:
    description: "SMTP送信元アドレス"
    required: true
  smtp_pass:
    description: "SMTP送信元パスワード（Gmailアプリパスワード等）"
    required: true
  alert_recipients:
    description: "通知先メール（カンマ区切り・クライアント宛）"
    required: true
  severity:
    description: "通知重要度（info/warn/critical）。critical のときのみ送信"
    required: false
    default: "critical"

runs:
  using: "composite"
  steps:
    - name: "Send Client Mail (critical only)"
      if: ${{ inputs.severity == 'critical' }}
      continue-on-error: true
      shell: bash
      env:
        SMTP_USER: ${{ inputs.smtp_user }}
        SMTP_PASS: ${{ inputs.smtp_pass }}
        ALERT_RECIPIENTS: ${{ inputs.alert_recipients }}
      run: |
        set +x
        python3 "${{ github.action_path }}/../../../scripts/notify_mail.py"
```

- **成功判定**: yamllint 構文OK / `lark_webhook`・`github_token` 入力が消えている

### 1-B. `scripts/notify_mail.py` を客向け文面で上書き

内部情報（workflow名/step/SHA/run_url/actor）を一切出さない丁寧な業務連絡文に。

```python
"""
notify_mail.py
GitHub Actions composite action `notify-failure` から呼ばれる SMTP 送信スクリプト。
依存ゼロ（標準ライブラリのみ）。宛先はクライアント（ARK_CLIENT_EMAIL）。
技術詳細は出さず、丁寧な業務連絡文のみ送る。

環境変数:
  SMTP_USER, SMTP_PASS : Gmail App Password など
  ALERT_RECIPIENTS     : カンマ区切り宛先（client_email を渡す）
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

    msg = EmailMessage()
    msg["Subject"] = "【AIフローアーキテクト】データ更新に関するご連絡"
    msg["From"] = f"AIフローアーキテクト 監視システム <{user}>"
    msg["To"] = ", ".join(to)
    msg.set_content(
        "いつもお世話になっております。AIフローアーキテクトです。\n\n"
        "ark-analytics のレポートデータ自動更新に一時的な障害を検知いたしました。\n"
        "現在、弊社にて復旧対応を進めております。\n\n"
        "恐れ入りますが、本メール受領後にレポート数値で気になる点がございましたら、\n"
        "弊社までご一報いただけますと幸いです。\n\n"
        "ご不便をおかけし申し訳ございません。引き続き安定稼働に努めてまいります。\n\n"
        "── AIフローアーキテクト 監視システム"
    )

    ctx = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=20) as s:
            s.login(user, pw)
            s.send_message(msg)
        print(f"[notify_mail] sent to {len(to)} recipient(s)")
        return 0
    except Exception as e:
        print(f"[notify_mail] SMTP送信失敗: {type(e).__name__}", file=sys.stderr)
        return 0  # 他処理を止めない


if __name__ == "__main__":
    sys.exit(main())
```

- **成功判定**: `python3 -m py_compile scripts/notify_mail.py` が exit 0

---

## STEP 2. 各 workflow の notify 配線を更新

### 2-A. レポート3本（critical）→ 宛先を客に

対象: `daily_refresh.yml` `weekly_report.yml` `monthly_report.yml`
notify-failure 呼び出しを下記に（lark_webhook / github_token 行を削除）:

```yaml
        uses: ./.github/actions/notify-failure
        with:
          smtp_user:        ${{ secrets.SMTP_USER }}
          smtp_pass:        ${{ secrets.SMTP_PASS }}
          alert_recipients: ${{ secrets.ARK_CLIENT_EMAIL }}
          severity:         "critical"
```

### 2-B. health_check.yml（鮮度チェック）→ 無効化

鮮度チェックは除去方針のため、`health_check.yml` を削除（または `on:` を `workflow_dispatch` のみにして実質停止）。
- 関連: `scripts/check_data_freshness.py` は呼ばれなくなる（削除は任意。残しても無害）
- `HEALTHCHECKS_PING_URL` Secret は不要になる（削除任意）

### 2-C. keepalive.yml（warn）→ notify-failure step 除去

`keepalive.yml`（53行・正常）の末尾 `Notify failure (3 channels)` step（42-53行）を削除。
warn は元々メール送信されない方針だが、`lark_webhook`/`github_token`/`ALERT_RECIPIENTS` 参照が残るため step ごと除去する。

- **成功判定**: `grep -rn "lark_webhook\|github_token\|LARK_BOT_WEBHOOK" .github/` が 0件

---

## STEP 3. テスト（客へ誤送信しない）

⚠️ 宛先が客（ARK_CLIENT_EMAIL）。テストで実際に客へ飛ばさないこと。

1. `notify_mail.py` を **開発者アドレスを ALERT_RECIPIENTS に一時設定してローカル単体実行** → 文面・SMTP疎通を確認
   ```
   ALERT_RECIPIENTS=<開発者宛> SMTP_USER=... SMTP_PASS=... python3 scripts/notify_mail.py
   ```
2. 文面が客向け（内部情報なし）であることを目視確認
3. critical限定ゲートの確認: warn 指定では送信されないこと（action.yml の if 条件）

- **成功判定**: 開発者宛に客向け文面が1通届く / 内部情報の混入なし

---

## STEP 4. ドキュメント・コミット・push（T19-24）

- README に監視の説明を「エラー時クライアントメール通知（メール1経路）」へ更新
- KNOWLEDGE.md に `2026-05-30: 監視を簡素化（メール1経路・客宛）` 追記
- `git diff --cached | grep -E "<本名>|@gmail\.com"` が0件（本名・個人メール非混入。実アドレスはSecret経由のみ）
- pre-commit hook pass → commit `refactor(monitoring): エラー時クライアントメール通知に簡素化`
- push → 全workflow 緑

---

## STEP 5. 案件記録

- CRM メモ追記（クライアント開発進捗ログ記録ルール）
- Lark 開発メモ Doc に `2026-05-30: 監視メールをクライアント向けに簡素化` を1行記録
- クライアントトークルームには送らない（社内運用改善のため）

---

## チェックリスト（当日コピペ用）

- [ ] STEP1-A action.yml メール専用化
- [ ] STEP1-B notify_mail.py 客向け差し替え
- [ ] STEP2-A レポート3本 ARK_CLIENT_EMAIL 参照（lark/github_token削除）
- [ ] STEP2-B health_check.yml 無効化（鮮度チェック除去）
- [ ] STEP2-C keepalive.yml の notify step 除去
- [ ] STEP3 ローカルテスト（客へ誤送信しない）
- [ ] STEP4 doc/commit/push/緑確認
- [ ] STEP5 CRM・Lark Doc 記録

## 不要になったもの（実行しない）

- ~~T4 Lark Webhook 発行・登録~~ → **キャンセル（人手作業ゼロに）**
- LARK_BOT_WEBHOOK Secret 登録不要
- ~~Issue自動作成・鮮度チェック・Healthchecks~~ → 除去
- ※ `src/alert.py` と LARK_APP_* Secret は別レイヤー。今回は触らない
