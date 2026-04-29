# gitmirror-md

GitLab(Self-Managed) の Wiki と Issue を同一リポジトリの `docs/` 配下に Markdown でミラーする CI/CD ツール。

- 同期対象: Wiki 全ページ / Issue 本文 + 全コメント
- コミット先: `main` 直接コミット
- 動作環境: Self-Managed GitLab + GitLab CI/CD
- パッケージ管理: [uv](https://docs.astral.sh/uv/)

## セットアップ

```bash
# 依存インストール
uv sync

# 環境変数（ローカル実行時）
export GITLAB_URL="http://gitlab.local:8080"
export SYNC_TOKEN="your-personal-access-token"
export CI_PROJECT_ID="1"
export CI_PROJECT_PATH="root/sample"
```

## ディレクトリ構成

```
.
├── docker-compose.yml        # テスト用GitLab一式
├── docs_project/
│   ├── CLAUDE_CODE_SPEC.md   # 実装仕様書
│   └── SETUP.md              # ローカル検証環境の構築手順
├── .gitlab-ci.yml            # 同期パイプライン
├── pyproject.toml            # プロジェクト定義 (uv)
├── uv.lock                   # ロックファイル
├── scripts/
│   ├── __init__.py
│   ├── common.py             # 共通ユーティリティ
│   ├── gitlab_client.py      # python-gitlab薄ラッパ
│   ├── sync_wiki.py          # Wiki -> docs/wiki/
│   └── sync_issues.py        # Issues -> docs/issues/{open,closed}/
└── docs/
    ├── wiki/                 # 自動生成(手動編集禁止)
    └── issues/               # 自動生成(手動編集禁止)
        ├── open/
        └── closed/
```

## 使い方

### 手動実行（ローカル）

```bash
# Wiki 同期
uv run python -m scripts.sync_wiki

# Issue 同期
uv run python -m scripts.sync_issues
```

### CI/CD

GitLab CI/CD は Wiki/Issue イベントでは自動起動しないため、Webhook + Pipeline Trigger Token で起動する。
CI 変数 `SYNC_TARGET` で同期対象を制御: `wiki` | `issues` | `all`（デフォルト: `all`）

詳細は `docs_project/SETUP.md` 参照。

## 必要な CI/CD 変数

| 変数 | 説明 |
|------|------|
| `SYNC_TOKEN` | Personal Access Token (`api` + `write_repository` scope) |
| `GITLAB_URL` | GitLab インスタンス URL (例: `http://gitlab/`) |
| `SYNC_TARGET` | 同期対象 `wiki` / `issues` / `all` (任意, デフォルト `all`) |
