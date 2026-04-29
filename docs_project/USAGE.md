# 他のリポジトリで gitmirror-md を使う手順

このツールを既存の GitLab プロジェクトに導入する手順です。

## 前提条件

- Self-Managed GitLab (CE/EE) が稼働していること
- Docker executor の GitLab Runner が登録済みであること
- 対象プロジェクトで Wiki / Issues が有効になっていること

## 導入手順

### 1. ファイルをコピー

以下のファイル/ディレクトリを対象リポジトリにコピーします。

```
scripts/
  __init__.py
  common.py
  gitlab_client.py
  sync_wiki.py
  sync_issues.py
.gitlab-ci.yml
requirements.txt
docs/
  wiki/.gitkeep
  issues/open/.gitkeep
  issues/closed/.gitkeep
```

### 2. CI/CD 変数を設定

GitLab UI: **Settings → CI/CD → Variables** に以下を追加します。

| Key | Value | 備考 |
|-----|-------|------|
| `SYNC_TOKEN` | Personal Access Token | `api` + `write_repository` scope が必要（詳細は手順3参照） |
| `GITLAB_URL` | `http://your-gitlab-host/` | GitLab インスタンスの URL |

> **注意**: `CI_PROJECT_ID` と `CI_PROJECT_PATH` は GitLab CI が自動で設定するため手動設定は不要です。

> **Docker executor の場合**: Runner のジョブコンテナから GitLab にアクセスできる URL を指定してください。
> `external_url` と Docker ネットワーク内のアクセス先が異なる場合は、サービス名 (例: `http://gitlab/`) を使用します。
> また、Runner の `config.toml` に `clone_url` を設定して、クローン時の URL も合わせてください。

### 3. Personal Access Token を作成

GitLab UI: **User Settings → Access Tokens**

- **Scopes**: `api`, `write_repository`
- **Expiration**: 必要に応じて設定（無期限も可）

このトークンを `SYNC_TOKEN` 変数に設定します。

> **注意**: `api` scope には `read_repository` の権限が含まれるため、別途指定する必要はありません。

### 4. Protected branch の設定

`.gitlab-ci.yml` は `git push origin HEAD:main` で直接 main ブランチに push します。
GitLab ではデフォルトブランチが Protected branch になっているため、`SYNC_TOKEN` のユーザーが push 可能である必要があります。

GitLab UI: **Settings → Repository → Protected branches**

- `main` ブランチの **Allowed to push and merge** にトークンのユーザー（またはそのロール）を追加

### 5. Pipeline Trigger Token を作成

GitLab UI: **Settings → CI/CD → Pipeline trigger tokens**

「Add trigger」でトークンを発行します。このトークンは Webhook の URL に使用します。

### 6. Webhook を設定

GitLab UI: **Settings → Webhooks**

#### Wiki 用 Webhook

- **URL**:
  ```
  http://<GITLAB_HOST>/api/v4/projects/<PROJECT_ID>/trigger/pipeline?token=<TRIGGER_TOKEN>&ref=main&variables[SYNC_TARGET]=wiki
  ```
- **Trigger**: `Wiki page events` にチェック

#### Issue 用 Webhook

- **URL**:
  ```
  http://<GITLAB_HOST>/api/v4/projects/<PROJECT_ID>/trigger/pipeline?token=<TRIGGER_TOKEN>&ref=main&variables[SYNC_TARGET]=issues
  ```
- **Trigger**: `Issues events` と `Note events` にチェック

> `<PROJECT_ID>` は **Settings → General** で確認できます。

### 7. ローカルネットワーク許可（Self-Managed のみ）

Webhook が同一インスタンスの API を叩く場合:

**Admin Area → Settings → Network → Outbound requests**
- `Allow requests to the local network from webhooks and integrations` を有効化

### 8. 動作確認

1. GitLab UI: **Build → Pipelines → Run pipeline** で手動実行
   - `SYNC_TARGET` = `all` で実行
2. パイプラインが成功し、`docs/` 配下にファイルが生成されることを確認
3. Wiki ページを編集 → 自動でパイプラインが起動し `docs/wiki/` が更新されることを確認
4. Issue を作成/コメント追加 → `docs/issues/` が更新されることを確認

## カスタマイズ

### 同期対象の切替

CI 変数 `SYNC_TARGET` で制御:
- `wiki` — Wiki のみ同期
- `issues` — Issue のみ同期
- `all` — 両方同期（デフォルト）

### コミットユーザー名の変更

`.gitlab-ci.yml` の `variables` セクションで変更:

```yaml
variables:
  GIT_AUTHOR_NAME: "your-bot-name"
  GIT_AUTHOR_EMAIL: "bot@your-domain.com"
```

または CI/CD Variables で上書きできます。

### デフォルトブランチの変更

デフォルトブランチが `main` 以外の場合、以下の2箇所を変更してください。

1. `.gitlab-ci.yml` の push 先:
   ```yaml
   git push origin HEAD:your-branch
   ```

2. Webhook URL の `ref` パラメータ:
   ```
   ...&ref=your-branch&variables[SYNC_TARGET]=wiki
   ```

### Runner タグの変更

`.gitlab-ci.yml` の `tags` セクションを環境に合わせて変更:

```yaml
sync:run:
  extends: .sync_base
  tags:
    - your-runner-tag
```

## 手動ファイルの保護

`docs/` 配下に手動でファイルを追加しても、同期時に削除されません。
自動生成ファイルには YAML front matter に `managed_by: gitmirror-md` マーカーが含まれており、
このマーカーがないファイルは削除対象外です。

手動追加ファイルは `index.md` にも「手動追加ページ」「手動追加ファイル」セクションとして反映されます。

## トラブルシューティング

| 症状 | 対処 |
|------|------|
| パイプラインが起動しない | Webhook のログ (Settings → Webhooks → Recent events) を確認。Trigger Token が正しいか確認 |
| `403 Forbidden` | `SYNC_TOKEN` の scope が不足。`api` + `write_repository` が必要 |
| `git push` で権限エラー | トークンのユーザーが対象ブランチに push 可能か確認（Protected branches の設定） |
| `git push` で接続エラー | `GITLAB_URL` が Docker ネットワーク内から到達可能な URL か確認。Runner の `clone_url` 設定も確認 |
| 再帰的にパイプラインが走る | コミットメッセージに `[skip ci]` が含まれているか確認 |
| Wiki が同期されない | Wiki 機能が有効か確認。少なくとも1ページ作成が必要 |
| ローカルネットワークエラー | Admin Area のOutbound requests設定を確認 |
| パイプラインが pending のまま | Runner が正しく登録されているか、tag (`docker`) が一致しているか確認 |
