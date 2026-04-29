"""統合テスト: 実際の GitLab API に対してスクリプトを実行する.

前提条件:
    - docker compose up で GitLab が起動していること
    - 環境変数 INTEGRATION_TEST=1 が設定されていること

実行方法:
    INTEGRATION_TEST=1 uv run pytest tests/test_integration.py -v
"""

import os
import time
from pathlib import Path

import pytest
import gitlab

GITLAB_URL = os.environ.get("GITLAB_URL", "http://localhost:8080")
ADMIN_PASSWORD = "RootPass12345!"
PROJECT_NAME = "integration-test"

# Skip all tests if INTEGRATION_TEST is not set
pytestmark = pytest.mark.skipif(
    os.environ.get("INTEGRATION_TEST") != "1",
    reason="INTEGRATION_TEST=1 not set (requires running GitLab)",
)


@pytest.fixture(scope="module")
def pat_token():
    """GitLab の root ユーザー用 PAT を取得または作成する."""
    # Try to use existing token first
    token_value = os.environ.get("SYNC_TOKEN", "glpat-integration-test-token")

    # Verify token works
    gl = gitlab.Gitlab(GITLAB_URL, private_token=token_value, keep_base_url=True)
    try:
        gl.auth()
        return token_value
    except Exception:
        pytest.skip("Cannot authenticate to GitLab. Is it running?")


@pytest.fixture(scope="module")
def project(pat_token):
    """テスト用プロジェクトを作成する（既存なら削除して再作成）."""
    gl = gitlab.Gitlab(GITLAB_URL, private_token=pat_token, keep_base_url=True)
    gl.auth()

    # Delete existing project if exists
    for p in gl.projects.list(search=PROJECT_NAME, get_all=True):
        if p.path == PROJECT_NAME:
            p.delete()
            time.sleep(2)  # Wait for deletion

    # Create new project
    proj = gl.projects.create({
        "name": PROJECT_NAME,
        "initialize_with_readme": True,
        "wiki_enabled": True,
        "issues_enabled": True,
    })

    yield proj

    # Cleanup
    try:
        proj.delete()
    except Exception:
        pass


@pytest.fixture(scope="module")
def env_vars(pat_token, project):
    """同期スクリプト用の環境変数を設定する."""
    os.environ["GITLAB_URL"] = GITLAB_URL
    os.environ["SYNC_TOKEN"] = pat_token
    os.environ["CI_PROJECT_ID"] = str(project.id)
    os.environ["CI_PROJECT_PATH"] = project.path_with_namespace
    yield
    # Cleanup
    for key in ["GITLAB_URL", "SYNC_TOKEN", "CI_PROJECT_ID", "CI_PROJECT_PATH"]:
        os.environ.pop(key, None)


@pytest.fixture(autouse=True)
def clean_docs():
    """テスト前後で docs/ をクリーンアップする."""
    docs_dir = Path("docs")
    yield
    # Cleanup generated files
    for f in docs_dir.rglob("*.md"):
        if f.name != ".gitkeep":
            f.unlink()


class TestWikiSync:
    def test_sync_creates_wiki_files(self, project, env_vars):
        """Wiki ページを作成し、同期でファイルが生成されることを確認."""
        # Create wiki pages
        project.wikis.create({"title": "Home", "content": "# Welcome\n\nThis is home."})
        project.wikis.create({"title": "Guide", "content": "## Setup\n\nStep 1..."})

        from scripts.sync_wiki import main
        main()

        assert (Path("docs/wiki/Home.md")).exists()
        assert (Path("docs/wiki/Guide.md")).exists()
        assert (Path("docs/wiki/index.md")).exists()

        # Verify content
        home_content = Path("docs/wiki/Home.md").read_text(encoding="utf-8")
        assert "slug: Home" in home_content
        assert "# Welcome" in home_content
        assert "managed_by: gitmirror-md" in home_content

    def test_sync_index_sorted(self, project, env_vars):
        """index.md がスラグ昇順でソートされていることを確認."""
        from scripts.sync_wiki import main
        main()

        index = Path("docs/wiki/index.md").read_text(encoding="utf-8")
        guide_pos = index.index("Guide")
        home_pos = index.index("Home")
        assert guide_pos < home_pos  # G < H alphabetically

    def test_sync_deletes_removed_page(self, project, env_vars):
        """Wiki ページを削除すると docs からも消えることを確認."""
        from scripts.sync_wiki import main

        # First sync
        main()
        assert Path("docs/wiki/Guide.md").exists()

        # Delete wiki page
        project.wikis.delete("Guide")

        # Second sync
        main()
        assert not Path("docs/wiki/Guide.md").exists()
        assert Path("docs/wiki/Home.md").exists()


class TestIssueSync:
    def test_sync_creates_open_issue(self, project, env_vars):
        """Issue 作成後に同期で open/ にファイルが生成される."""
        project.issues.create({
            "title": "Test bug",
            "description": "Something is broken",
            "labels": "bug",
        })

        from scripts.sync_issues import main
        main()

        files = list(Path("docs/issues/open").glob("0001-*.md"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "state: opened" in content
        assert "Something is broken" in content
        assert "managed_by: gitmirror-md" in content

    def test_sync_includes_comments(self, project, env_vars):
        """コメントが同期されることを確認."""
        issue = project.issues.get(1)
        issue.notes.create({"body": "I can confirm this bug"})

        from scripts.sync_issues import main
        main()

        files = list(Path("docs/issues/open").glob("0001-*.md"))
        content = files[0].read_text(encoding="utf-8")
        assert "## コメント" in content
        assert "I can confirm this bug" in content

    def test_sync_excludes_system_notes(self, project, env_vars):
        """System Notes が除外されることを確認."""
        # Add a label (creates system note)
        issue = project.issues.get(1)
        issue.labels = ["bug", "confirmed"]
        issue.save()

        from scripts.sync_issues import main
        main()

        files = list(Path("docs/issues/open").glob("0001-*.md"))
        content = files[0].read_text(encoding="utf-8")
        assert "added ~confirmed label" not in content.lower()

    def test_sync_moves_closed_issue(self, project, env_vars):
        """Issue を close すると closed/ に移動する."""
        issue = project.issues.get(1)
        issue.state_event = "close"
        issue.save()

        from scripts.sync_issues import main
        main()

        open_files = list(Path("docs/issues/open").glob("0001-*.md"))
        closed_files = list(Path("docs/issues/closed").glob("0001-*.md"))
        assert len(open_files) == 0
        assert len(closed_files) == 1

    def test_sync_creates_index(self, project, env_vars):
        """index.md がテーブル形式で生成される."""
        from scripts.sync_issues import main
        main()

        index = Path("docs/issues/index.md").read_text(encoding="utf-8")
        assert "| iid | state |" in index
        assert "| 1 |" in index

    def test_manual_file_not_deleted(self, project, env_vars):
        """手動追加ファイルが削除されないことを確認."""
        manual_file = Path("docs/issues/open/manual-notes.md")
        manual_file.parent.mkdir(parents=True, exist_ok=True)
        manual_file.write_text("# My manual notes\n\nThis should not be deleted.\n")

        from scripts.sync_issues import main
        main()

        assert manual_file.exists()
        assert "My manual notes" in manual_file.read_text(encoding="utf-8")
