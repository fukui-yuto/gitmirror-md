"""パイプライン統合テスト: GitLab CI/CD パイプラインの実行を検証する.

前提条件:
    - docker compose up で GitLab + Runner が起動していること
    - Runner が登録済みであること
    - テスト用プロジェクトにソースコードが push 済みであること
    - 環境変数 PIPELINE_TEST=1 が設定されていること

実行方法:
    PIPELINE_TEST=1 SYNC_TOKEN=<token> CI_PROJECT_ID=<id> uv run pytest tests/test_pipeline.py -v
"""

import os
import time

import pytest
import gitlab

GITLAB_URL = os.environ.get("GITLAB_URL", "http://localhost:8080")
PIPELINE_TIMEOUT = 180  # seconds


pytestmark = pytest.mark.skipif(
    os.environ.get("PIPELINE_TEST") != "1",
    reason="PIPELINE_TEST=1 not set (requires running GitLab + Runner)",
)


@pytest.fixture(scope="module")
def gl():
    """Authenticated GitLab client."""
    token = os.environ.get("SYNC_TOKEN", "glpat-ci-test-token99")
    client = gitlab.Gitlab(GITLAB_URL, private_token=token, keep_base_url=True)
    try:
        client.auth()
    except Exception:
        pytest.skip("Cannot authenticate to GitLab. Is it running?")
    return client


@pytest.fixture(scope="module")
def project(gl):
    """既存のテスト用プロジェクトを取得する."""
    project_id = os.environ.get("CI_PROJECT_ID", "1")
    try:
        return gl.projects.get(project_id)
    except Exception:
        pytest.skip(f"Project {project_id} not found. Push source code first.")


@pytest.fixture(scope="module")
def synced_pipeline(gl, project):
    """SYNC_TARGET=all でパイプラインを実行し結果を返す."""
    pipeline = project.pipelines.create({
        "ref": "main",
        "variables": [{"key": "SYNC_TARGET", "value": "all"}],
    })
    status = _wait_for_pipeline(pipeline)
    return pipeline, status


def _wait_for_pipeline(pipeline, timeout=PIPELINE_TIMEOUT):
    """パイプラインの完了を待つ."""
    start = time.time()
    while time.time() - start < timeout:
        pipeline.refresh()
        if pipeline.status in ("success", "failed", "canceled", "skipped"):
            return pipeline.status
        time.sleep(5)
    return pipeline.status


def _get_job_trace(project, pipeline):
    """失敗したジョブのトレースを取得する."""
    jobs = pipeline.jobs.list(get_all=True)
    traces = []
    for job in jobs:
        if job.status == "failed":
            trace = project.jobs.get(job.id).trace().decode("utf-8", errors="replace")
            lines = trace.strip().split("\n")
            traces.append(f"Job '{job.name}' failed:\n" + "\n".join(lines[-30:]))
    return "\n\n".join(traces)


class TestPipelineExecution:
    def test_pipeline_succeeds(self, project, synced_pipeline):
        """パイプラインが正常に完了することを確認."""
        pipeline, status = synced_pipeline
        if status == "failed":
            trace = _get_job_trace(project, pipeline)
            pytest.fail(f"Pipeline failed:\n{trace}")
        assert status == "success", f"Pipeline status: {status}"

    def test_wiki_files_committed(self, project, synced_pipeline):
        """パイプライン後、docs/wiki/ にファイルがコミットされていることを確認."""
        tree = project.repository_tree(path="docs/wiki", ref="main", recursive=True, get_all=True)
        names = [item["name"] for item in tree if item["type"] == "blob"]
        assert "index.md" in names, f"Wiki index.md not found. Files: {names}"
        assert any(n.endswith(".md") and n != "index.md" and n != ".gitkeep" for n in names), \
            f"No wiki page files found. Files: {names}"

    def test_issue_files_committed(self, project, synced_pipeline):
        """パイプライン後、docs/issues/ にファイルがコミットされていることを確認."""
        tree = project.repository_tree(path="docs/issues", ref="main", recursive=True, get_all=True)
        paths = [item["path"] for item in tree if item["type"] == "blob"]
        assert any("index.md" in p for p in paths), f"Issues index.md not found. Files: {paths}"

    def test_front_matter_in_wiki(self, project, synced_pipeline):
        """Wiki ファイルに front matter と managed_by マーカーが含まれることを確認."""
        tree = project.repository_tree(path="docs/wiki", ref="main", recursive=True, get_all=True)
        wiki_files = [item for item in tree if item["type"] == "blob" and item["name"].endswith(".md")
                      and item["name"] not in ("index.md", ".gitkeep")]
        assert len(wiki_files) > 0, "No wiki files found"

        file_info = project.files.get(file_path=wiki_files[0]["path"], ref="main")
        content = file_info.decode().decode("utf-8")
        assert "managed_by: gitmirror-md" in content
        assert content.startswith("---")

    def test_skip_ci_prevents_recursion(self, project, synced_pipeline):
        """同期コミットのメッセージに [skip ci] が含まれていることを確認."""
        commits = project.commits.list(per_page=5, get_all=False)
        sync_commits = [c for c in commits if "chore(sync):" in c.title]
        assert len(sync_commits) > 0, "No sync commits found"
        assert "[skip ci]" in sync_commits[0].title

    def test_idempotent_run(self, project, gl):
        """差分なしの再実行で空コミットが作られないことを確認."""
        commits_before = project.commits.list(per_page=5, get_all=False)
        before_count = len(commits_before)
        before_sha = commits_before[0].id

        pipeline = project.pipelines.create({
            "ref": "main",
            "variables": [{"key": "SYNC_TARGET", "value": "all"}],
        })
        status = _wait_for_pipeline(pipeline)
        assert status == "success", f"Pipeline status: {status}"

        commits_after = project.commits.list(per_page=5, get_all=False)
        after_sha = commits_after[0].id
        assert before_sha == after_sha, "Unexpected new commit created (should be idempotent)"
