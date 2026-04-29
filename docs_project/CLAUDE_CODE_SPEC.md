# gitmirror-md — Claude Code 向け実装指示書

## 1. プロジェクト概要

Self-Managed GitLab の **Wiki と Issue を、同一リポジトリの `docs/` 配下に Markdown でミラー** する CI/CD ツール。Wiki または Issue が更新されるたびに Webhook 経由でパイプラインを起動し、`main` ブランチへ直接コミットする。

- ツール名: **gitmirror-md**
- 実装言語: Python 3.12
- 実行環境: GitLab CI/CD (Self-Managed GitLab + Docker executor Runner)
- メイン依存ライブラリ: `python-gitlab`, `PyYAML`

## 2. 要件

### 機能要件

| ID | 要件 |
|----|------|
| F-1 | GitLab Wiki の全ページを `docs/wiki/` 配下に Markdown で出力する |
| F-2 | Wiki の slug 階層をディレクトリ構造として再現する |
| F-3 | GitLab Issue の本文を `docs/issues/{open,closed}/<iid>-<slug>.md` に出力する |
| F-4 | Issue の **ユーザコメント** を時系列で同ファイルに追記する(System Notes は除外) |
| F-5 | Issue の `state` に応じて `open/` `closed/` を自動で振り分ける(closeされたら open/ から削除し closed/ に作成) |
| F-6 | 各 Issue ファイル冒頭に YAML front matter で `iid / state / labels / assignees / author / created_at / updated_at / web_url` を出力 |
| F-7 | Issue 一覧 `docs/issues/index.md` と Wiki 一覧 `docs/wiki/index.md` を自動生成 |
| F-8 | パイプラインから `main` ブランチへ直接 push する(差分があるときのみコミット) |
| F-9 | 同期対象を CI 変数 `SYNC_TARGET=wiki|issues|all` で切替可能 |

### 非機能要件

- API ページングは全件取得を保証(`get_all=True` 相当)
- 既存ファイルは毎回上書きではなく、削除されたWikiページ/Issueは `docs/` からも削除する(残骸を残さない)
- 出力 Markdown はファイル冒頭からの内容差分が安定するよう、決定的なソート順で生成する
- GitLab API のレート制限を考慮し、429 リトライを実装

## 3. ディレクトリ構成(完成形)

```
.
├── docker-compose.yml        # 既存(テスト用GitLab、変更不要)
├── SETUP.md                  # 既存(検証環境構築手順、変更不要)
├── README.md                 # 既存(プロジェクト説明、必要に応じ追記)
├── requirements.txt          # 既存
├── .gitlab-ci.yml            # 新規実装
├── scripts/
│   ├── __init__.py
│   ├── gitlab_client.py      # 新規実装: python-gitlab薄ラッパ
│   ├── sync_wiki.py          # 新規実装: Wiki -> docs/wiki/
│   ├── sync_issues.py        # 新規実装: Issues -> docs/issues/
│   └── common.py             # 新規実装: slug化/front matter/ファイルIO等の共通処理
└── docs/
    ├── wiki/                 # 自動生成(.gitkeepのみコミット)
    └── issues/
        ├── open/             # .gitkeep のみ
        └── closed/           # .gitkeep のみ
```

## 4. 各ファイルの実装仕様

### 4.1 `scripts/gitlab_client.py`

- `python-gitlab` の `Gitlab` インスタンス生成をラップする
- 環境変数:
  - `GITLAB_URL` (例: `http://gitlab/`)
  - `SYNC_TOKEN` (Personal Access Token, scope: `api`)
  - `CI_PROJECT_ID` (CI/CDの組み込み変数)
- 提供する関数/メソッド:
  - `get_project()` -> `gitlab.v4.objects.Project`
  - 429 / 5xx に対し、指数バックオフで最大5回リトライするデコレータ `@retry_on_rate_limit`

### 4.2 `scripts/common.py`

- `slugify(text: str) -> str`: 日本語含む文字列を安全なファイル名に変換(空白→`-`、記号除去、長さ80字制限)
- `write_file_if_changed(path: Path, content: str) -> bool`: 既存ファイルと内容比較し、差分があるときだけ書き込み。戻り値で書き込み有無を返す
- `dump_front_matter(data: dict) -> str`: YAML front matter 文字列を生成(`---\n...\n---\n`)
- `clean_orphaned_files(target_dir: Path, valid_paths: set[Path]) -> list[Path]`: `target_dir` 以下で `valid_paths` に含まれないファイルを削除し、削除したパスを返す
- 全関数に型ヒントと docstring を付ける

### 4.3 `scripts/sync_wiki.py`

- エントリポイント: `main()`
- 処理フロー:
  1. `get_project()` で対象プロジェクト取得
  2. `project.wikis.list(get_all=True)` で全ページslug一覧取得
  3. 各 slug に対し `project.wikis.get(slug)` で本文取得
  4. `docs/wiki/<slug_path>.md` に書き出し(slug の `/` は階層として展開)
  5. `docs/wiki/index.md` に全ページのリンク一覧を生成(slug 昇順)
  6. 取得した slug 集合に存在しないファイルは `clean_orphaned_files` で削除
- 出力 Markdown の先頭に front matter で `slug / title / format / updated_at` を付与
- ログは `print` ではなく `logging` モジュール、INFO レベルで「作成 / 更新 / 削除」を区別して出力

### 4.4 `scripts/sync_issues.py`

- エントリポイント: `main()`
- 処理フロー:
  1. `project.issues.list(state='all', get_all=True, order_by='updated_at', sort='desc')` で全 Issue 取得
  2. 各 Issue に対し:
     - `notes = issue.notes.list(get_all=True, sort='asc', order_by='created_at')`
     - **`note.system == True` のものは除外**(System Notes 除外)
     - 残ったユーザコメントを古い順に整形
  3. `state` に応じて `docs/issues/open/` または `docs/issues/closed/` に出力
  4. ファイル名: `f"{iid:04d}-{slugify(title)}.md"`
  5. **state遷移時のクリーンアップ**: 今回 `closed` の Issue が `open/` に古いファイルとして残っていたら削除(逆も同様)
  6. `docs/issues/index.md` を生成。テーブル形式で `iid / state / title / labels / assignees / updated_at` を昇順表示
  7. 削除された Issue(API応答に存在しない iid)は両ディレクトリから削除

#### Issue Markdown フォーマット

```markdown
---
iid: 12
state: opened
title: "ログイン画面で500エラー"
labels:
  - bug
  - priority::high
assignees:
  - yuto
author: yuto
created_at: "2026-04-20T10:00:00.000Z"
updated_at: "2026-04-25T14:30:00.000Z"
web_url: "http://gitlab.local:8080/root/sample/-/issues/12"
---

# #12 ログイン画面で500エラー

## 本文

(issue.description をそのまま)

## コメント

### @yuto — 2026-04-21 09:15

(コメント本文)

### @taro — 2026-04-21 10:42

(コメント本文)
```

- コメントが0件のときは `## コメント` セクションごと省略
- `description` が空のときは `## 本文` セクション下に `_(本文なし)_` と表示

### 4.5 `.gitlab-ci.yml`

```yaml
stages:
  - sync

variables:
  GIT_STRATEGY: clone
  GIT_DEPTH: "0"
  SYNC_TARGET: "all"  # wiki | issues | all (パイプライン起動時に上書き可)

.sync_base:
  stage: sync
  image: python:3.12-slim
  before_script:
    - apt-get update -qq && apt-get install -y -qq git
    - pip install --no-cache-dir -r requirements.txt
    - git config user.name "${GIT_AUTHOR_NAME}"
    - git config user.email "${GIT_AUTHOR_EMAIL}"
    # push 用にHTTPS認証URLへ書き換え
    - git remote set-url origin "https://oauth2:${SYNC_TOKEN}@${CI_SERVER_HOST}:${CI_SERVER_PORT}/${CI_PROJECT_PATH}.git"
  script:
    - |
      if [ "$SYNC_TARGET" = "wiki" ] || [ "$SYNC_TARGET" = "all" ]; then
        python -m scripts.sync_wiki
      fi
      if [ "$SYNC_TARGET" = "issues" ] || [ "$SYNC_TARGET" = "all" ]; then
        python -m scripts.sync_issues
      fi
    - |
      git add docs/
      if git diff --cached --quiet; then
        echo "No changes to commit."
      else
        git commit -m "chore(sync): update docs from wiki/issues [skip ci]"
        git push origin HEAD:main
      fi
  rules:
    - if: '$CI_PIPELINE_SOURCE == "trigger" || $CI_PIPELINE_SOURCE == "web" || $CI_PIPELINE_SOURCE == "schedule"'

sync:run:
  extends: .sync_base
  tags:
    - docker
```

- コミットメッセージに `[skip ci]` を入れて、自身の push で再帰的にパイプラインが走らないようにする
- `rules` で trigger / web / schedule 起動のみ許可。通常の push では走らない

### 4.6 Webhook → Pipeline Trigger 連携(SETUP.md追記)

GitLab CI/CD は Wiki/Issue イベントを直接トリガーできないため、以下の手順で連携する。

1. **Settings → CI/CD → Pipeline triggers** で Trigger Token を発行
2. **Settings → Webhooks** で以下を作成:
   - URL:
     ```
     http://gitlab/api/v4/projects/<PROJECT_ID>/trigger/pipeline?token=<TRIGGER_TOKEN>&ref=main&variables[SYNC_TARGET]=wiki
     ```
   - Trigger: `Wiki page events` のみチェック
3. 同様に Issue 用 Webhook を作成(`variables[SYNC_TARGET]=issues`、Trigger は `Issues events` と `Comments`)

> Self-Managed の Webhook が同インスタンスのAPIを叩けない場合、Admin Area → Settings → Network → Outbound requests で `Allow requests to the local network from webhooks` を有効化する。

## 5. 実装順序(推奨)

1. `scripts/common.py` を実装し、単体で動作確認
2. `scripts/gitlab_client.py` を実装し、Pythonインタラクティブで `get_project()` の疎通確認
3. `scripts/sync_wiki.py` 実装 → ローカル実行で `docs/wiki/` が生成されることを確認
4. `scripts/sync_issues.py` 実装 → 同様にローカル確認
5. `.gitlab-ci.yml` 実装 → web トリガーで手動実行 → push 成功を確認
6. Webhook 設定 → Wiki / Issue を実際に編集してパイプラインが自動起動することを確認

## 6. テスト観点

- [ ] Wiki ページを新規作成 → `docs/wiki/` に該当ファイルが追加される
- [ ] Wiki ページを編集 → 該当ファイルの内容が更新される
- [ ] Wiki ページを削除 → 該当ファイルが `docs/wiki/` から削除される
- [ ] Issue を新規作成 → `docs/issues/open/` に追加される
- [ ] Issue にコメント追加 → 同ファイルに `## コメント` セクションが追記される
- [ ] Issue を close → `open/` から消え `closed/` に移動する
- [ ] Issue を削除(管理者のみ可) → 両ディレクトリから消える
- [ ] System Notes(label変更通知等)が `## コメント` に含まれていない
- [ ] 同期対象なし(差分なし)の場合、空コミットが作られない
- [ ] パイプラインが自身の push で再帰起動しない(`[skip ci]` 効いている)

## 7. 制約・前提

- 対象プロジェクトの Wiki / Issues 機能が有効化されていること
- Runner が `python:3.12-slim` イメージを利用できること
- `SYNC_TOKEN` は対象プロジェクトに対し `api` + `write_repository` 権限を持つこと
- `CI_SERVER_HOST` / `CI_SERVER_PORT` は GitLab 組み込みの CI 変数を使用

## 8. 参考: 既存ファイル

`docker-compose.yml`, `SETUP.md`, `README.md`, `requirements.txt` はすでに用意済み。**変更不要**。Claude Code はこれらの内容を前提として上記新規ファイルを実装すること。
