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

`external_url` を `gitlab.local:8080` にしているため、以下を hosts ファイルに追記すると Web UI のURLが安定します。

**Windows**: `C:\Windows\System32\drivers\etc\hosts`
**Linux/Mac**: `/etc/hosts`

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
2. Project name: `sync-test`
3. Visibility: Private で OK
4. **Initialize repository with a README** にチェック

作成後、以下を有効化しておきます。

- **Settings → General → Visibility, project features, permissions**
  - Wiki: Enabled
  - Issues: Enabled

## 5. Runner 登録

GitLab UI: **Settings → CI/CD → Runners** から registration token を取得。

```bash
docker exec -it test-gitlab-runner gitlab-runner register \
  --non-interactive \
  --url "http://gitlab/" \
  --registration-token "<REGISTRATION_TOKEN>" \
  --executor "docker" \
  --docker-image "python:3.12-slim" \
  --description "test-runner" \
  --tag-list "docker" \
  --run-untagged="true" \
  --locked="false" \
  --docker-network-mode "gitmirror-md_gitlab-net"
```

> **重要**: `--url` には Docker ネットワーク内のサービス名 `http://gitlab/` を使用してください。
> `--docker-network-mode` は docker-compose のネットワーク名を指定します。`docker network ls` で確認できます。

### Runner の clone_url 設定

Runner がジョブを実行する際、`external_url` の URL をそのまま使ってリポジトリをクローンしようとしますが、Docker ネットワーク内からは `gitlab.local:8080` にアクセスできません。以下の設定で内部 URL を使うようにします。

```bash
docker exec test-gitlab-runner bash -c 'cat >> /etc/gitlab-runner/config.toml << EOF
  [runners.docker]
    network_mode = "gitmirror-md_gitlab-net"
  clone_url = "http://gitlab/"
EOF'

docker exec test-gitlab-runner gitlab-runner restart
```

## 6. ソースコードを push

```bash
git remote add gitlab http://gitlab.local:8080/root/sync-test.git
git push gitlab main
```

## 7. CI/CD 変数の設定

**Settings → CI/CD → Variables** に以下を追加。

| Key | Value | Protected | Masked |
|-----|-------|-----------|--------|
| `SYNC_TOKEN` | 手順3で作ったPAT | No | Yes |
| `GITLAB_URL` | `http://gitlab/` | No | No |

> **重要**: `GITLAB_URL` には Docker ネットワーク内のサービス名を使用します。
> デフォルトの `${CI_SERVER_URL}` は `external_url` の値 (`http://gitlab.local:8080`) になりますが、
> Docker executor のジョブコンテナからはこの URL にアクセスできないため、
> CI 変数で `http://gitlab/` に上書きする必要があります。

## 8. 動作確認

**Build → Pipelines → Run pipeline** から手動実行。

- `SYNC_TARGET` = `all` で実行
- パイプラインが成功し、`docs/` にファイルがコミットされることを確認

## 9. テストの実行

```bash
# ユニットテスト
uv run pytest tests/test_common.py tests/test_sync_wiki.py tests/test_sync_issues.py -v

# 統合テスト (GitLab API)
INTEGRATION_TEST=1 SYNC_TOKEN=<token> uv run pytest tests/test_integration.py -v

# パイプライン E2E テスト (CI/CD)
PIPELINE_TEST=1 SYNC_TOKEN=<token> CI_PROJECT_ID=<id> uv run pytest tests/test_pipeline.py -v
```

## 10. Docker ネットワークの注意事項

`docker-compose.yml` では以下のポート構成を使用しています。

| 設定 | 値 | 説明 |
|------|-----|------|
| `external_url` | `http://gitlab.local:8080` | ブラウザからアクセスする URL |
| `nginx['listen_port']` | `80` | コンテナ内で nginx がリッスンするポート |
| ポートマッピング | `8080:80` | ホストの 8080 → コンテナの 80 |
| Docker 内サービス名 | `gitlab` | Runner からのアクセスに使用 |

`external_url` にポート番号を含めると、nginx が内部でもそのポートでリッスンしようとするため、
`nginx['listen_port'] = 80` を明示する必要があります。

## 11. 停止 / 完全削除

```bash
docker compose down          # 停止のみ(データは残る)
docker compose down -v       # ボリュームごと削除(初期化)
```
