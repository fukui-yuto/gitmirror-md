# テスト用 GitLab セットアップ手順

ローカルに Self-Managed GitLab を docker-compose で立て、Wiki/Issue 同期の動作確認を行うための環境です。

## 1. 起動

```bash
docker compose up -d
```

初回起動は GitLab の初期化に **3〜5分** かかります。以下で起動完了を確認してください。

```bash
docker compose logs -f gitlab | grep -i "gitlab Reconfigured"
# または
curl -fsS http://localhost:8080/-/health
```

## 2. hosts 設定(任意だが推奨)

`external_url` を `gitlab.local:8080` にしているため、以下を `/etc/hosts` に追記すると Web UI / git clone のURLが安定します。

```
127.0.0.1   gitlab.local
```

ブラウザで `http://gitlab.local:8080` にアクセス。

## 3. 初回ログイン

- ユーザ名: `root`
- パスワード: `RootPass12345!`(`docker-compose.yml` の `initial_root_password`)

ログイン後、**User Settings → Access Tokens** で Personal Access Token を発行します。

- Scopes: `api`, `read_repository`, `write_repository`
- このトークンを後述の CI/CD 変数 `SYNC_TOKEN` に登録します。

## 4. テスト用プロジェクト作成

1. New Project → Create blank project
2. Project name: `wiki-issue-sync-test`
3. Visibility: Private で OK
4. **Initialize repository with a README** にチェック

作成後、以下を有効化しておきます。

- **Settings → General → Visibility, project features, permissions**
  - Wiki: Enabled
  - Issues: Enabled
- **Settings → Webhooks**(後述、同期トリガー用)

## 5. Runner 登録

```bash
# GitLab UI: Settings → CI/CD → Runners から registration token を取得
docker exec -it test-gitlab-runner gitlab-runner register \
  --non-interactive \
  --url "http://gitlab.local:8080/" \
  --registration-token "<REGISTRATION_TOKEN>" \
  --executor "docker" \
  --docker-image "python:3.12-slim" \
  --description "test-docker-runner" \
  --tag-list "docker,sync" \
  --run-untagged="true" \
  --locked="false" \
  --docker-network-mode "gitlab-wiki-issue-sync_gitlab-net"
```

> `gitlab.local` は Runner コンテナからも名前解決できる必要があります。`docker-compose.yml` で同一ネットワーク (`gitlab-net`) に置いているため、サービス名 `gitlab` でもアクセス可能です。プロジェクト URL を `http://gitlab/` で登録しても動きます。

## 6. このリポジトリを push

```bash
git init
git remote add origin http://gitlab.local:8080/root/wiki-issue-sync-test.git
git add .
git commit -m "initial: wiki/issue sync skeleton"
git push -u origin main
```

## 7. CI/CD 変数の設定

**Settings → CI/CD → Variables** に以下を追加。

| Key | Value | Protected | Masked |
|-----|-------|-----------|--------|
| `SYNC_TOKEN` | 手順3で作ったPAT | No | Yes |
| `GIT_AUTHOR_NAME` | `wiki-issue-sync-bot` | No | No |
| `GIT_AUTHOR_EMAIL` | `bot@gitlab.local` | No | No |

## 8. 停止 / 完全削除

```bash
docker compose down          # 停止のみ(データは残る)
docker compose down -v       # ボリュームごと削除(初期化)
```
