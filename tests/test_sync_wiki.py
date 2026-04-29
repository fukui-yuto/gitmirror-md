"""scripts/sync_wiki.py の単体テスト."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.sync_wiki import main, DOCS_WIKI_DIR


class FakeWikiPage:
    def __init__(self, slug, title, content="page content", format="markdown", updated_at=None):
        self.slug = slug
        self.title = title
        self.content = content
        self.format = format
        if updated_at:
            self.updated_at = updated_at


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("GITLAB_URL", "http://gitlab.local:8080")
    monkeypatch.setenv("SYNC_TOKEN", "test-token")
    monkeypatch.setenv("CI_PROJECT_ID", "1")
    monkeypatch.setenv("CI_PROJECT_PATH", "root/sample")


@pytest.fixture
def work_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs" / "wiki").mkdir(parents=True)
    return tmp_path


class TestSyncWiki:
    def test_creates_wiki_files(self, mock_env, work_dir):
        pages = [FakeWikiPage("home", "Home", "Welcome")]
        mock_project = MagicMock()

        with patch("scripts.sync_wiki.get_project", return_value=mock_project):
            mock_project.wikis.list.return_value = pages
            mock_project.wikis.get.return_value = pages[0]
            main()

        output = work_dir / "docs" / "wiki" / "home.md"
        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert "slug: home" in content
        assert "title: Home" in content
        assert "Welcome" in content

    def test_creates_index(self, mock_env, work_dir):
        pages = [
            FakeWikiPage("beta", "Beta Page"),
            FakeWikiPage("alpha", "Alpha Page"),
        ]
        mock_project = MagicMock()

        with patch("scripts.sync_wiki.get_project", return_value=mock_project):
            mock_project.wikis.list.return_value = pages
            mock_project.wikis.get.side_effect = lambda slug: next(p for p in pages if p.slug == slug)
            main()

        index = work_dir / "docs" / "wiki" / "index.md"
        assert index.exists()
        content = index.read_text(encoding="utf-8")
        # alpha should come before beta (sorted by slug)
        assert content.index("alpha") < content.index("beta")

    def test_nested_slug_creates_directory(self, mock_env, work_dir):
        pages = [FakeWikiPage("parent/child", "Child Page")]
        mock_project = MagicMock()

        with patch("scripts.sync_wiki.get_project", return_value=mock_project):
            mock_project.wikis.list.return_value = pages
            mock_project.wikis.get.return_value = pages[0]
            main()

        output = work_dir / "docs" / "wiki" / "parent" / "child.md"
        assert output.exists()

    def test_removes_orphaned_files(self, mock_env, work_dir):
        # Pre-existing managed file that no longer exists in wiki
        orphan = work_dir / "docs" / "wiki" / "old-page.md"
        orphan.write_text("---\nmanaged_by: gitmirror-md\n---\nold content")

        pages = [FakeWikiPage("home", "Home")]
        mock_project = MagicMock()

        with patch("scripts.sync_wiki.get_project", return_value=mock_project):
            mock_project.wikis.list.return_value = pages
            mock_project.wikis.get.return_value = pages[0]
            main()

        assert not orphan.exists()

    def test_no_updated_at_omits_from_front_matter(self, mock_env, work_dir):
        page = FakeWikiPage("test", "Test")
        # No updated_at attribute
        if hasattr(page, "updated_at"):
            delattr(page, "updated_at")
        mock_project = MagicMock()

        with patch("scripts.sync_wiki.get_project", return_value=mock_project):
            mock_project.wikis.list.return_value = [page]
            mock_project.wikis.get.return_value = page
            main()

        output = work_dir / "docs" / "wiki" / "test.md"
        content = output.read_text(encoding="utf-8")
        assert "updated_at" not in content
