# gitmirror-md

GitLab(Self-Managed) の Wiki と Issue を同一リポジトリの `docs/` 配下に Markdown でミラーする CI/CD ツール。

- 同期対象: Wiki 全ページ / Issue 本文 + 全コメント
- コミット先: `main` 直接コミット
- 動作環境: Self-Managed GitLab + GitLab CI/CD (Docker executor)
- パッケージ管理: [uv](https://docs.astral.sh/uv/)

## セットアップ

```bash
# 依存インストール
uv sync

# 環境変数（ローカル実行時）
export GITLAB_URL="http://your-gitlab-host/"
export SYNC_TOKEN="your-personal-access-token"
export CI_PROJECT_ID="1"
export CI_PROJECT_PATH="root/sample"
```

## ディレクトリ構成

```
.
├── docker-compose.yml        # テスト用GitLab環境
├── .gitlab-ci.yml            # 同期パイプライン
├── pyproject.toml            # プロジェクト定義 (uv)
├── uv.lock                   # ロックファイル
├── requirements.txt          # pip 用依存定義 (CI で使用)
├── scripts/
│   ├── __init__.py
│   ├── common.py             # 共通ユーティリティ
│   ├── gitlab_client.py      # python-gitlab薄ラッパ
│   ├── sync_wiki.py          # Wiki -> docs/wiki/
│   └── sync_issues.py        # Issues -> docs/issues/{open,closed}/
├── tests/
│   ├── test_common.py        # 共通ユーティリティのユニットテスト (21件)
│   ├── test_sync_wiki.py     # Wiki同期のユニットテスト (5件)
│   ├── test_sync_issues.py   # Issue同期のユニットテスト (8件) [残り6件は省略]
│   ├── test_integration.py   # 統合テスト: GitLab API 直接 (9件)
│   └── test_pipeline.py      # パイプライン統合テスト: CI/CD E2E (6件)
├── docs/
│   ├── wiki/                 # 自動生成 (Wiki ミラー)
│   └── issues/               # 自動生成 (Issue ミラー)
│       ├── open/
│       └── closed/
└── docs_project/
    ├── CLAUDE_CODE_SPEC.md   # 実装仕様書
    ├── SETUP.md              # テスト環境構築手順
    └── USAGE.md              # 他リポジトリでの導入ガイド
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

詳細は `docs_project/USAGE.md` 参照。

## 必要な CI/CD 変数

| 変数 | 説明 |
|------|------|
| `SYNC_TOKEN` | Personal Access Token (`api` + `write_repository` scope) |
| `GITLAB_URL` | GitLab インスタンス URL (例: `http://gitlab/`)。Docker 環境ではサービス名を使用 |
| `SYNC_TARGET` | 同期対象 `wiki` / `issues` / `all` (任意, デフォルト `all`) |

## テスト

```bash
# ユニットテスト (40件)
uv run pytest tests/test_common.py tests/test_sync_wiki.py tests/test_sync_issues.py -v

# 統合テスト (GitLab API, 9件) — 要 GitLab 起動
INTEGRATION_TEST=1 SYNC_TOKEN=<token> uv run pytest tests/test_integration.py -v

# パイプラインE2Eテスト (6件) — 要 GitLab + Runner + プロジェクト
PIPELINE_TEST=1 SYNC_TOKEN=<token> CI_PROJECT_ID=<id> uv run pytest tests/test_pipeline.py -v
```

## 手動ファイルの保護

`docs/` 配下に手動でファイルを追加しても、同期時に削除されません。
自動生成ファイルには `managed_by: gitmirror-md` マーカーが front matter に含まれており、
このマーカーがないファイルは同期対象外として保護されます。

ただし、手動追加ファイルは `index.md` には反映されません。`index.md` は API から取得したデータのみで生成されます。
