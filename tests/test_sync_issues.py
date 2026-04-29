"""scripts/sync_issues.py の単体テスト."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.sync_issues import main, DOCS_ISSUES_DIR, OPEN_DIR, CLOSED_DIR


class FakeNote:
    def __init__(self, author_username, body, created_at, system=False):
        self.author = {"username": author_username}
        self.body = body
        self.created_at = created_at
        self.system = system


class FakeIssue:
    def __init__(self, iid, title, state="opened", description="", labels=None,
                 assignees=None, author="yuto", created_at="2026-04-20T10:00:00.000Z",
                 updated_at="2026-04-25T14:30:00.000Z", web_url="http://gitlab/issues/1",
                 notes=None):
        self.iid = iid
        self.title = title
        self.state = state
        self.description = description
        self.labels = labels or []
        self.assignees = assignees or [{"username": author}]
        self.author = {"username": author}
        self.created_at = created_at
        self.updated_at = updated_at
        self.web_url = web_url
        self._notes = notes or []
        self.notes = MagicMock()
        self.notes.list.return_value = self._notes


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("GITLAB_URL", "http://gitlab.local:8080")
    monkeypatch.setenv("SYNC_TOKEN", "test-token")
    monkeypatch.setenv("CI_PROJECT_ID", "1")
    monkeypatch.setenv("CI_PROJECT_PATH", "root/sample")


@pytest.fixture
def work_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs" / "issues" / "open").mkdir(parents=True)
    (tmp_path / "docs" / "issues" / "closed").mkdir(parents=True)
    return tmp_path


class TestSyncIssues:
    def test_creates_open_issue(self, mock_env, work_dir):
        issues = [FakeIssue(1, "Bug report", state="opened", description="Something broke")]
        mock_project = MagicMock()

        with patch("scripts.sync_issues.get_project", return_value=mock_project):
            mock_project.issues.list.return_value = issues
            main()

        files = list((work_dir / "docs" / "issues" / "open").glob("0001-*.md"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "state: opened" in content
        assert "Something broke" in content

    def test_creates_closed_issue(self, mock_env, work_dir):
        issues = [FakeIssue(2, "Fixed bug", state="closed")]
        mock_project = MagicMock()

        with patch("scripts.sync_issues.get_project", return_value=mock_project):
            mock_project.issues.list.return_value = issues
            main()

        files = list((work_dir / "docs" / "issues" / "closed").glob("0002-*.md"))
        assert len(files) == 1

    def test_state_transition_removes_old_file(self, mock_env, work_dir):
        # Simulate issue that was open, now closed
        old_file = work_dir / "docs" / "issues" / "open" / "0003-old-title.md"
        old_file.write_text("old")

        issues = [FakeIssue(3, "Old title", state="closed")]
        mock_project = MagicMock()

        with patch("scripts.sync_issues.get_project", return_value=mock_project):
            mock_project.issues.list.return_value = issues
            main()

        assert not old_file.exists()
        files = list((work_dir / "docs" / "issues" / "closed").glob("0003-*.md"))
        assert len(files) == 1

    def test_excludes_system_notes(self, mock_env, work_dir):
        notes = [
            FakeNote("yuto", "User comment", "2026-04-21T09:15:00.000Z", system=False),
            FakeNote("system", "added label ~bug", "2026-04-21T09:16:00.000Z", system=True),
        ]
        issues = [FakeIssue(4, "With notes", notes=notes)]
        mock_project = MagicMock()

        with patch("scripts.sync_issues.get_project", return_value=mock_project):
            mock_project.issues.list.return_value = issues
            main()

        files = list((work_dir / "docs" / "issues" / "open").glob("0004-*.md"))
        content = files[0].read_text(encoding="utf-8")
        assert "User comment" in content
        assert "added label" not in content

    def test_no_comments_section_when_no_user_notes(self, mock_env, work_dir):
        notes = [
            FakeNote("system", "changed status", "2026-04-21T09:16:00.000Z", system=True),
        ]
        issues = [FakeIssue(5, "No comments", notes=notes)]
        mock_project = MagicMock()

        with patch("scripts.sync_issues.get_project", return_value=mock_project):
            mock_project.issues.list.return_value = issues
            main()

        files = list((work_dir / "docs" / "issues" / "open").glob("0005-*.md"))
        content = files[0].read_text(encoding="utf-8")
        assert "## コメント" not in content

    def test_empty_description(self, mock_env, work_dir):
        issues = [FakeIssue(6, "Empty desc", description="")]
        mock_project = MagicMock()

        with patch("scripts.sync_issues.get_project", return_value=mock_project):
            mock_project.issues.list.return_value = issues
            main()

        files = list((work_dir / "docs" / "issues" / "open").glob("0006-*.md"))
        content = files[0].read_text(encoding="utf-8")
        assert "_(本文なし)_" in content

    def test_creates_index(self, mock_env, work_dir):
        issues = [
            FakeIssue(2, "Second"),
            FakeIssue(1, "First"),
        ]
        mock_project = MagicMock()

        with patch("scripts.sync_issues.get_project", return_value=mock_project):
            mock_project.issues.list.return_value = issues
            main()

        index = work_dir / "docs" / "issues" / "index.md"
        assert index.exists()
        content = index.read_text(encoding="utf-8")
        # iid 昇順
        assert content.index("| 1 |") < content.index("| 2 |")

    def test_removes_deleted_issue(self, mock_env, work_dir):
        # Managed file exists for issue that no longer exists in API
        orphan = work_dir / "docs" / "issues" / "open" / "0099-deleted.md"
        orphan.write_text("---\nmanaged_by: gitmirror-md\n---\nold")

        issues = [FakeIssue(1, "Current")]
        mock_project = MagicMock()

        with patch("scripts.sync_issues.get_project", return_value=mock_project):
            mock_project.issues.list.return_value = issues
            main()

        assert not orphan.exists()
